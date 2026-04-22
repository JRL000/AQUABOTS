# Claude Code Prompt — AquaBots Auto-Nav Integration Test (04-10-2026)

Paste this as your first message to Claude Code after launching in `C:\Users\johnr\AQUABOTS_GitHub`.

---

## STATUS (04-11-2026) — historical artifact

This prompt kicked off the 04-10-2026 auto-nav integration session. The work it describes is **done**:

- **Jetson ↔ Pixhawk MAVLink link:** mavproxy owns `/dev/ttyACM0`, app.py reads UDP 14552, QGC connects over Tailscale to UDP 14550. All four Jetson services (`mavproxy`, `aquabot-app`, `signaling`, `webrtc`) run as systemd user units and auto-start on boot.
- **Ground-station control path (Option A):** QGC → Tailscale → Jetson → mavproxy → Pixhawk. Verified from off-site network.
- **Waypoint mission upload:** full MAVLink mission protocol in `jetson/app.py`. 7-phase state machine in `jetson/static/js/controls.js`. GO / HOLD / RTH / RESUME / ABORT all wired.
- **Bench-verified 04-10-2026 and 04-11-2026:** motor spins on arm+throttle, rudder responds, waypoints upload, state machine transitions cleanly, GPS lock, live telemetry, STATUSTEXT forwarded to browser.
- **Water test still outstanding.** Blocking item: Pixhawk EKF is flagging compass variance — compass calibration spin required before AUTO mode will engage. Tracked in `memory/project_compass_issue.md`.

The prompt body below is preserved as the original intent / success criteria for the session. For the current state of the code, see:

- `Claude/session-logs/04-10-2026_to_04-11-2026.md` — full play-by-play
- `jetson/README.md` — architecture overview
- `jetson/CHANGES_FOR_MAYRA.md` — every modification made to Mayra's files
- `Claude/project-docs/CLAUDE_CODE_HANDOFF.md` — closed-out audit

---

Read `CLAUDE_CODE_HANDOFF.md` in this repo for full project context (Jetson specs, SSH access, Mayra's DO_NOT_UPGRADE camera rules, etc.) before doing anything. Those rules are ABSOLUTE and non-negotiable.

## Today's primary goal

**Get the AquaBot ready for its first auto-navigation water test, WITHOUT SENSORS in this test.** By end of day I want to put the boat in water, connect it to Starlink, send it a waypoint from a ground station, and have it autonomously navigate there via Pixhawk ArduPilot Rover mode.

This is a motion/navigation test, not a sensor test. Sensor ingestion (pH/TDS/temp via ESP32) is explicitly out of scope today.

## What's already done and verified

- **Power system:** Mounted and working. Battery → cutoff switch → fuses → busbars → ATO fuse box → Pixhawk + ESC. Verified last night: ESC calibrated via QGroundControl, motor responds to `servo3_trim` changes. Pixhawk boots and accepts commands over USB/telemetry.
- **Baseplate:** Busbars, cutoff switch, ATO fuse box, 5V+12V buck converters are drilled and mounted on the aluminum plate. Plate is cut and fitted to hull (currently disassembled for work but will go back in).
- **Pixhawk:** ArduPilot firmware, configured for Rover mode. ESC calibrated. Motor known working via manual stick input.
- **Jetson access:** passwordless SSH via key to `mayra@100.76.1.26` (Tailscale, works from anywhere). Full backup at `C:\Users\johnr\Documents\AQUABOTS\jetson_backups\`. Code discovery partially started (see handoff doc).
- **Starlink Mini:** On the team, verified working from earlier tests. Not yet integrated into the hull for this test.

## What still needs to happen today

1. **Physical reassembly.** Plate back in hull. Jetson, Pixhawk, Starlink, BEC temporarily mounted (zip ties / double-sided tape OK for this test — we don't need to drill mounts today). Servo on hull, verified moving under Pixhawk command.

2. **Pixhawk ↔ Jetson MAVLink link (IF-3).** This is the critical software piece. The Jetson needs to talk to the Pixhawk over serial/USB using MAVLink. Standard options:
   - `mavproxy` as a router
   - `pymavlink` for direct Python control
   - `mavlink-router` if we want multi-endpoint (Jetson → Pixhawk + Jetson → ground station simultaneously)
   
   **Task for Claude Code:** SSH into the Jetson, check what's already installed (`which mavproxy`, `pip show pymavlink` in the existing venv, check `aquabot/` directory for any MAVLink code). Report back before installing anything.

3. **Ground station control path.** Decide and configure how commands get from a ground station (my laptop) to the drone:
   - **Option A:** QGroundControl on laptop → Starlink → Jetson → USB/serial → Pixhawk (standard MAVLink-over-UDP setup)
   - **Option B:** QGC directly to Pixhawk via telemetry radio (no Jetson involved). Simpler but doesn't prove the Jetson integration path.
   
   I want **Option A** because this test is also supposed to validate the Jetson as the comms hub.

4. **Waypoint mission test.** Configure a simple mission in QGC (one waypoint 20m from start, return home, disarm). Verify the Pixhawk receives and executes it. Dry test on land first (motor on a stand or very low throttle), then water test.

5. **Safety gating.** Because **EMI filtering is NOT YET INSTALLED** (all parts on hand but not soldered in), extended motor testing is risky. Keep motor runtime minimal — long enough to validate nav but not long enough to thermally stress anything or generate sustained ESC noise that could corrupt signals. **Don't** skip this — it's an explicit rule from the power system changelog.

## Constraints and rules

- Follow ALL camera/NVIDIA rules from `CLAUDE_CODE_HANDOFF.md` — no `apt upgrade`, no `pip install opencv-python`, no JetPack changes, no nvidia-* touches. Camera is not needed for this test but the Jetson must not be broken.
- Before installing anything on the Jetson, tell me what you want to install and why. I'd rather spend 30 seconds approving than 2 hours debugging a broken camera stack.
- If you find existing MAVLink code on the Jetson (in `aquabot/` or elsewhere), USE IT instead of writing from scratch. Mayra and Jamie may have already set this up.
- Sensor code (`esp32_sensor_reader.py`, `sensor_reader.py`, the `TEMP:/SAL:/PH:` ingestion question from the handoff doc) is **deferred** — not today's focus. If you find answers passively, note them, but don't go hunting.
- If something feels like scope creep, tell me. I'd rather ship a working nav test than a half-finished everything.

## Expected deliverables by end of session

1. Documented Jetson ↔ Pixhawk MAVLink link — a short script or command that establishes the connection and logs telemetry.
2. QGC on laptop → Starlink → Jetson → Pixhawk path verified end-to-end (at minimum: laptop can see Pixhawk telemetry and arm/disarm).
3. Successful dry-land waypoint mission test.
4. Go/no-go decision on the water test.
5. Brief notes in the repo about what worked, what didn't, and what's deferred.

## First steps (do these in order)

1. Read `CLAUDE_CODE_HANDOFF.md` completely. Confirm you understand the camera constraints.
2. SSH into the Jetson (`ssh mayra@100.76.1.26` — passwordless).
3. Check: is there already any MAVLink or Pixhawk-related code in `/home/mayra/aquabot/` or anywhere else in `/home/mayra/`? Run a focused search:
   ```bash
   grep -rIl --include="*.py" -E "mavlink|pymavlink|mavproxy|MAVLink" /home/mayra 2>/dev/null
   ```
4. Check what's installed: `which mavproxy`, `ls ~/venv/bin/ 2>/dev/null | grep -i mav`, and if there's a venv, activate it and `pip list | grep -i mav`.
5. Report findings before proceeding. If MAVLink tooling already exists on the Jetson, we use it. If not, we discuss what to install.

Do not install anything in step 4. Just discovery. We decide next actions together after step 5.

## Working preferences

- Concise but informative
- Push back on bad ideas and scope creep
- One meaningful step at a time for troubleshooting — don't stack 5 commands into one if any could fail
- PowerShell syntax for local Windows commands; bash for Jetson commands
- When in doubt about anything touching the camera stack or nvidia packages: STOP and ask
