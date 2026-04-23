---
name: Planned Jetson layout restructure for git-based deploy
description: User wants to eventually restructure the Jetson so the repo layout matches /home/mayra/..., enabling `git pull` + restart as the deploy flow instead of push-to-jetson.sh. Not a priority.
type: project
---

User wants to eventually replace the scp-based `push-to-jetson.sh` deploy flow with a git-based one: clone the repo onto the Jetson, then deploy = `git pull && systemctl --user restart <units>`.

**Why:** simpler deploys, exact commit tracking on the Jetson, systemd unit pushes get covered for free (current script doesn't handle them).

**How to apply:** not a priority — only tackle this if the user brings it up again or asks about improving the deploy flow. The migration involves:
1. Decide on a single source-of-truth path on the Jetson (e.g. clone at `~/AquaBot-src`) and either move the install dirs or symlink them.
2. Update systemd units to point at the new paths.
3. Replace `push-to-jetson.sh` with a pull+restart wrapper (or retire it entirely).

Current Jetson paths (as of 2026-04-23) vs. repo paths:
- Repo `jetson/app.py` → Jetson `~/AquaBotGUI_WebRTC/app.py`
- Repo `jetson/webrtc_sender.py` → Jetson `~/webrtc_jetson.py` (note the rename)
- Repo `jetson/mavproxy_launcher.py` → Jetson `~/mavproxy_launcher.py`
- Repo `jetson/templates/`, `jetson/static/` → under `~/AquaBotGUI_WebRTC/`
- Repo `jetson/systemd/*.service` → Jetson `~/.config/systemd/user/*.service`
