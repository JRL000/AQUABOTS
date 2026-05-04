/**
 * pixhawk_link.c
 *
 * MAVLink bridge to a directly-attached Pixhawk over UART. Demo-only path
 * for follower hulls without a Jetson. See pixhawk_link.h.
 */

#include "pixhawk_link.h"
#include "mav_min.h"
#include "latlon_offset.h"
#include "swarm_protocol.h"
#include "swarm_transport.h"
#include "node_config.h"
#include "esp_log.h"
#include "esp_console.h"
#include "esp_timer.h"
#include "driver/uart.h"
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include <string.h>
#include <stdio.h>

static const char *TAG = "PX_LINK";

// ============================================================================
// SHARED STATE (protected by spinlock)
// ============================================================================

static portMUX_TYPE s_lock = portMUX_INITIALIZER_UNLOCKED;

static struct {
    /* Cached leader GPS (from MSG_TYPE_GPS_ANCHOR). */
    bool     anchor_valid;
    int32_t  anchor_lat_e7;
    int32_t  anchor_lon_e7;
    int16_t  anchor_heading_cdeg;
    int64_t  anchor_received_at_us;

    /* Cached formation offset (from on_position_assigned). */
    bool     offset_valid;
    int32_t  offset_x_mm;
    int32_t  offset_y_mm;
    int16_t  offset_heading_deg;

    /* Last computed target (for rate limiting + diagnostics). */
    bool     target_valid;
    int32_t  target_lat_e7;
    int32_t  target_lon_e7;
    int64_t  target_last_sent_us;

    /* Pixhawk-reported state (from incoming HEARTBEAT). */
    bool     px_armed;
    uint32_t px_custom_mode;
    int64_t  px_last_heartbeat_us;

    /* Retry timing for the GUIDED+ARM ladder. */
    int64_t  last_set_mode_us;
    int64_t  last_arm_us;

    /* Stop latch — sticky once set; cleared only on a fresh formation event
     * or explicit clear from the console. */
    bool     stopped;

    /* Counters. */
    uint32_t targets_sent;
    uint32_t heartbeats_sent;
    uint32_t heartbeats_rx;

    /* Sequence number for outgoing MAVLink frames. */
    uint8_t  seq;
} s;

static bool s_initialised = false;
static bool s_running = false;
static mav_min_parser_t s_parser;

/* Serialises uart_write_bytes() across the TX task and any external
 * callers (e.g., pixhawk_link_emergency_stop from the radio recv
 * chain). uart_write_bytes is not internally thread-safe per IDF docs;
 * concurrent calls would interleave bytes mid-MAVLink-frame. */
static SemaphoreHandle_t s_tx_mutex = NULL;

// ============================================================================
// HELPERS
// ============================================================================

static int64_t now_us(void) { return esp_timer_get_time(); }

static uint8_t self_sysid(void)
{
    uint16_t nid = node_config_get_node_id();
    if (nid == NODE_ID_INVALID) nid = 0;
    return (uint8_t)(PIXHAWK_LINK_SELF_SYSID_BASE + (nid & 0x3F));
}

static uint8_t next_seq(void)
{
    portENTER_CRITICAL(&s_lock);
    uint8_t v = s.seq++;
    portEXIT_CRITICAL(&s_lock);
    return v;
}

static void uart_send(const uint8_t *buf, size_t len)
{
    if (s_tx_mutex) xSemaphoreTake(s_tx_mutex, portMAX_DELAY);
    uart_write_bytes(PIXHAWK_LINK_UART_NUM, (const char *)buf, len);
    if (s_tx_mutex) xSemaphoreGive(s_tx_mutex);
}

static double recover_heading_deg(int16_t raw)
{
    /* swarm_bridge stores heading as int16_t centi-degrees but values
     * 327.68°..359.99° overflow into negative. Recover by interpreting
     * negative values as the uint16_t equivalent. Result returned as
     * floating-point degrees in [0, 360). */
    int32_t cdeg = (raw < 0) ? ((int32_t)raw + 65536) : (int32_t)raw;
    double  d    = cdeg / 100.0;
    while (d < 0)        d += 360.0;
    while (d >= 360.0)   d -= 360.0;
    return d;
}

// ============================================================================
// MAVLINK SENDERS
// ============================================================================

static void send_heartbeat(void)
{
    uint8_t frame[MAV_MIN_MAX_FRAME];
    size_t len = mav_min_pack_heartbeat(frame, next_seq(),
                                        self_sysid(),
                                        PIXHAWK_LINK_SELF_COMPID);
    uart_send(frame, len);
    portENTER_CRITICAL(&s_lock);
    s.heartbeats_sent++;
    portEXIT_CRITICAL(&s_lock);
}

static void send_set_mode(uint32_t custom_mode)
{
    uint8_t frame[MAV_MIN_MAX_FRAME];
    size_t len = mav_min_pack_set_mode(frame, next_seq(),
                                       self_sysid(),
                                       PIXHAWK_LINK_SELF_COMPID,
                                       PIXHAWK_LINK_TARGET_SYSID,
                                       custom_mode);
    uart_send(frame, len);
}

static void send_arm(bool arm)
{
    uint8_t frame[MAV_MIN_MAX_FRAME];
    size_t len = mav_min_pack_arm(frame, next_seq(),
                                  self_sysid(),
                                  PIXHAWK_LINK_SELF_COMPID,
                                  PIXHAWK_LINK_TARGET_SYSID,
                                  PIXHAWK_LINK_TARGET_COMPID,
                                  arm);
    uart_send(frame, len);
}

static void send_position_target(int32_t lat_e7, int32_t lon_e7)
{
    uint8_t frame[MAV_MIN_MAX_FRAME];
    uint32_t t_ms = (uint32_t)(now_us() / 1000);
    size_t len = mav_min_pack_position_target(frame, next_seq(),
                                              self_sysid(),
                                              PIXHAWK_LINK_SELF_COMPID,
                                              PIXHAWK_LINK_TARGET_SYSID,
                                              PIXHAWK_LINK_TARGET_COMPID,
                                              t_ms, lat_e7, lon_e7);
    uart_send(frame, len);
    portENTER_CRITICAL(&s_lock);
    s.targets_sent++;
    s.target_last_sent_us = now_us();
    s.target_lat_e7 = lat_e7;
    s.target_lon_e7 = lon_e7;
    s.target_valid = true;
    portEXIT_CRITICAL(&s_lock);
}

// ============================================================================
// ESP-NOW RECEIVE — MSG_TYPE_GPS_ANCHOR
// ============================================================================

static void on_radio_recv(const uint8_t *src_mac, const uint8_t *data,
                          int len, int8_t rssi)
{
    if (len < (int)sizeof(swarm_header_t)) return;
    swarm_header_t hdr;
    memcpy(&hdr, data, sizeof(hdr));
    if (hdr.msg_type != MSG_TYPE_GPS_ANCHOR) return;
    if (len < (int)(sizeof(hdr) + sizeof(gps_anchor_payload_t))) return;

    gps_anchor_payload_t payload;
    memcpy(&payload, data + sizeof(hdr), sizeof(payload));

    portENTER_CRITICAL(&s_lock);
    s.anchor_lat_e7         = payload.lat_e7;
    s.anchor_lon_e7         = payload.lon_e7;
    s.anchor_heading_cdeg   = payload.heading_cdeg;
    s.anchor_received_at_us = now_us();
    s.anchor_valid          = (payload.fix_type >= 3);
    portEXIT_CRITICAL(&s_lock);
}

// ============================================================================
// COMMAND SEQUENCER
// ============================================================================

/**
 * Decide what to send to the Pixhawk this tick. Called from the TX task at
 * a steady cadence. Implements the GUIDED + ARM + TARGET state ladder
 * without blocking: each tick fires at most one command.
 */
static void sequencer_tick(void)
{
    /* Snapshot shared state under lock. */
    portENTER_CRITICAL(&s_lock);
    bool     anchor_valid = s.anchor_valid;
    bool     offset_valid = s.offset_valid;
    bool     stopped      = s.stopped;
    int32_t  ax = s.anchor_lat_e7, ay = s.anchor_lon_e7;
    int16_t  ah = s.anchor_heading_cdeg;
    int64_t  anchor_age_us = now_us() - s.anchor_received_at_us;
    int32_t  ox = s.offset_x_mm, oy = s.offset_y_mm;
    int16_t  oh = s.offset_heading_deg;
    bool     px_armed     = s.px_armed;
    uint32_t px_mode      = s.px_custom_mode;
    int64_t  last_target  = s.target_last_sent_us;
    int64_t  last_set_mode = s.last_set_mode_us;
    int64_t  last_arm     = s.last_arm_us;
    portEXIT_CRITICAL(&s_lock);

    if (stopped) return;
    if (!anchor_valid || !offset_valid) return;
    if (anchor_age_us > (int64_t)PIXHAWK_LINK_ANCHOR_STALE_MS * 1000) {
        ESP_LOGW(TAG, "anchor stale (%lld ms) — switching Pixhawk to HOLD",
                 (long long)(anchor_age_us / 1000));
        send_set_mode(MAV_ROVER_MODE_HOLD);
        portENTER_CRITICAL(&s_lock);
        s.last_set_mode_us = now_us();
        portEXIT_CRITICAL(&s_lock);
        return;
    }

    int64_t now = now_us();

    /* 1. Make sure we're in GUIDED. */
    if (px_mode != MAV_ROVER_MODE_GUIDED) {
        if (now - last_set_mode > (int64_t)PIXHAWK_LINK_MODE_RETRY_MS * 1000) {
            ESP_LOGI(TAG, "→ SET_MODE GUIDED (current=%lu)", (unsigned long)px_mode);
            send_set_mode(MAV_ROVER_MODE_GUIDED);
            portENTER_CRITICAL(&s_lock);
            s.last_set_mode_us = now;
            portEXIT_CRITICAL(&s_lock);
        }
        return;
    }

    /* 2. Arm if needed. */
    if (!px_armed) {
        if (now - last_arm > (int64_t)PIXHAWK_LINK_ARM_RETRY_MS * 1000) {
            ESP_LOGI(TAG, "→ ARM");
            send_arm(true);
            portENTER_CRITICAL(&s_lock);
            s.last_arm_us = now;
            portEXIT_CRITICAL(&s_lock);
        }
        return;
    }

    /* 3. Send a target if it's been long enough since the last one. */
    if (now - last_target >= (int64_t)PIXHAWK_LINK_TARGET_MIN_PERIOD_MS * 1000) {
        int32_t target_lat, target_lon;
        latlon_offset_apply(ax, ay, recover_heading_deg(ah),
                            ox, oy, oh,
                            &target_lat, &target_lon, NULL);

        /* Sanity check — refuse obviously bad targets. */
        if (target_lat == 0 && target_lon == 0) {
            ESP_LOGW(TAG, "computed target (0,0); skipping send");
            return;
        }
        send_position_target(target_lat, target_lon);
    }
}

// ============================================================================
// BACKGROUND TASKS
// ============================================================================

static void rx_task(void *arg)
{
    (void)arg;
    uint8_t buf[64];
    while (s_running) {
        int n = uart_read_bytes(PIXHAWK_LINK_UART_NUM, buf, sizeof(buf),
                                pdMS_TO_TICKS(50));
        for (int i = 0; i < n; i++) {
            mav_min_msg_t msg;
            if (!mav_min_parse_byte(&s_parser, buf[i], &msg)) continue;
            if (msg.msgid != MAVLINK_MSG_ID_HEARTBEAT) continue;

            mav_min_heartbeat_t hb;
            if (!mav_min_decode_heartbeat(&msg, &hb)) continue;

            /* Only track the autopilot heartbeat (sysid 1, compid 1) — not
             * any other GCS that happens to be on the bus. */
            if (msg.sysid != PIXHAWK_LINK_TARGET_SYSID ||
                msg.compid != PIXHAWK_LINK_TARGET_COMPID) {
                continue;
            }
            portENTER_CRITICAL(&s_lock);
            s.px_armed             = (hb.base_mode & MAV_MODE_FLAG_SAFETY_ARMED) != 0;
            s.px_custom_mode       = hb.custom_mode;
            s.px_last_heartbeat_us = now_us();
            s.heartbeats_rx++;
            portEXIT_CRITICAL(&s_lock);
        }
    }
    vTaskDelete(NULL);
}

static void tx_task(void *arg)
{
    (void)arg;
    int64_t last_hb_us = 0;
    while (s_running) {
        int64_t now = now_us();
        if (now - last_hb_us >= (int64_t)PIXHAWK_LINK_HEARTBEAT_MS * 1000) {
            send_heartbeat();
            last_hb_us = now;
        }
        sequencer_tick();
        vTaskDelay(pdMS_TO_TICKS(100));
    }
    vTaskDelete(NULL);
}

// ============================================================================
// PUBLIC API
// ============================================================================

esp_err_t pixhawk_link_init(void)
{
    if (s_initialised) return ESP_OK;

    memset((void *)&s, 0, sizeof(s));
    mav_min_parser_reset(&s_parser);

    if (!s_tx_mutex) {
        s_tx_mutex = xSemaphoreCreateMutex();
        if (!s_tx_mutex) {
            ESP_LOGE(TAG, "failed to create tx mutex");
            return ESP_ERR_NO_MEM;
        }
    }

    uart_config_t cfg = {
        .baud_rate  = PIXHAWK_LINK_UART_BAUD,
        .data_bits  = UART_DATA_8_BITS,
        .parity     = UART_PARITY_DISABLE,
        .stop_bits  = UART_STOP_BITS_1,
        .flow_ctrl  = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    esp_err_t err;
    err = uart_driver_install(PIXHAWK_LINK_UART_NUM,
                              PIXHAWK_LINK_UART_BUF_SIZE,
                              PIXHAWK_LINK_UART_BUF_SIZE,
                              0, NULL, 0);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "uart_driver_install: %s", esp_err_to_name(err));
        return err;
    }
    err = uart_param_config(PIXHAWK_LINK_UART_NUM, &cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "uart_param_config: %s", esp_err_to_name(err));
        return err;
    }
    err = uart_set_pin(PIXHAWK_LINK_UART_NUM,
                       PIXHAWK_LINK_UART_TX_GPIO,
                       PIXHAWK_LINK_UART_RX_GPIO,
                       UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "uart_set_pin: %s", esp_err_to_name(err));
        return err;
    }

    s_initialised = true;
    ESP_LOGI(TAG, "init OK (UART%d TX=%d RX=%d @ %d)",
             PIXHAWK_LINK_UART_NUM,
             PIXHAWK_LINK_UART_TX_GPIO,
             PIXHAWK_LINK_UART_RX_GPIO,
             PIXHAWK_LINK_UART_BAUD);
    return ESP_OK;
}

esp_err_t pixhawk_link_start(void)
{
    if (!s_initialised) return ESP_ERR_INVALID_STATE;
    if (s_running) return ESP_OK;
    s_running = true;

    swarm_transport_register_recv_cb(on_radio_recv);

    xTaskCreate(rx_task, "px_rx", 4096, NULL, 5, NULL);
    xTaskCreate(tx_task, "px_tx", 4096, NULL, 5, NULL);
    ESP_LOGI(TAG, "started (sysid=%u compid=%u → target sysid=%u)",
             self_sysid(), PIXHAWK_LINK_SELF_COMPID, PIXHAWK_LINK_TARGET_SYSID);
    return ESP_OK;
}

void pixhawk_link_set_offset(const formation_position_t *pos, int node_index)
{
    (void)node_index;
    if (!pos) return;
    portENTER_CRITICAL(&s_lock);
    s.offset_x_mm        = pos->x_mm;
    s.offset_y_mm        = pos->y_mm;
    s.offset_heading_deg = pos->heading_deg;
    s.offset_valid       = true;
    s.stopped            = false;  /* fresh assignment clears the latch */
    portEXIT_CRITICAL(&s_lock);
}

void pixhawk_link_emergency_stop(void)
{
    portENTER_CRITICAL(&s_lock);
    s.stopped = true;
    portEXIT_CRITICAL(&s_lock);
    ESP_LOGW(TAG, "EMERGENCY STOP — HOLD + DISARM");
    send_set_mode(MAV_ROVER_MODE_HOLD);
    send_arm(false);
}

void pixhawk_link_get_status(pixhawk_link_status_t *out)
{
    if (!out) return;
    portENTER_CRITICAL(&s_lock);
    out->pixhawk_armed       = s.px_armed;
    out->pixhawk_custom_mode = s.px_custom_mode;
    out->anchor_valid        = s.anchor_valid;
    out->anchor_age_ms       = s.anchor_valid
                               ? (now_us() - s.anchor_received_at_us) / 1000
                               : -1;
    out->offset_valid        = s.offset_valid;
    out->target_lat_e7       = s.target_lat_e7;
    out->target_lon_e7       = s.target_lon_e7;
    out->targets_sent        = s.targets_sent;
    out->heartbeats_sent     = s.heartbeats_sent;
    out->heartbeats_rx       = s.heartbeats_rx;
    portEXIT_CRITICAL(&s_lock);
}

// ============================================================================
// CONSOLE COMMAND
// ============================================================================

static const char *rover_mode_name(uint32_t m)
{
    switch (m) {
        case MAV_ROVER_MODE_MANUAL:       return "MANUAL";
        case MAV_ROVER_MODE_HOLD:         return "HOLD";
        case MAV_ROVER_MODE_AUTO:         return "AUTO";
        case MAV_ROVER_MODE_RTL:          return "RTL";
        case MAV_ROVER_MODE_SMART_RTL:    return "SMART_RTL";
        case MAV_ROVER_MODE_GUIDED:       return "GUIDED";
        case MAV_ROVER_MODE_INITIALIZING: return "INITIALIZING";
        default:                          return "?";
    }
}

static int cmd_px_status(int argc, char **argv)
{
    (void)argc; (void)argv;
    pixhawk_link_status_t st;
    pixhawk_link_get_status(&st);
    printf("\n=== Pixhawk Link Status ===\n");
    printf("  Pixhawk: armed=%s mode=%s (%lu)\n",
           st.pixhawk_armed ? "YES" : "no",
           rover_mode_name(st.pixhawk_custom_mode),
           (unsigned long)st.pixhawk_custom_mode);
    printf("  Anchor : %s",
           st.anchor_valid ? "valid" : "INVALID");
    if (st.anchor_valid) printf(" age=%lld ms", (long long)st.anchor_age_ms);
    printf("\n");
    printf("  Offset : %s\n", st.offset_valid ? "valid" : "INVALID");
    if (st.target_lat_e7 || st.target_lon_e7) {
        printf("  Target : %.7f, %.7f\n",
               st.target_lat_e7 / 1e7, st.target_lon_e7 / 1e7);
    }
    printf("  Counters: tx_hb=%lu rx_hb=%lu targets=%lu\n\n",
           (unsigned long)st.heartbeats_sent,
           (unsigned long)st.heartbeats_rx,
           (unsigned long)st.targets_sent);
    return 0;
}

static int cmd_px_stop(int argc, char **argv)
{
    (void)argc; (void)argv;
    pixhawk_link_emergency_stop();
    printf("Sent HOLD + DISARM\n");
    return 0;
}

void pixhawk_link_register_commands(void)
{
    const esp_console_cmd_t status_cmd = {
        .command = "px_status",
        .help    = "Show Pixhawk link status",
        .hint    = NULL,
        .func    = &cmd_px_status,
    };
    const esp_console_cmd_t stop_cmd = {
        .command = "px_stop",
        .help    = "Force Pixhawk HOLD and disarm",
        .hint    = NULL,
        .func    = &cmd_px_stop,
    };
    esp_console_cmd_register(&status_cmd);
    esp_console_cmd_register(&stop_cmd);
}
