/**
 * pixhawk_link.h
 *
 * MAVLink bridge between this ESP32 and a directly-attached Pixhawk over
 * UART. Used on demo follower hulls that don't carry a Jetson — the ESP32
 * substitutes for the missing companion computer.
 *
 * Lifecycle:
 *
 *   pixhawk_link_init()   sets up UART2 to the Pixhawk and the local state
 *                         (parser, target cache).
 *
 *   pixhawk_link_start()  starts the background tasks (RX parser, 1 Hz
 *                         heartbeat, command sequencer) and registers the
 *                         ESP-NOW receive callback for MSG_TYPE_GPS_ANCHOR.
 *
 * Inputs that drive the boat:
 *
 *   pixhawk_link_set_offset(pos, node_index)
 *       Called from main.c's on_position_assigned() callback when the
 *       formation module assigns this boat a new offset. Cached locally;
 *       combined with the latest GPS_ANCHOR to compute a target lat/lon.
 *
 *   (ESP-NOW MSG_TYPE_GPS_ANCHOR receive)
 *       Wired internally — populates the leader-GPS cache.
 *
 * Outputs to the Pixhawk:
 *
 *   - HEARTBEAT every 1 Hz so the Pixhawk keeps us as a connected GCS.
 *   - On first valid (anchor + offset) pair: SET_MODE → GUIDED, then
 *     COMMAND_LONG → ARM, then SET_POSITION_TARGET_GLOBAL_INT.
 *   - On subsequent updates: only SET_POSITION_TARGET_GLOBAL_INT, rate-
 *     limited to PIXHAWK_LINK_TARGET_MIN_PERIOD_MS.
 *
 * Safety:
 *
 *   - If GPS_ANCHOR is older than PIXHAWK_LINK_ANCHOR_STALE_MS, we stop
 *     issuing position targets and switch the Pixhawk to HOLD.
 *
 *   - pixhawk_link_emergency_stop() is the public hook for CMD_STOP from
 *     the swarm leader. Called from main.c's on_command_received().
 *
 * Role gating:
 *
 *   This module should only be initialised on Jetson-less follower hulls.
 *   main.c queries node_config_has_jetson() and skips init when true.
 */

#ifndef PIXHAWK_LINK_H
#define PIXHAWK_LINK_H

#include "esp_err.h"
#include "formation.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// ============================================================================
// PIN / UART CONFIGURATION
// ============================================================================
//
// Pinned to UART_NUM_2 with TX=GPIO38, RX=GPIO39 — chosen to stay clear of
// every other peripheral in the firmware:
//
//   GPIO 1     ADC TDS                (sensor_bridge)
//   GPIO 4     1-Wire DS18B20         (sensor_bridge)
//   GPIO 16/17 UART1 pH EZO + A02YYUW (sensor_bridge / a02yyuw)
//   GPIO 19/20 native USB             (ESP32-S3)
//   GPIO 43/44 UART0 / Jetson / log   (sensor_bridge / console)
//
// Edit these defines if a follower hull's wiring differs.

#define PIXHAWK_LINK_UART_NUM        UART_NUM_2
#define PIXHAWK_LINK_UART_TX_GPIO    GPIO_NUM_38
#define PIXHAWK_LINK_UART_RX_GPIO    GPIO_NUM_39
#define PIXHAWK_LINK_UART_BAUD       57600
#define PIXHAWK_LINK_UART_BUF_SIZE   1024

// ============================================================================
// TIMING / SAFETY
// ============================================================================

#define PIXHAWK_LINK_HEARTBEAT_MS         1000
#define PIXHAWK_LINK_TARGET_MIN_PERIOD_MS 500     // don't spam Pixhawk
#define PIXHAWK_LINK_ANCHOR_STALE_MS      5000    // stop after this long w/o leader
#define PIXHAWK_LINK_MODE_RETRY_MS        2000    // retry SET_MODE if not in GUIDED
#define PIXHAWK_LINK_ARM_RETRY_MS         2000    // retry ARM if not armed

// ============================================================================
// MAVLink IDS
// ============================================================================

/**
 * Target Pixhawk MAVLink IDs. ArduPilot defaults: SYSID 1, COMPID 1.
 * Override at compile time via -D if a hull uses different IDs.
 */
#ifndef PIXHAWK_LINK_TARGET_SYSID
#define PIXHAWK_LINK_TARGET_SYSID    1
#endif
#ifndef PIXHAWK_LINK_TARGET_COMPID
#define PIXHAWK_LINK_TARGET_COMPID   1
#endif

/**
 * Our (ESP32) MAVLink IDs. Each follower gets a unique sysid so MAVProxy
 * logs on a future Jetson-equipped leader stay clean. compid 190 = the
 * "GCS" half of the GCS pair convention — same as the original baby drone
 * sketch.
 */
#define PIXHAWK_LINK_SELF_SYSID_BASE 200
#define PIXHAWK_LINK_SELF_COMPID     190

// ============================================================================
// PUBLIC API
// ============================================================================

/**
 * Initialise UART2 to the Pixhawk + local state. Idempotent.
 *
 * Safe to call before swarm_transport_init() — UART setup only.
 */
esp_err_t pixhawk_link_init(void);

/**
 * Start the background tasks (heartbeat, RX parser, command sequencer)
 * and register the MSG_TYPE_GPS_ANCHOR receive handler.
 *
 * swarm_transport_init() and node_config_init() must have run first.
 */
esp_err_t pixhawk_link_start(void);

/**
 * Cache the latest formation offset assigned to this boat. Combined with
 * the latest GPS_ANCHOR to produce a target lat/lon for the Pixhawk.
 *
 * Called from main.c's on_position_assigned() callback.
 */
void pixhawk_link_set_offset(const formation_position_t *pos, int node_index);

/**
 * Emergency stop — switch the Pixhawk to HOLD mode and disarm. Safe to
 * call multiple times; idempotent. Called from main.c's
 * on_command_received() when CMD_STOP arrives from the leader.
 */
void pixhawk_link_emergency_stop(void);

/**
 * Diagnostic snapshot for the console.
 */
typedef struct {
    bool     pixhawk_armed;
    uint32_t pixhawk_custom_mode;
    bool     anchor_valid;
    int64_t  anchor_age_ms;
    bool     offset_valid;
    int32_t  target_lat_e7;
    int32_t  target_lon_e7;
    uint32_t targets_sent;
    uint32_t heartbeats_sent;
    uint32_t heartbeats_rx;
} pixhawk_link_status_t;

void pixhawk_link_get_status(pixhawk_link_status_t *out);

/**
 * Register console commands ('px_status' etc.). Call from main.c after
 * the console is up.
 */
void pixhawk_link_register_commands(void);

#ifdef __cplusplus
}
#endif

#endif // PIXHAWK_LINK_H
