---
name: Jetson systemd user-service topology
description: All four AquaBot services are systemd --user units under /home/mayra/.config/systemd/user; cross-scope ordering to system units (nvargus-daemon etc.) is not enforceable, so code-level retries handle boot races.
type: reference
originSessionId: 6350b94f-1a52-4fc2-ae1f-71e82b0851d6
---
The four AquaBot services on the Jetson are all **user-scope** systemd units, not system-scope:

| Unit | Script (Jetson path) | Purpose |
|---|---|---|
| `signaling.service` | `~/AquaBotGUI_WebRTC/signaling_server.py` | WebRTC signaling on ws:8765 |
| `mavproxy.service` | `~/mavproxy_launcher.py` | Pixhawk UART → UDP:14552 router |
| `aquabot-app.service` | `~/AquaBotGUI_WebRTC/app.py` | Flask dashboard on :5000 + telemetry/control WS on :8766/:8770 |
| `webrtc.service` | `~/webrtc_jetson.py` | GStreamer capture + aiortc sender |

Unit files live at `/home/mayra/.config/systemd/user/*.service` on the Jetson and are mirrored in the repo at `jetson/systemd/`. Manage via `systemctl --user <verb> <unit>`.

**Key constraint:** user units can `After=` / `Wants=` other user units, but **cannot reliably order against system units** like `nvargus-daemon.service`. Do not try to add `After=nvargus-daemon.service` to user services — it's ignored by the user systemd manager. Use code-level retries (which `webrtc_sender.py` now has for both signaling connect and GStreamer state) to cover those races.

**Push workflow:** `bash ./push-to-jetson.sh <target>` from the repo root. Targets: `webrtc`, `app`, `signaling`, `mavproxy`, `ui`, `all`. The script scps the file, restarts the user unit, and tails 30 log lines. Note the file-name rename: the repo's `webrtc_sender.py` lands on the Jetson as `webrtc_jetson.py` (the systemd unit points at the Jetson-side name).

**Systemd unit pushes are NOT covered by push-to-jetson.sh.** If a `.service` file changes, scp it manually to `~/.config/systemd/user/<unit>.service` and run `systemctl --user daemon-reload`.
