/**
 * mav_min.h
 *
 * Minimal MAVLink v2 encoder/decoder for the four messages we need to drive
 * an ArduPilot Rover Pixhawk over UART:
 *
 *   Outbound:
 *     HEARTBEAT                        (msgid 0)
 *     SET_MODE                         (msgid 11)
 *     COMMAND_LONG                     (msgid 76)
 *     SET_POSITION_TARGET_GLOBAL_INT   (msgid 86)
 *
 *   Inbound (parser):
 *     HEARTBEAT — used to track Pixhawk arm state and current flight mode.
 *     All other messages are accepted by the parser but not interpreted.
 *
 * This module exists because pulling the entire MAVLink C library into the
 * IDF build is overkill for four message types. We hand-roll the wire format
 * (well-defined at https://mavlink.io/en/guide/serialization.html) so the
 * firmware stays small and auditable.
 *
 * Wire format (MAVLink v2, no signing):
 *
 *   STX(0xFD) LEN INC_FLG CMP_FLG SEQ SYSID COMPID MSGID[3] PAYLOAD[LEN] CRC[2]
 *
 *   - LEN reflects the truncated payload (trailing zero bytes stripped).
 *   - CRC = X.25 over (LEN..PAYLOAD_END) then one extra byte per-message
 *     (CRC_EXTRA, fixed value computed from the message definition).
 */

#ifndef MAV_MIN_H
#define MAV_MIN_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

// ============================================================================
// CONSTANTS — only what we need
// ============================================================================

#define MAV_MIN_STX_V2                 0xFD
#define MAV_MIN_HEADER_LEN             10      // STX..MSGID[3]
#define MAV_MIN_CRC_LEN                2
#define MAV_MIN_MAX_PAYLOAD            255
#define MAV_MIN_MAX_FRAME              (MAV_MIN_HEADER_LEN + MAV_MIN_MAX_PAYLOAD + MAV_MIN_CRC_LEN)

// ArduPilot Rover custom mode values (from ArduPilot source).
#define MAV_ROVER_MODE_MANUAL          0
#define MAV_ROVER_MODE_HOLD            4
#define MAV_ROVER_MODE_AUTO            10
#define MAV_ROVER_MODE_RTL             11
#define MAV_ROVER_MODE_SMART_RTL       12
#define MAV_ROVER_MODE_GUIDED          15
#define MAV_ROVER_MODE_INITIALIZING    16

// MAV_MODE_FLAG bits (subset).
#define MAV_MODE_FLAG_CUSTOM_MODE_ENABLED  0x01
#define MAV_MODE_FLAG_SAFETY_ARMED         0x80

// MAV_TYPE values.
#define MAV_TYPE_GCS                   6
#define MAV_AUTOPILOT_INVALID          8
#define MAV_STATE_ACTIVE               4

// MAV_CMD values used.
#define MAV_CMD_COMPONENT_ARM_DISARM   400

// Message IDs.
#define MAVLINK_MSG_ID_HEARTBEAT                       0
#define MAVLINK_MSG_ID_SET_MODE                        11
#define MAVLINK_MSG_ID_COMMAND_LONG                    76
#define MAVLINK_MSG_ID_SET_POSITION_TARGET_GLOBAL_INT  86

// MAV_FRAME values (subset).
#define MAV_FRAME_GLOBAL_RELATIVE_ALT_INT              6

// POSITION_TARGET_TYPEMASK (position only — ignore vel/accel/yaw).
// Bits set = "ignore". Bits 0..2 are pos x/y/z; clearing them = use position.
#define MAV_POS_TARGET_MASK_POS_ONLY  0x0DF8

// ============================================================================
// OUTBOUND ENCODERS
// ============================================================================
// All return the number of bytes written into out (frame size). out must be
// at least MAV_MIN_MAX_FRAME bytes.
//
// seq is the MAVLink sequence number (caller maintains a counter).
// sysid/compid identify this transmitter (ours, not the Pixhawk's).

/** Build a HEARTBEAT frame. */
size_t mav_min_pack_heartbeat(uint8_t *out, uint8_t seq,
                              uint8_t sysid, uint8_t compid);

/** Build a SET_MODE frame targeting the Pixhawk (target_sysid). */
size_t mav_min_pack_set_mode(uint8_t *out, uint8_t seq,
                             uint8_t sysid, uint8_t compid,
                             uint8_t target_sysid,
                             uint32_t custom_mode);

/** Build a COMMAND_LONG ARM/DISARM frame targeting the Pixhawk. */
size_t mav_min_pack_arm(uint8_t *out, uint8_t seq,
                        uint8_t sysid, uint8_t compid,
                        uint8_t target_sysid, uint8_t target_compid,
                        bool arm);

/** Build a SET_POSITION_TARGET_GLOBAL_INT frame. lat/lon as 1e7-scaled ints. */
size_t mav_min_pack_position_target(uint8_t *out, uint8_t seq,
                                    uint8_t sysid, uint8_t compid,
                                    uint8_t target_sysid, uint8_t target_compid,
                                    uint32_t time_boot_ms,
                                    int32_t lat_e7, int32_t lon_e7);

// ============================================================================
// INBOUND PARSER
// ============================================================================

typedef enum {
    MAV_MIN_RX_IDLE = 0,
    MAV_MIN_RX_LEN,
    MAV_MIN_RX_HDR,
    MAV_MIN_RX_PAYLOAD,
    MAV_MIN_RX_CRC,
} mav_min_rx_state_t;

typedef struct {
    mav_min_rx_state_t state;
    uint8_t buf[MAV_MIN_MAX_FRAME];
    size_t  pos;
    size_t  payload_len;
} mav_min_parser_t;

typedef struct {
    uint32_t msgid;
    uint8_t  sysid;
    uint8_t  compid;
    uint8_t  payload_len;
    const uint8_t *payload;  // points inside parser buffer; valid until next parse step
} mav_min_msg_t;

/** Reset/initialise a parser. */
void mav_min_parser_reset(mav_min_parser_t *p);

/**
 * Feed one byte into the parser. Returns true exactly once when a complete,
 * CRC-valid frame has been assembled, populating *out. The pointer in
 * out->payload is valid until the next call to this function.
 */
bool mav_min_parse_byte(mav_min_parser_t *p, uint8_t b, mav_min_msg_t *out);

// ============================================================================
// HEARTBEAT DECODE
// ============================================================================
//
// Helper for the one inbound message we actually interpret.

typedef struct {
    uint32_t custom_mode;
    uint8_t  type;
    uint8_t  autopilot;
    uint8_t  base_mode;
    uint8_t  system_status;
    uint8_t  mavlink_version;
} mav_min_heartbeat_t;

/**
 * Decode a HEARTBEAT payload. Returns true on success. Pads missing trailing
 * bytes with zeros (MAVLink v2 truncation rule).
 */
bool mav_min_decode_heartbeat(const mav_min_msg_t *msg, mav_min_heartbeat_t *out);

#ifdef __cplusplus
}
#endif

#endif // MAV_MIN_H
