/**
 * latlon_offset.h
 *
 * Convert a formation offset (x, y in mm relative to the leader, with the
 * leader's heading defining the local coordinate frame) into an absolute
 * latitude/longitude.
 *
 * Coordinate frame matches firmware/main/formation.c and the Python
 * reference at jetson/swarm_coordinator.py:offset_to_latlon():
 *
 *     +Y_form = forward (the direction the leader is facing)
 *     +X_form = right of the leader
 *     heading_offset_deg = degrees clockwise from leader heading
 *
 * Earth frame:
 *
 *     +north, +east
 *
 * Heading convention: degrees clockwise from north, in the range [0, 360).
 *
 * Math is a small-angle flat-earth approximation. Adequate for tens to
 * hundreds of meters at temperate latitudes — the boats operate at pond
 * scale, so this is fine.
 */

#ifndef LATLON_OFFSET_H
#define LATLON_OFFSET_H

#include <math.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#define LATLON_EARTH_M_PER_DEG 111111.0

/**
 * Combine an anchor lat/lon (1e7 ints, matching MAVLink GLOBAL_INT
 * convention) plus a leader heading (degrees, floating point — already
 * range-recovered from any int16 wrap by the caller) plus a formation
 * offset (mm) into a target lat/lon (1e7 ints) and target heading
 * (centi-degrees).
 *
 * out_target_heading_cdeg may be NULL if the caller doesn't care.
 */
static inline void latlon_offset_apply(int32_t anchor_lat_e7,
                                       int32_t anchor_lon_e7,
                                       double  leader_heading_deg,
                                       int32_t offset_x_mm,
                                       int32_t offset_y_mm,
                                       int16_t heading_offset_deg,
                                       int32_t *out_target_lat_e7,
                                       int32_t *out_target_lon_e7,
                                       int16_t *out_target_heading_cdeg)
{
    double leader_lat       = anchor_lat_e7 / 1e7;
    double leader_lon       = anchor_lon_e7 / 1e7;
    double leader_heading_d = leader_heading_deg;
    double h_rad            = leader_heading_d * (M_PI / 180.0);

    /* Heading is degrees clockwise from north. In (north, east) coords:
     *   forward unit = (cos H,  sin H)
     *   right   unit = forward rotated 90° clockwise = (-sin H, cos H)
     * World pos = offset_y * forward + offset_x * right. */
    double sinh = sin(h_rad);
    double cosh = cos(h_rad);
    double north_m = ((double)offset_y_mm * cosh - (double)offset_x_mm * sinh) / 1000.0;
    double east_m  = ((double)offset_y_mm * sinh + (double)offset_x_mm * cosh) / 1000.0;

    double cos_lat = cos(leader_lat * (M_PI / 180.0));
    if (cos_lat < 1e-6) cos_lat = 1e-6;

    double delta_lat = north_m / LATLON_EARTH_M_PER_DEG;
    double delta_lon = east_m  / (LATLON_EARTH_M_PER_DEG * cos_lat);

    double target_lat = leader_lat + delta_lat;
    double target_lon = leader_lon + delta_lon;

    if (out_target_lat_e7) *out_target_lat_e7 = (int32_t)(target_lat * 1e7);
    if (out_target_lon_e7) *out_target_lon_e7 = (int32_t)(target_lon * 1e7);

    if (out_target_heading_cdeg) {
        double target_h = leader_heading_d + (double)heading_offset_deg;
        while (target_h < 0)        target_h += 360.0;
        while (target_h >= 360.0)   target_h -= 360.0;
        *out_target_heading_cdeg = (int16_t)(target_h * 100.0);
    }
}

#ifdef __cplusplus
}
#endif

#endif // LATLON_OFFSET_H
