"""
Serial protocol between the Jetson and the on-board ESP32 swarm node.

Carried over the existing sensor_bridge UART (the same line that delivers
TEMP/SAL/PH). Lines are ASCII, tag-prefixed, comma-separated key=value,
newline-terminated:

    <TAG>:<key>=<val>,<key>=<val>,...\n

The Jetson dispatches by tag prefix. The legacy TEMP: line keeps working.

Mirror of firmware/main/swarm_bridge.h — keep the constants in sync.
"""

# ---------------------------------------------------------------------------
# Tags (ESP32 -> Jetson)
# ---------------------------------------------------------------------------
TAG_ROLE       = "SWARM_ROLE"        # role + leader_id + members [+ my_index]
TAG_TARGET     = "SWARM_TARGET"      # x_mm, y_mm, h(deg), seq
TAG_LEADER_GPS = "SWARM_LEADER_GPS"  # lat, lon, h, age_ms (formation center)
TAG_FORMATION  = "SWARM_FORMATION"   # type, spacing, nodes
TAG_STOP       = "SWARM_STOP"        # reason

# ---------------------------------------------------------------------------
# Tags (Jetson -> ESP32)
# ---------------------------------------------------------------------------
TAG_ANCHOR_GPS = "ANCHOR_GPS"        # lat, lon, h, fix, t
TAG_SET_FORM   = "SET_FORMATION"     # type, spacing
TAG_ENABLE     = "SWARM_ENABLE"      # on (0 or 1)


# All inbound (ESP32 -> Jetson) tags the coordinator listens for.
INBOUND_TAGS = (TAG_ROLE, TAG_TARGET, TAG_LEADER_GPS, TAG_FORMATION, TAG_STOP)

_ALL_TAGS = INBOUND_TAGS + (TAG_ANCHOR_GPS, TAG_SET_FORM, TAG_ENABLE)


def parse_line(line: str):
    """
    Parse a single newline-stripped line.

    Returns (tag, fields_dict) on a recognized swarm-bridge line, or
    (None, None) on anything else (sensor TEMP line, blank line, garbage).

    Values are returned as strings; the caller converts.
    """
    if not line or ":" not in line:
        return None, None

    tag, _, body = line.partition(":")
    if tag not in _ALL_TAGS:
        return None, None

    fields = {}
    for piece in body.split(","):
        piece = piece.strip()
        if not piece or "=" not in piece:
            continue
        k, _, v = piece.partition("=")
        fields[k.strip()] = v.strip()
    return tag, fields


def encode_anchor_gps(lat: float, lon: float, heading_deg: float,
                      fix_type: int, t_unix: int) -> str:
    return (f"{TAG_ANCHOR_GPS}:lat={lat:.7f},lon={lon:.7f},"
            f"h={heading_deg:.1f},fix={int(fix_type)},t={int(t_unix)}\n")


def encode_set_formation(pattern: str, spacing_mm: int) -> str:
    return f"{TAG_SET_FORM}:type={pattern},spacing={int(spacing_mm)}\n"


def encode_enable(on: bool) -> str:
    return f"{TAG_ENABLE}:on={1 if on else 0}\n"
