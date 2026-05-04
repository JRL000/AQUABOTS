---
name: pixhawk_link follower drone module (2026-05-03, shipped + pushed)
description: New ESP-IDF module on the ESP32 firmware that drives a directly-attached Pixhawk via MAVLink for demo follower hulls without a Jetson. Same binary on every node, role-gated by NVS flag has_jetson. Code-complete + clean build, no hardware test yet.
type: project
---

Closes the swarm formation loop on follower hulls that don't carry a
Jetson. Before today, the ESP32 stack computed where each follower
should go but had no path to actually drive the Pixhawk on a Jetsonless
hull. Now it does.

**Why:** John's demo ships a stripped-down follower configuration
(ESP32 + Pixhawk only) for cost. Production architecture has Jetsons
on every hull driving the Pixhawks themselves; the ESP32 only does
swarm coordination there. One firmware build covers both — runtime
NVS flag picks the role.

**How to apply:** When touching swarm/formation/Pixhawk behavior,
read this first → `Claude/session-logs/2026-05-03.md` → the actual
code. The flow is:

  Leader Jetson broadcasts GPS_ANCHOR via ESP-NOW
    → follower swarm_transport delivers to pixhawk_link callback
    → pixhawk_link caches anchor
    → formation.c assigns this follower its (x, y) offset
    → on_position_assigned → pixhawk_link_set_offset
    → pixhawk_link's TX task: SET_MODE GUIDED → ARM →
      SET_POSITION_TARGET_GLOBAL_INT to local Pixhawk
    → Pixhawk navigates there

## What was added

- `firmware/main/pixhawk_link.{c,h}` — UART2 MAVLink bridge, two
  FreeRTOS tasks (RX parser + TX sequencer), anchor stale watchdog,
  emergency stop hook, console commands.
- `firmware/main/mav_min.{c,h}` — minimal MAVLink v2 wire format
  encoder/decoder for HEARTBEAT, SET_MODE, COMMAND_LONG (arm),
  SET_POSITION_TARGET_GLOBAL_INT, plus inbound HEARTBEAT parser.
  Hand-rolled — pulling in the full MAVLink C library is hundreds
  of files for four messages.
- `firmware/main/latlon_offset.h` — header-only port of
  `jetson/swarm_coordinator.py:offset_to_latlon`. Same flat-earth
  math as the Jetson side so leader and followers agree on geometry.
- `firmware/main/node_config.{c,h}` — added persistent `has_jetson`
  flag (NVS key `has_jetson`, default `true`). Console: `set_jetson
  <0|1>`. Surfaced in existing `info` output.
- `firmware/main/sensor_bridge.c` — added active EZO pH polling
  (`R\r` per cycle) and Jetsonless-mode CSV log line:
  `SLOG,<ms>,<ph>,<tds_ppm>,<temp_c>` matching Jamie's
  `Sensor_DataLog.py` column order.

## Pre-existing fix folded in

`swarm_bridge.c` called `membership_get_count()` without including
`membership.h`. Newer IDF toolchain (v5.5.2) rejected the implicit
declaration that older versions tolerated. Fixed in passing.

## Pin map for demo followers

```
ESP32 GPIO 38 (TX) -> Pixhawk TELEM1 RX
ESP32 GPIO 39 (RX) -> Pixhawk TELEM1 TX
GND                -> GND
57600 baud, MAVLink2  (Pixhawk SERIAL2 defaults — no Pixhawk reconfig)
```

Chosen specifically to stay clear of every other peripheral the
firmware uses (sensor_bridge pH UART on GPIO 16/17, ultrasonic on
GPIO 17, console / Jetson UART on GPIO 43/44, ADC on GPIO 1, 1-Wire
on GPIO 4, native USB on GPIO 19/20).

## Per-hull provisioning recipe

```
set_node_id <N>       # 1..254, unique per hull
set_jetson 0          # demo follower hulls only; production = default 1
<press reset>
```

Both flags persist in NVS, survive reboots and re-flashes (until you
explicitly `nvs erase` or change the partition table).

## Build verification

Clean `idf.py build` against native IDF v5.5.2 on Windows (Python
3.11 venv). No physical flash test yet. **Definitely needs**
bench-Pixhawk verification before it goes near a boat.

## Known issue, NOT fixed today

`gps_anchor_payload_t.heading_cdeg` is `int16_t`, overflows for
headings 327.68°..359.99°. `pixhawk_link.c::recover_heading_deg`
does an opportunistic recovery. Real fix is to change the protocol
struct to `uint16_t` (both ends). Out of scope for the demo push.

## Demo-only scope

`pixhawk_link` is gated `if (!node_config_has_jetson())`. On
production / leader hulls (`has_jetson=1`, the default) it is
not initialised, not started, and its console commands are not
registered — the Jetson talks to the Pixhawk directly there, and
two MAVLink masters on one UART would conflict.

## Sensor logging integration

`Sensor_DataLog.py` is Jamie's MicroPython script. Cannot be flashed
alongside ESP-IDF (different runtimes). Useful behaviors ported into
`sensor_bridge.c`:

- Active EZO pH polling each cycle (`R\r`).
- Jamie's CSV column order on Jetsonless hulls (`SLOG,<ms>,<ph>,
  <tds_ppm>,<temp_c>`) emitted alongside the existing Jetson-bound
  TEMP:/SAL:/PH: format.

The .py file stays at the repo root as Jamie's reference; not used
at runtime.
