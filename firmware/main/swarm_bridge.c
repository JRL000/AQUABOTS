/**
 * swarm_bridge.c
 *
 * ESP32 side of the Jetson <-> ESP32 swarm protocol. See swarm_bridge.h
 * for line format and tag list.
 */

#include "swarm_bridge.h"
#include "swarm_protocol.h"
#include "swarm_transport.h"
#include "sensor_bridge.h"
#include "leader_election.h"
#include "node_config.h"
#include "formation.h"
#include "command_engine.h"
#include "esp_log.h"
#include "driver/uart.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_timer.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <ctype.h>

static const char *TAG = "SWARM_BRIDGE";

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

static bool s_running = false;
static bool s_swarm_enabled = false;     // toggled by SWARM_ENABLE line

// Latest leader GPS as RECEIVED via radio (from the leader's broadcast).
// For a follower, this drives the SWARM_LEADER_GPS line emitted to the
// Jetson at 1 Hz.
static struct {
    bool     valid;
    int32_t  lat_e7;
    int32_t  lon_e7;
    int16_t  heading_cdeg;
    int64_t  received_at_us;
} s_leader_gps;

// Latest local-boat GPS as REPORTED by the Jetson (ANCHOR_GPS line).
// For a leader, this drives the periodic MSG_TYPE_GPS_ANCHOR broadcast.
static struct {
    bool     valid;
    int32_t  lat_e7;
    int32_t  lon_e7;
    int16_t  heading_cdeg;
    uint8_t  fix_type;
    int64_t  received_at_us;
} s_my_gps;

// ---------------------------------------------------------------------------
// UART helpers (we share the Jetson UART with sensor_bridge)
// ---------------------------------------------------------------------------

static void tx_line(const char *line)
{
    uart_write_bytes(SENSOR_BRIDGE_JETSON_UART_NUM, line, strlen(line));
}

static void emit_role_line(void)
{
    uint16_t my_id = node_config_get_node_id();
    uint16_t leader_id = leader_election_get_leader();
    bool is_leader = leader_election_is_leader();
    int members = membership_get_count() + 1;
    char buf[128];
    if (is_leader) {
        snprintf(buf, sizeof(buf),
                 "%s:role=leader,leader_id=%u,members=%d\n",
                 SWARM_BRIDGE_TAG_ROLE, my_id, members);
    } else {
        snprintf(buf, sizeof(buf),
                 "%s:role=follower,leader_id=%u,members=%d,my_index=%d\n",
                 SWARM_BRIDGE_TAG_ROLE, leader_id, members,
                 formation_get_my_index());
    }
    tx_line(buf);
}

// ---------------------------------------------------------------------------
// Public notify hooks (called from main.c's existing callback handlers)
// ---------------------------------------------------------------------------

void swarm_bridge_notify_role(uint16_t leader_id, bool is_self,
                              int my_index, int member_count)
{
    char buf[128];
    if (is_self) {
        snprintf(buf, sizeof(buf),
                 "%s:role=leader,leader_id=%u,members=%d\n",
                 SWARM_BRIDGE_TAG_ROLE, leader_id, member_count);
    } else {
        snprintf(buf, sizeof(buf),
                 "%s:role=follower,leader_id=%u,members=%d,my_index=%d\n",
                 SWARM_BRIDGE_TAG_ROLE, leader_id, member_count, my_index);
    }
    tx_line(buf);
}

void swarm_bridge_notify_formation(const formation_config_t *config)
{
    if (!config) return;
    char buf[128];
    snprintf(buf, sizeof(buf),
             "%s:type=%s,spacing=%ld,nodes=%d\n",
             SWARM_BRIDGE_TAG_FORMATION,
             formation_type_to_string(config->type),
             (long)config->spacing_mm,
             config->node_count);
    tx_line(buf);
}

void swarm_bridge_notify_position(const formation_position_t *pos, int node_index)
{
    if (!pos) return;
    static uint32_t seq = 0;
    seq++;
    char buf[128];
    snprintf(buf, sizeof(buf),
             "%s:x=%ld,y=%ld,h=%d,seq=%lu\n",
             SWARM_BRIDGE_TAG_TARGET,
             (long)pos->x_mm, (long)pos->y_mm,
             pos->heading_deg, (unsigned long)seq);
    tx_line(buf);
}

bool swarm_bridge_notify_command(const swarm_command_t *command)
{
    if (!command) return true;
    if (command->cmd_type == CMD_STOP) {
        char buf[64];
        snprintf(buf, sizeof(buf), "%s:reason=leader_cmd\n", SWARM_BRIDGE_TAG_STOP);
        tx_line(buf);
    }
    return true;
}

// ---------------------------------------------------------------------------
// Inbound line parser (Jetson -> ESP32)
// ---------------------------------------------------------------------------

static const char *find_field(const char *body, const char *key)
{
    /* Returns pointer to value char just after "key=" inside body, or NULL.
     * Body looks like "k1=v1,k2=v2,..." */
    size_t klen = strlen(key);
    const char *p = body;
    while (p && *p) {
        const char *eq = strchr(p, '=');
        if (!eq) return NULL;
        if ((size_t)(eq - p) == klen && strncmp(p, key, klen) == 0) {
            return eq + 1;
        }
        const char *comma = strchr(p, ',');
        if (!comma) return NULL;
        p = comma + 1;
    }
    return NULL;
}

static long parse_long(const char *s) { return s ? strtol(s, NULL, 10) : 0; }
static double parse_double(const char *s) { return s ? strtod(s, NULL) : 0.0; }

static void handle_anchor_gps(const char *body)
{
    /* Jetson reports our boat's current GPS. Stash it; if we're the leader
     * we'll broadcast it as MSG_TYPE_GPS_ANCHOR on the next tick. */
    double lat = parse_double(find_field(body, "lat"));
    double lon = parse_double(find_field(body, "lon"));
    double h = parse_double(find_field(body, "h"));
    long fix = parse_long(find_field(body, "fix"));

    s_my_gps.lat_e7 = (int32_t)(lat * 1e7);
    s_my_gps.lon_e7 = (int32_t)(lon * 1e7);
    s_my_gps.heading_cdeg = (int16_t)(h * 100.0);
    s_my_gps.fix_type = (uint8_t)fix;
    s_my_gps.received_at_us = esp_timer_get_time();
    s_my_gps.valid = true;
}

static void handle_set_formation(const char *body)
{
    const char *type_v = find_field(body, "type");
    const char *spacing_v = find_field(body, "spacing");
    if (!type_v) return;

    /* find_field returns a pointer into body; we need a NUL-terminated copy. */
    char tbuf[16] = {0};
    size_t i = 0;
    while (type_v[i] && type_v[i] != ',' && i < sizeof(tbuf) - 1) {
        tbuf[i] = type_v[i]; i++;
    }
    formation_type_t t = formation_type_from_string(tbuf);
    if (t != FORMATION_NONE || strcmp(tbuf, "none") == 0) {
        formation_set_type(t);  // silently fails if not leader; that's fine
    }
    if (spacing_v) {
        long s = parse_long(spacing_v);
        if (s >= 500 && s <= 10000) {
            formation_set_spacing((int32_t)s);
        }
    }
}

static void handle_swarm_enable(const char *body)
{
    long on = parse_long(find_field(body, "on"));
    s_swarm_enabled = (on != 0);
    ESP_LOGI(TAG, "swarm participation %s", s_swarm_enabled ? "ENABLED" : "DISABLED");
    /* Re-emit role + formation so the Jetson sees fresh state immediately. */
    emit_role_line();
    formation_config_t cfg;
    if (formation_get_config(&cfg) == ESP_OK) {
        swarm_bridge_notify_formation(&cfg);
    }
}

static void process_line(char *line)
{
    if (!line || !*line) return;
    char *colon = strchr(line, ':');
    if (!colon) return;
    *colon = '\0';
    const char *tag = line;
    const char *body = colon + 1;

    if      (strcmp(tag, SWARM_BRIDGE_TAG_ANCHOR_GPS) == 0) handle_anchor_gps(body);
    else if (strcmp(tag, SWARM_BRIDGE_TAG_SET_FORM)   == 0) handle_set_formation(body);
    else if (strcmp(tag, SWARM_BRIDGE_TAG_ENABLE)     == 0) handle_swarm_enable(body);
    /* Other tags (ESP32->Jetson types) are ignored if echoed back. */
}

// ---------------------------------------------------------------------------
// Background tasks
// ---------------------------------------------------------------------------

static void rx_task(void *arg)
{
    char line[SWARM_BRIDGE_MAX_LINE_LEN];
    size_t len = 0;
    uint8_t byte;

    while (s_running) {
        int n = uart_read_bytes(SENSOR_BRIDGE_JETSON_UART_NUM, &byte, 1,
                                pdMS_TO_TICKS(100));
        if (n <= 0) continue;
        if (byte == '\r') continue;
        if (byte == '\n') {
            line[len] = '\0';
            process_line(line);
            len = 0;
            continue;
        }
        if (len < sizeof(line) - 1) {
            line[len++] = (char)byte;
        } else {
            len = 0;  // overflow — drop the line
        }
    }
    vTaskDelete(NULL);
}

static void anchor_tx_task(void *arg)
{
    /* Leader: every second, broadcast our GPS over ESP-NOW so followers
     * have a fresh formation center.
     * Follower: every second, emit SWARM_LEADER_GPS to the Jetson with the
     * latest leader GPS we received over the radio.
     */
    while (s_running) {
        bool is_leader = leader_election_is_leader();

        if (s_swarm_enabled && is_leader && s_my_gps.valid) {
            gps_anchor_payload_t payload = {
                .lat_e7       = s_my_gps.lat_e7,
                .lon_e7       = s_my_gps.lon_e7,
                .heading_cdeg = s_my_gps.heading_cdeg,
                .fix_type     = s_my_gps.fix_type,
                .reserved     = 0,
                .leader_t_ms  = (uint32_t)(esp_timer_get_time() / 1000),
            };

            swarm_header_t hdr = {
                .swarm_id    = 0,
                .src_id      = node_config_get_node_id(),
                .dst_id      = SWARM_BROADCAST_ADDR,
                .group_id    = 0,
                .msg_type    = MSG_TYPE_GPS_ANCHOR,
                .seq         = 0,
                .flags       = 0,
                .payload_len = sizeof(payload),
            };

            uint8_t pkt[sizeof(hdr) + sizeof(payload)];
            memcpy(pkt, &hdr, sizeof(hdr));
            memcpy(pkt + sizeof(hdr), &payload, sizeof(payload));
            uint8_t bcast[6] = {0xFF,0xFF,0xFF,0xFF,0xFF,0xFF};
            swarm_transport_send(bcast, pkt, sizeof(pkt));
        }

        if (s_swarm_enabled && !is_leader && s_leader_gps.valid) {
            int64_t age_us = esp_timer_get_time() - s_leader_gps.received_at_us;
            char buf[160];
            snprintf(buf, sizeof(buf),
                     "%s:lat=%.7f,lon=%.7f,h=%.1f,age_ms=%lld\n",
                     SWARM_BRIDGE_TAG_LEADER_GPS,
                     s_leader_gps.lat_e7 / 1e7,
                     s_leader_gps.lon_e7 / 1e7,
                     s_leader_gps.heading_cdeg / 100.0,
                     (long long)(age_us / 1000));
            tx_line(buf);
        }

        vTaskDelay(pdMS_TO_TICKS(1000));
    }
    vTaskDelete(NULL);
}

// ---------------------------------------------------------------------------
// MSG_TYPE_GPS_ANCHOR receive handler (from peers via ESP-NOW)
// ---------------------------------------------------------------------------

static void on_radio_recv(const uint8_t *src_mac, const uint8_t *data,
                          int len, int8_t rssi)
{
    if (len < (int)sizeof(swarm_header_t)) return;
    swarm_header_t hdr;
    memcpy(&hdr, data, sizeof(hdr));
    if (hdr.msg_type != MSG_TYPE_GPS_ANCHOR) return;
    if (len < (int)(sizeof(swarm_header_t) + sizeof(gps_anchor_payload_t))) return;

    /* Only accept anchors from the elected leader. */
    if (hdr.src_id != leader_election_get_leader()) return;

    gps_anchor_payload_t payload;
    memcpy(&payload, data + sizeof(hdr), sizeof(payload));

    s_leader_gps.lat_e7        = payload.lat_e7;
    s_leader_gps.lon_e7        = payload.lon_e7;
    s_leader_gps.heading_cdeg  = payload.heading_cdeg;
    s_leader_gps.received_at_us = esp_timer_get_time();
    s_leader_gps.valid         = true;
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

esp_err_t swarm_bridge_init(void)
{
    memset(&s_leader_gps, 0, sizeof(s_leader_gps));
    memset(&s_my_gps, 0, sizeof(s_my_gps));
    ESP_LOGI(TAG, "initialized");
    return ESP_OK;
}

esp_err_t swarm_bridge_start(void)
{
    if (s_running) return ESP_OK;
    s_running = true;

    swarm_transport_register_recv_cb(on_radio_recv);

    xTaskCreate(rx_task,        "swarm_br_rx",  4096, NULL, 4, NULL);
    xTaskCreate(anchor_tx_task, "swarm_br_tx",  4096, NULL, 4, NULL);
    ESP_LOGI(TAG, "started (rx + anchor tasks)");
    return ESP_OK;
}
