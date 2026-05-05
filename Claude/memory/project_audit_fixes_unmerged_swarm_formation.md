---
name: Audit fixes from 2026-04-30/05-01 are unmerged on `swarm-formation` branch
description: A batch of correctness fixes (firmware UART migration to fix silently-dropped swarm transport, arm_vehicle COMMAND_ACK plumbing, GUI watchdog removal, EMI guide updates) is sitting on branch `swarm-formation` at commit `c5c401b` and has NOT been merged into `main`. Production / demo builds should reflect them eventually.
type: project
---
**TL;DR — `swarm-formation` ↔ `main` need a merge eventually.** Not blocking the 2026-05-03 pixhawk_link demo flash, but the fixes are real and shouldn't be lost.

## What's on `swarm-formation` that isn't on `main`

Three commits, all pushed to GitHub:

| Commit | Summary |
|---|---|
| `d160aa7` | GUI cleanup: removed misleading 8 s `cmdStartMission` watchdog (was firing the wrong "Mode did not switch to AUTO" message before the server's 30 s HOME wait could resolve). Also moved `swarm_coordinator.py` import to module top, switched `webrtc_sender.py` MAVLink source from non-existent `/dev/ttyACM0` to `udpin:127.0.0.1:14553`, deleted the duplicate "AQUABOTS POWER SYSTEM CHANGELOG.md" stub. |
| `65c2ebb` | Major fix: swarm-bridge transport between ESP32 and Jetson was silently dropping all SWARM_* messages. Firmware was calling `uart_*_bytes` on `UART_NUM_0`, but `sensor_bridge` intentionally doesn't install a driver on UART_NUM_0 (it conflicts with the IDF console). `sensor_bridge` had a `fwrite(stdout)` fallback for TEMP/SAL/PH that worked; `swarm_bridge` had no equivalent. Moved `SENSOR_BRIDGE_JETSON_UART_NUM` to `UART_NUM_2` on GPIO 5 (TX) / GPIO 6 (RX). Both `sensor_bridge` and `swarm_bridge` now use the standard UART driver. **Required hardware action**: rewire ESP32 GPIO 5/6 → Jetson 40-pin header `/dev/ttyTHS2` (JST-SH 4-pin). Same commit also makes `arm_vehicle()` / `disarm_vehicle()` poll the `armed` global to verify the autopilot accepted the command, surfaces ArduPilot's STATUSTEXT as the failure reason, and disables the A02YYUW obstacle sensor (no free hardware UART left). |
| `c5c401b` | Documentation for the above: power changelog 2026-05-01 entry, EMI install guide § "S2 / IF-3 specifics", session log narrative, CHANGES_FOR_MAYRA. |

## Why these aren't on `main` yet

- `main` has been the working branch for the 2026-05-03 pixhawk_link demo work, which moves fast and is hardware-test-driven.
- The audit fixes need a **physical rewire** (ESP32 GPIO 5/6 → Jetson ttyTHS2) before they can be verified on a real boat. Merging without verification means master could be in a state where swarm formation is broken on the production hardware until the wiring catches up.
- The 05-03 PC session was working purely on follower-drone integration (`pixhawk_link`) which doesn't touch the swarm-bridge serial path — so the audit fixes weren't urgent for that work.

## Conflicts to expect when merging

`main` has touched several of the same files since the merge base (`5efd2fa`):

- `firmware/main/main.c` — both branches modified the obstacle-sensor section + post-init callback wiring. Hand-merge.
- `firmware/main/sensor_bridge.h` — `swarm-formation` moved `SENSOR_BRIDGE_JETSON_UART_NUM` to `UART_NUM_2`; `main` still has it at `UART_NUM_0`. The audit-fix value is correct *only* on hardware that's been rewired, so this conflict resolution depends on whether the wiring is done.
- `jetson/app.py` — both branches edited `arm_vehicle` / `disarm_vehicle` and surrounding handlers.
- `jetson/static/js/controls.js` — `swarm-formation` removed the 8 s watchdog, `main` still has it. Audit-fix version is unambiguously better; take it.
- `jetson/static/js/safety.js` — battery thresholds were 6S on `swarm-formation`; `main` still has the original 3S numbers. Audit-fix version is correct for the actual pack chemistry; take it.
- `jetson/CHANGES_FOR_MAYRA.md`, `jetson/swarm_coordinator.py`, `jetson/webrtc_sender.py` — minor changes; review per-file.
- `Claude/project-docs/AQUABOTS_POWER_SYSTEM_CHANGELOG.md`, `Claude/project-docs/AQUABOTS_EMI_INSTALL_GUIDE.md`, `Claude/project-docs/AQUABOTS_WIRING_GUIDE.md` — `swarm-formation` has 2026-04-30/05-01 entries; `main` has WG-2 corrections. Keep both.

## How to apply

When the user is ready to merge:

1. Verify `swarm-formation` audit fixes are still desired (re-read its session logs `Claude/session-logs/2026-04-30.md` and `2026-05-01.md`).
2. Verify the ESP32→Jetson rewire is done (or will be done before any swarm-formation deploy on real hardware).
3. `git checkout main && git merge swarm-formation` — expect conflicts on the files above. Resolve with the audit-fix version of the JS thresholds + GUI watchdog removal; coordinate the firmware UART change with the hardware wiring state.
4. Test build, push.

Skipping the merge means the production `main` build silently drops swarm-formation messages forever and arms the vehicle without verifying the autopilot accepted the command. Both real, both bad. Just not blocking today's flash session.
