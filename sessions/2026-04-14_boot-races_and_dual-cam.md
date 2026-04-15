# 2026-04-14 Session — boot-race hardening + dual-camera overlay

## TL;DR
Three threads of work today, all on branch `auto-nav-test`:
1. **Camera I2C probe failure (`imx219 -121`)** → traced to a physically broken FPC clamp on the Jetson carrier's port A. Wedging the ribbon got it to bind; any power cycle typically dislodges it.
2. **Intermittent GUI-at-boot failures** → code review turned up 8 ranked suspects, top 4 fixed in a single commit (signaling connect retry, Pixhawk heartbeat timeout, GStreamer state check, ESP32 serial retry, telemetry-ready gate).
3. **Dual-camera device tree overlay** → flashed via `config-by-hardware.py` so both carrier CSI ports are declared (`sensor-id=0` = port A, `sensor-id=1` = port C). Port C has a working clamp and is now the intended primary.

## Key findings
- `-121` = `EREMOTEIO`: the IMX219's I2C address was addressed and got no ACK → physical contact failure, always hardware.
- Before today's DT flash, only `module0` was declared in the Jetson device tree. Setting `sensor-id=1` in userspace was a no-op (returned "No cameras available" from argus) regardless of which physical connector the ribbon was in.
- The boot-race pattern in the Jetson code is "open a resource synchronously at import time with no retry, relying on systemd ordering for readiness that systemd doesn't actually guarantee." Present in: Pixhawk heartbeat wait, signaling connect, ESP32 serial, Flask-vs-WS-port race. All four now retry / gate properly.
- User systemd units cannot reliably `After=` system units (like `nvargus-daemon`). Code-level retries cover the gap.

## Branch state at session end
```
(HEAD -> auto-nav-test)
  ae27XXX  Jetson: harden boot-time races so GUI loads on first try   (committed)
  ae27XXX  webrtc: fix async-with after awaited websockets.connect()   (committed)
(auto-nav)
  ad168b7  Camera: switch nvarguscamerasrc to sensor-id=0              (committed)
(origin/auto-nav)
  5015c15  Sensor bridge end-to-end + slow mode + RTH-stuck fix        (pulled from remote)
```

Uncommitted local diff at session end: `jetson/webrtc_sender.py` with `sensor-id=1` (vs committed `sensor-id=0`). Deliberately not committed — the dual-cam overlay + port-C ribbon hadn't been end-to-end verified when the session paused.

## Deployed Jetson state at session end
- `/boot/extlinux/extlinux.conf`: points at `tegra234-p3767-camera-p3768-imx219-dual.dtbo` (was `imx219-A.dtbo`).
  - Backup preserved: `/boot/extlinux/extlinux.conf.backup-20260414-180040`.
- `/home/mayra/webrtc_jetson.py`: boot-race fixes + `sensor-id=1`.
- `/home/mayra/AquaBotGUI_WebRTC/app.py`: telemetry-ready gate + ESP32 retry.
- `~/.config/systemd/user/webrtc.service`: `Wants=signaling.service` added.

## Known unknown (next session starts here)
After the DT flash and power-cycle, the Jetson did not return to the tailnet within ~3 min polling (>18 attempts failed). Unclear whether the dual overlay caused a boot issue, or if the tail was re-establishing slowly, or if there was an unrelated power/USB/ribbon issue. Next session should:
1. Verify Jetson is physically powered and HDMI-visible (or tail responding).
2. If stuck: power off, reattach HDMI, inspect boot messages; if needed, restore `/boot/extlinux/extlinux.conf.backup-20260414-180040` from a bootable recovery path.
3. If boots: run the verification block below.

## Verification block (copy/paste when SSH is back)
```bash
ssh mayra@100.76.1.26 "
  echo '=== device tree modules ==='; ls /proc/device-tree/tegra-camera-platform/modules/
  echo '=== imx219 probes ==='; sudo dmesg | grep -iE 'imx219' | tail -20
  echo '=== video nodes ==='; ls /dev/video*
  echo '=== services ==='; for u in signaling mavproxy webrtc aquabot-app; do printf '%-15s %s\n' \$u \$(systemctl --user is-active \$u); done
  echo '=== webrtc log ==='; tail -20 /tmp/webrtc.log
  echo '=== dashboard ==='; curl -sf -o /dev/null -w 'HTTP %{http_code}\n' http://127.0.0.1:5000
"
```
Expected on success: `module0` AND `module1` listed; one `imx219 N-0010 bound` line (for the port that has the ribbon); `/dev/video0` present; dashboard returns HTTP 200.

## Rollback cheat sheet
- **Roll back to pre-boot-race-fix code:** `git checkout auto-nav && bash ./push-to-jetson.sh all`
- **Roll back to single-cam overlay:** `ssh mayra@100.76.1.26 "sudo /opt/nvidia/jetson-io/config-by-hardware.py -n 2='Camera IMX219-A' && sudo reboot"`
- **Nuclear revert of extlinux:** `ssh mayra@100.76.1.26 "sudo cp /boot/extlinux/extlinux.conf.backup-20260414-180040 /boot/extlinux/extlinux.conf && sudo reboot"`

## Open hardware issue
- Port A FPC clamp physically broken. Captured in memory `hardware_camera_clamp.md`. Fix tiers: Kapton tape (quick) → foam pressure plate (durable) → connector replacement or carrier swap (permanent).
