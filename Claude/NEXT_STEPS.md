# NEXT STEPS — flash 3 boards (1 main, 2 followers)

**For the laptop session.** Use the ESP-IDF terminal (the standalone "ESP-IDF
PowerShell" or "ESP-IDF Command Prompt" shortcut from the IDF install). NOT
VS Code.

The PC session (2026-05-03) already wrote and committed the firmware. Your
job: flash 3 boards and provision each one.

## 0. Pre-flight

From the ESP-IDF terminal, sync the repo and confirm the firmware builds
on the laptop's IDF install:

```
cd <path-to-AQUABOTS_GitHub>
git pull
cd firmware
idf.py set-target esp32s3        # only needed if a fresh checkout
idf.py build
```

If the build is already current and clean (it should be — PC pushed a
clean build at commit `5e87fd5` or later) you'll get "Project build
complete" fast.

## 1. Identify each board's COM port

Plug in one board at a time. After plugging, run:

```
idf.py -p ?
```

Or just look at the new entry in Device Manager (Windows). Note the COM
port (e.g., `COM7`).

Repeat for all 3 boards. Suggest labeling them physically (sticky note
or marker) as you go: **main**, **follower-1**, **follower-2**.

## 2. Flash + provision each board

For each board, the cycle is:

```
idf.py -p COM<N> flash monitor
```

Wait for boot logs to settle and the `swarm>` prompt to appear. Then
type the provisioning commands for that role.

### Board: **main drone** (the one with the Jetson)

```
swarm> set_node_id 3
swarm> info
```

`info` should show `Node ID: 3`, `Has Jetson: YES (production / leader hull)`.
Press the physical reset button on the board.

`has_jetson` defaults to true so no `set_jetson` command needed for the
main drone. Node ID 3 is intentional — leader election picks the highest
node_id, so the main drone wins and stays leader.

Exit the monitor with `Ctrl+]`.

### Board: **follower-1**

```
swarm> set_node_id 1
swarm> set_jetson 0
swarm> info
```

`info` should show `Node ID: 1`, `Has Jetson: no (demo follower; pixhawk_link active)`.
Press the physical reset button.

Exit monitor with `Ctrl+]`.

### Board: **follower-2**

```
swarm> set_node_id 2
swarm> set_jetson 0
swarm> info
```

Same checks. Reset. Exit.

## 3. Verify each follower talks to its Pixhawk

Wire each follower's ESP32 to its Pixhawk (only do this AFTER flashing —
don't have the Pixhawk hooked up while flashing in case of UART contention):

```
ESP32 GPIO 38 (TX)  →  Pixhawk TELEM1 RX
ESP32 GPIO 39 (RX)  →  Pixhawk TELEM1 TX
GND                 →  GND
```

Power on the Pixhawk first, then power the ESP32. Reconnect the monitor:

```
idf.py -p COM<N> monitor
```

At the `swarm>` prompt, run:

```
swarm> px_status
```

Expected on a healthy follower:
- `Pixhawk: armed=no mode=MANUAL (0)` (or whatever mode the Pixhawk is in)
- `Counters: tx_hb=N rx_hb=M` — both should be ticking up. Heartbeat
  exchange is the proof of life.

If `rx_hb=0` after 10 seconds, check:
1. UART wiring (TX↔RX swap is the most common mistake)
2. Pixhawk TELEM1 baud rate. Default ArduPilot is 57600 + MAVLink2 on
   `SERIAL2`. If the Pixhawk has been customised, fix it in QGroundControl:
   `SERIAL2_BAUD = 57`, `SERIAL2_PROTOCOL = 2`.

Exit monitor with `Ctrl+]`.

## 4. Demo dry run (no water)

1. Power on all 3 boards (main + 2 followers) and the leader's Jetson.
2. Open the dashboard on the leader's Jetson (port 5000).
3. Click "Start Swarm Mode" in the GUI.
4. Followers should:
   - Show `anchor=valid` in `px_status`.
   - Switch their Pixhawks to GUIDED.
   - ARM their Pixhawks.
   - Start sending position targets.
5. **Don't put it in water yet** — for the first dry run, watch the
   wheels/motors twitch toward the assigned formation positions to
   confirm the loop is closed end-to-end.

## 5. If something goes wrong

- `idf.py monitor` shows live ESP32 logs. Watch for `PX_LINK` tag lines.
- `px_stop` from any follower's console forces HOLD + DISARM immediately
  on that boat.
- The leader's GUI "stop" button broadcasts `CMD_STOP` over radio;
  followers HOLD + DISARM on receipt.
- Re-flash any board at any time with `idf.py -p COM<N> flash monitor`.
  NVS-stored `node_id` and `has_jetson` survive re-flashes (unless you
  also `idf.py erase-flash`, which wipes them — only do that if you
  need to re-provision from scratch).

## State at handoff (from PC session 2026-05-03)

- All firmware committed and pushed to `main`.
- Last commit: `5e87fd5 firmware: pixhawk_link UART thread-safety fix +
  cleaner console init` (or later if anything came after).
- Build verified clean on PC's IDF v5.5.2 install. No flash test yet.

## Background reading (optional)

- `Claude/session-logs/2026-05-03.md` — full narrative of what was built
  and why.
- `Claude/memory/project_pixhawk_link_2026-05-03.md` — concise reference
  for the new firmware module.
- `firmware/main/pixhawk_link.h` — module API and pin map.
