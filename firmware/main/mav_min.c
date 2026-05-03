/**
 * mav_min.c
 *
 * Minimal MAVLink v2 wire format. See mav_min.h for the rationale.
 */

#include "mav_min.h"
#include <string.h>

// ============================================================================
// CRC-16/MCRF4XX (MAVLink "x.25") — copied verbatim from MAVLink helpers
// ============================================================================

static inline void crc_accumulate(uint8_t data, uint16_t *crc)
{
    uint8_t tmp = data ^ (uint8_t)(*crc & 0xFF);
    tmp ^= (tmp << 4);
    *crc = (*crc >> 8) ^ ((uint16_t)tmp << 8) ^ ((uint16_t)tmp << 3) ^ ((uint16_t)tmp >> 4);
}

static uint16_t crc_calc(const uint8_t *data, size_t len, uint8_t crc_extra)
{
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++) {
        crc_accumulate(data[i], &crc);
    }
    crc_accumulate(crc_extra, &crc);
    return crc;
}

// ============================================================================
// CRC_EXTRA values for the messages we touch (from MAVLink common.xml)
// ============================================================================

static uint8_t crc_extra_for(uint32_t msgid)
{
    switch (msgid) {
        case MAVLINK_MSG_ID_HEARTBEAT:                      return 50;
        case MAVLINK_MSG_ID_SET_MODE:                       return 89;
        case MAVLINK_MSG_ID_COMMAND_LONG:                   return 152;
        case MAVLINK_MSG_ID_SET_POSITION_TARGET_GLOBAL_INT: return 5;
        default:                                            return 0;
    }
}

// ============================================================================
// FRAME ASSEMBLY (with v2 trailing-zero truncation)
// ============================================================================

static size_t pack_frame(uint8_t *out, uint8_t seq,
                         uint8_t sysid, uint8_t compid,
                         uint32_t msgid, uint8_t crc_extra,
                         const uint8_t *payload, size_t payload_len)
{
    /* MAVLink v2 truncation: strip trailing zero bytes (min 1 byte). */
    while (payload_len > 1 && payload[payload_len - 1] == 0) {
        payload_len--;
    }

    out[0] = MAV_MIN_STX_V2;
    out[1] = (uint8_t)payload_len;
    out[2] = 0;             // incompat flags (no signing)
    out[3] = 0;             // compat flags
    out[4] = seq;
    out[5] = sysid;
    out[6] = compid;
    out[7] = (uint8_t)(msgid & 0xFF);
    out[8] = (uint8_t)((msgid >> 8) & 0xFF);
    out[9] = (uint8_t)((msgid >> 16) & 0xFF);
    if (payload_len > 0) {
        memcpy(&out[10], payload, payload_len);
    }

    /* CRC over LEN..end-of-payload (i.e., bytes [1..10+payload_len)). */
    uint16_t crc = crc_calc(&out[1], 9 + payload_len, crc_extra);

    out[10 + payload_len]     = (uint8_t)(crc & 0xFF);
    out[10 + payload_len + 1] = (uint8_t)((crc >> 8) & 0xFF);

    return 10 + payload_len + 2;
}

// ============================================================================
// PAYLOAD WRITERS — little-endian, packed, in MAVLink wire order
// ============================================================================

static void w_u16(uint8_t *p, size_t off, uint16_t v)
{
    p[off]     = (uint8_t)(v & 0xFF);
    p[off + 1] = (uint8_t)((v >> 8) & 0xFF);
}

static void w_u32(uint8_t *p, size_t off, uint32_t v)
{
    p[off]     = (uint8_t)(v & 0xFF);
    p[off + 1] = (uint8_t)((v >> 8) & 0xFF);
    p[off + 2] = (uint8_t)((v >> 16) & 0xFF);
    p[off + 3] = (uint8_t)((v >> 24) & 0xFF);
}

static void w_i32(uint8_t *p, size_t off, int32_t v)
{
    w_u32(p, off, (uint32_t)v);
}

static void w_f32(uint8_t *p, size_t off, float v)
{
    uint32_t u;
    memcpy(&u, &v, sizeof(u));
    w_u32(p, off, u);
}

// ============================================================================
// PUBLIC ENCODERS
// ============================================================================

size_t mav_min_pack_heartbeat(uint8_t *out, uint8_t seq,
                              uint8_t sysid, uint8_t compid)
{
    /* Wire order (9 bytes): custom_mode(u32), type(u8), autopilot(u8),
     * base_mode(u8), system_status(u8), mavlink_version(u8). */
    uint8_t p[9] = {0};
    w_u32(p, 0, 0);                  // custom_mode
    p[4] = MAV_TYPE_GCS;
    p[5] = MAV_AUTOPILOT_INVALID;
    p[6] = MAV_MODE_FLAG_CUSTOM_MODE_ENABLED;
    p[7] = MAV_STATE_ACTIVE;
    p[8] = 3;                        // mavlink_version
    return pack_frame(out, seq, sysid, compid,
                      MAVLINK_MSG_ID_HEARTBEAT,
                      crc_extra_for(MAVLINK_MSG_ID_HEARTBEAT),
                      p, sizeof(p));
}

size_t mav_min_pack_set_mode(uint8_t *out, uint8_t seq,
                             uint8_t sysid, uint8_t compid,
                             uint8_t target_sysid,
                             uint32_t custom_mode)
{
    /* Wire order (6 bytes): custom_mode(u32), target_system(u8), base_mode(u8). */
    uint8_t p[6] = {0};
    w_u32(p, 0, custom_mode);
    p[4] = target_sysid;
    p[5] = MAV_MODE_FLAG_CUSTOM_MODE_ENABLED;
    return pack_frame(out, seq, sysid, compid,
                      MAVLINK_MSG_ID_SET_MODE,
                      crc_extra_for(MAVLINK_MSG_ID_SET_MODE),
                      p, sizeof(p));
}

size_t mav_min_pack_arm(uint8_t *out, uint8_t seq,
                        uint8_t sysid, uint8_t compid,
                        uint8_t target_sysid, uint8_t target_compid,
                        bool arm)
{
    /* Wire order (33 bytes): param1..param7 (f32 each), command (u16),
     * target_system (u8), target_component (u8), confirmation (u8). */
    uint8_t p[33] = {0};
    w_f32(p, 0, arm ? 1.0f : 0.0f);  // param1
    /* params 2..7 left at 0.0f (already memset). */
    w_u16(p, 28, MAV_CMD_COMPONENT_ARM_DISARM);
    p[30] = target_sysid;
    p[31] = target_compid;
    p[32] = 0;                       // confirmation
    return pack_frame(out, seq, sysid, compid,
                      MAVLINK_MSG_ID_COMMAND_LONG,
                      crc_extra_for(MAVLINK_MSG_ID_COMMAND_LONG),
                      p, sizeof(p));
}

size_t mav_min_pack_position_target(uint8_t *out, uint8_t seq,
                                    uint8_t sysid, uint8_t compid,
                                    uint8_t target_sysid, uint8_t target_compid,
                                    uint32_t time_boot_ms,
                                    int32_t lat_e7, int32_t lon_e7)
{
    /* Wire order (53 bytes):
     *   time_boot_ms (u32)        @ 0
     *   lat_int      (i32)        @ 4
     *   lon_int      (i32)        @ 8
     *   alt          (f32)        @ 12
     *   vx, vy, vz   (f32 each)   @ 16, 20, 24
     *   afx, afy, afz(f32 each)   @ 28, 32, 36
     *   yaw, yaw_rate(f32 each)   @ 40, 44
     *   type_mask    (u16)        @ 48
     *   target_system(u8)         @ 50
     *   target_component(u8)      @ 51
     *   coordinate_frame(u8)      @ 52
     */
    uint8_t p[53] = {0};
    w_u32(p, 0, time_boot_ms);
    w_i32(p, 4, lat_e7);
    w_i32(p, 8, lon_e7);
    /* alt..yaw_rate left at 0 (Rover ignores altitude/velocity/yaw under
     * the position-only type mask). */
    w_u16(p, 48, MAV_POS_TARGET_MASK_POS_ONLY);
    p[50] = target_sysid;
    p[51] = target_compid;
    p[52] = MAV_FRAME_GLOBAL_RELATIVE_ALT_INT;
    return pack_frame(out, seq, sysid, compid,
                      MAVLINK_MSG_ID_SET_POSITION_TARGET_GLOBAL_INT,
                      crc_extra_for(MAVLINK_MSG_ID_SET_POSITION_TARGET_GLOBAL_INT),
                      p, sizeof(p));
}

// ============================================================================
// PARSER
// ============================================================================

void mav_min_parser_reset(mav_min_parser_t *p)
{
    p->state = MAV_MIN_RX_IDLE;
    p->pos = 0;
    p->payload_len = 0;
}

bool mav_min_parse_byte(mav_min_parser_t *p, uint8_t b, mav_min_msg_t *out)
{
    switch (p->state) {
        case MAV_MIN_RX_IDLE:
            if (b == MAV_MIN_STX_V2) {
                p->buf[0] = b;
                p->pos = 1;
                p->state = MAV_MIN_RX_LEN;
            }
            return false;

        case MAV_MIN_RX_LEN:
            p->buf[p->pos++] = b;
            p->payload_len = b;
            if (p->payload_len > MAV_MIN_MAX_PAYLOAD) {
                /* Bogus length — resync. */
                mav_min_parser_reset(p);
                return false;
            }
            p->state = MAV_MIN_RX_HDR;
            return false;

        case MAV_MIN_RX_HDR:
            p->buf[p->pos++] = b;
            if (p->pos == MAV_MIN_HEADER_LEN) {
                p->state = (p->payload_len == 0) ? MAV_MIN_RX_CRC : MAV_MIN_RX_PAYLOAD;
            }
            return false;

        case MAV_MIN_RX_PAYLOAD:
            p->buf[p->pos++] = b;
            if (p->pos == MAV_MIN_HEADER_LEN + p->payload_len) {
                p->state = MAV_MIN_RX_CRC;
            }
            return false;

        case MAV_MIN_RX_CRC:
            p->buf[p->pos++] = b;
            if (p->pos == MAV_MIN_HEADER_LEN + p->payload_len + MAV_MIN_CRC_LEN) {
                /* Frame complete — validate CRC. */
                uint32_t msgid = (uint32_t)p->buf[7]
                               | ((uint32_t)p->buf[8] << 8)
                               | ((uint32_t)p->buf[9] << 16);
                uint16_t expected = (uint16_t)p->buf[MAV_MIN_HEADER_LEN + p->payload_len]
                                  | ((uint16_t)p->buf[MAV_MIN_HEADER_LEN + p->payload_len + 1] << 8);
                uint16_t actual = crc_calc(&p->buf[1], 9 + p->payload_len,
                                           crc_extra_for(msgid));
                bool ok = (expected == actual);
                if (ok && out) {
                    out->msgid       = msgid;
                    out->sysid       = p->buf[5];
                    out->compid      = p->buf[6];
                    out->payload_len = (uint8_t)p->payload_len;
                    out->payload     = (p->payload_len > 0) ? &p->buf[MAV_MIN_HEADER_LEN] : NULL;
                }
                mav_min_parser_reset(p);
                return ok;
            }
            return false;
    }
    return false;
}

// ============================================================================
// HEARTBEAT DECODE
// ============================================================================

bool mav_min_decode_heartbeat(const mav_min_msg_t *msg, mav_min_heartbeat_t *out)
{
    if (!msg || msg->msgid != MAVLINK_MSG_ID_HEARTBEAT || !out) {
        return false;
    }
    /* Pad missing trailing bytes with zero (v2 truncation). */
    uint8_t buf[9] = {0};
    size_t copy = msg->payload_len <= sizeof(buf) ? msg->payload_len : sizeof(buf);
    if (msg->payload && copy > 0) {
        memcpy(buf, msg->payload, copy);
    }
    out->custom_mode     = (uint32_t)buf[0]
                         | ((uint32_t)buf[1] << 8)
                         | ((uint32_t)buf[2] << 16)
                         | ((uint32_t)buf[3] << 24);
    out->type            = buf[4];
    out->autopilot       = buf[5];
    out->base_mode       = buf[6];
    out->system_status   = buf[7];
    out->mavlink_version = buf[8];
    return true;
}
