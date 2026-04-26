/**
 * swarm_bridge.h
 *
 * Serial protocol between the ESP32 swarm node and the Jetson companion
 * computer on the same boat. Carried over the existing sensor_bridge UART
 * (115200 baud, 8N1).
 *
 * Format: ASCII line, tag-prefixed, comma-separated key=value pairs,
 *         newline-terminated.
 *
 *     <TAG>:<key>=<val>,<key>=<val>,...\n
 *
 * Coexists with the legacy "TEMP:23.45,SAL:0.324,PH:7.12" sensor line —
 * the Jetson dispatches by tag prefix.
 *
 * Direction: ESP32 -> Jetson
 *
 *   SWARM_ROLE:role=leader,leader_id=2,members=3
 *   SWARM_ROLE:role=follower,leader_id=2,members=3,my_index=1
 *       Sent on role/membership change.
 *
 *   SWARM_TARGET:x=2000,y=-1500,h=45,seq=42
 *       Formation position offset for THIS boat, relative to formation
 *       center. x/y in millimeters, h (heading offset) in degrees.
 *       seq increments per assignment for Jetson-side dedup.
 *
 *   SWARM_LEADER_GPS:lat=33.4252,lon=-111.9398,h=87.5,age_ms=500
 *       Leader's GPS as received via ESP-NOW (the formation center).
 *       Re-emitted at 1 Hz as long as the radio link is up.
 *       age_ms = milliseconds since the last MSG_TYPE_GPS_ANCHOR was
 *       received over the radio.
 *
 *   SWARM_FORMATION:type=wedge,spacing=2000,nodes=3
 *       Informational. Sent on formation type / spacing / count change.
 *
 *   SWARM_STOP:reason=collision
 *   SWARM_STOP:reason=manual
 *       Leader said emergency stop. Jetson should switch Pixhawk to HOLD.
 *
 * Direction: Jetson -> ESP32
 *
 *   ANCHOR_GPS:lat=33.4252,lon=-111.9398,h=87.5,fix=3,t=1714200000
 *       This boat's current GPS read from Pixhawk. Sent at 1 Hz.
 *       If this boat is the leader, ESP32 rebroadcasts as MSG_TYPE_GPS_ANCHOR
 *       over ESP-NOW so followers know the formation center.
 *       fix: 0=no fix, 2=2D, 3=3D, 4=DGPS, 5+=RTK
 *
 *   SET_FORMATION:type=wedge,spacing=2000
 *       User selected a pattern in the GUI. Forwarded to ESP32; if this
 *       boat is the leader, ESP32 broadcasts new formation_config to swarm.
 *       type ∈ {none, line, wedge, circle, column}
 *       spacing in millimeters (500..10000)
 *
 *   SWARM_ENABLE:on=1
 *   SWARM_ENABLE:on=0
 *       User toggled Start/Exit Swarm Mode. ESP32 starts/stops participating
 *       in formation assignments.
 */

#ifndef SWARM_BRIDGE_H
#define SWARM_BRIDGE_H

#include "esp_err.h"
#include <stdint.h>
#include <stdbool.h>

// ============================================================================
// LINE TAGS
// ============================================================================

#define SWARM_BRIDGE_TAG_ROLE        "SWARM_ROLE"
#define SWARM_BRIDGE_TAG_TARGET      "SWARM_TARGET"
#define SWARM_BRIDGE_TAG_LEADER_GPS  "SWARM_LEADER_GPS"
#define SWARM_BRIDGE_TAG_FORMATION   "SWARM_FORMATION"
#define SWARM_BRIDGE_TAG_STOP        "SWARM_STOP"

#define SWARM_BRIDGE_TAG_ANCHOR_GPS  "ANCHOR_GPS"
#define SWARM_BRIDGE_TAG_SET_FORM    "SET_FORMATION"
#define SWARM_BRIDGE_TAG_ENABLE      "SWARM_ENABLE"

// ============================================================================
// LIMITS
// ============================================================================

#define SWARM_BRIDGE_MAX_LINE_LEN    256

// ============================================================================
// PUBLIC API
// ============================================================================

/**
 * Initialize the swarm-bridge module. Reuses the existing sensor_bridge
 * Jetson UART — sensor_bridge_init() must be called first.
 */
esp_err_t swarm_bridge_init(void);

/**
 * Start the background UART RX task that reads inbound lines from the
 * Jetson (ANCHOR_GPS / SET_FORMATION / SWARM_ENABLE). Also registers the
 * MSG_TYPE_GPS_ANCHOR receive handler with swarm_transport.
 */
esp_err_t swarm_bridge_start(void);

// ============================================================================
// NOTIFY HOOKS
// ============================================================================
//
// Called from main.c's existing callback handlers (so logging in main.c
// continues to work AND the bridge gets the same events). Each hook
// formats the corresponding outbound line and writes it to the Jetson.

#include "command_engine.h"
#include "formation.h"

/** Call from on_leader_changed() in main.c. */
void swarm_bridge_notify_role(uint16_t leader_id, bool is_self,
                              int my_index, int member_count);

/** Call from on_formation_changed() in main.c. */
void swarm_bridge_notify_formation(const formation_config_t *config);

/** Call from on_position_assigned() in main.c. */
void swarm_bridge_notify_position(const formation_position_t *pos, int node_index);

/** Call from on_command_received() in main.c. Returns the value the
 *  callback should return (always true; provided for ergonomics). */
bool swarm_bridge_notify_command(const swarm_command_t *command);

#endif // SWARM_BRIDGE_H
