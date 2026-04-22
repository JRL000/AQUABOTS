# Claude Code Handoff — AquaBots Jetson Code Audit

**Date:** 04-10-2026
**User:** John Lopez (AquaBots Team 26061, ENGR 498B Spring 2026, U of A)
**Role:** Software Integration Lead, Power System Design
**Working dir for Claude Code:** `C:\Users\johnr\AQUABOTS_GitHub`

---

## STATUS UPDATE (04-11-2026) — audit closed out

The critical unknown this doc was written to answer has been resolved. Summary so future readers don't have to re-run the investigation:

- **Does Jetson code parse the current `TEMP:/SAL:/PH:` CSV format?** YES. `jetson/app.py:read_esp32()` reads `/dev/ttyACM1` at 115200, parses `TEMP:xx.x,SAL:xx.x,PH:xx.x`, and publishes the values via the telemetry JSON broadcast every 3 s. This file is in the repo under `jetson/`.
- **ESP32-side implementation** exists as of 04-11-2026: `firmware/main/sensor_bridge.c/h` on the `auto-nav` branch. Pins and framing match Jamie's Arduino prototype. See `Claude/session-logs/04-10-2026_to_04-11-2026.md` for the build-out notes and `memory/project_sensor_bridge.md` for the summary.
- **Jetson code mirror to this repo:** done. The `jetson/` directory holds `app.py`, `mavlink_router.py`, `controls.js`, `templates/`, and the systemd units.
- **Camera pipeline constraint** in § 🚫 below is still live and non-negotiable. JetPack was NOT upgraded; the 6.2 breakage was worked around by replacing `cv2.VideoCapture` with PyGObject GStreamer (see `memory/project_camera_fix.md`).

The rest of this document is retained as the historical investigation plan — the "Next Steps" section below has been executed and the findings are the three bullets above.

---

## What we're doing (and why)

Auditing the software currently on Mayra's NVIDIA Jetson Orin Nano to understand:
1. **What code exists on it** (much of it is uncommitted, scattered in `/home/mayra/`)
2. **What that code does** (camera pipeline, WebRTC streaming, sensor ingestion, GUI server)
3. **Specifically: whether any code exists that parses the CURRENT ESP32 sensor firmware output** — this is the #1 unknown
4. **Push the source code to GitHub** once we understand it, so it's backed up and versioned

The Jetson is the central compute node for the ASV. It runs the camera pipeline (IMX219 → GStreamer → WebRTC → Starlink → ground station GUI) and is supposed to ingest sensor data from an ESP32 over USB serial (IF-3 in the block diagram).

---

## Jetson access — ALREADY SET UP

- **SSH:** `ssh mayra@100.76.1.26` (Tailscale IP, works over any network)
- **Auth:** SSH key already installed (`C:/Users/johnr/.ssh/id_ed25519`), no password needed
- **SSH config entry** already in `C:\Users\johnr\.ssh\config` for host `100.76.1.26`
- **User account:** `mayra` (the old `john` account was deleted)

Claude Code can SSH in directly from the terminal and run any discovery commands. No VS Code Remote-SSH needed — that was used in the previous session but Claude Code can bypass it.

---

## Jetson specs (memorized so you don't have to re-check)

- **Hostname:** `jetson-orin`
- **OS:** Ubuntu 22.04.5 LTS (ARM64, aarch64)
- **Kernel:** 5.15.148-tegra
- **JetPack:** 6.1 (L4T R36.4.7, Sept 2025)
- **Python:** numpy 1.23.5 (system, DO NOT upgrade), tensorrt 10.3.0, Jetson.GPIO 2.1.7
- **OpenCV:** NVIDIA apt-installed (NOT pip opencv-python — stays that way)
- **Camera:** IMX219 CSI via `nvargus` + GStreamer
- **Docker:** installed and running (possibly has containerized code)
- **`/home/mayra`:** 2.9 GB, already tarballed and backed up to `C:\Users\johnr\Documents\AQUABOTS\jetson_backups\home_mayra_backup.tar.gz`
- **`/home/mayra`** itself is a git repo on branch `main` (state of remote unknown)

---

## 🚫 ABSOLUTE CONSTRAINTS — DO NOT VIOLATE

Mayra wrote `~/DO_NOT_UPGRADE_CAMERA.md` on the Jetson. These rules are non-negotiable:

- **NEVER** `apt upgrade nvidia-*` packages
- **NEVER** `pip install opencv-python` (would break NVIDIA OpenCV ABI)
- **NEVER** remove `nvidia-opencv`
- **NEVER** upgrade JetPack
- **NEVER** touch OpenCV, GStreamer, JetPack, or camera drivers
- **NEVER** run `sudo apt upgrade` (pulls nvidia-* updates)
- **ONLY** use targeted `sudo apt install <specific-package>` if absolutely needed
- If unsure whether an action could affect the camera stack → DO NOT DO IT, ask John first

If anything in the camera pipeline breaks, the AquaBots project is blocked.

**Safe operations:** read any file, `cd` anywhere, `cat`/`grep`/`find`, git operations, create venvs, read logs, edit files in `/home/mayra/`.

---

## What we found so far in `/home/mayra/`

**Confirmed directories of interest:**
- `aquabot/` — likely the main package (NOT YET EXPLORED)
- `AquaBotGUI_WebRTC/` — Mayra's ground station GUI (modified/tracked)
- `AquaBotGUI_backup_2026-04-02_18-55/` — GUI backup
- `gstwebrtc-demos/` — GStreamer WebRTC reference code
- `webrtc_jetson_repo/` — project-specific WebRTC code
- `jetson-inference/` — NVIDIA AI inference library (unclear if actively used)
- `venv/` — Python virtual environment

**Loose Python/shell scripts in `~` (directly in mayra's home):**
- `esp32_sensor_reader.py` — STALE: reads `HEADING:` and `$GPRMC` (old ESP32 firmware format, IMU/GPS since moved to Pixhawk)
- `sensor_reader.py` — STALE: reads `HEAD:` only, also old format
- `heading_reader.py` — not yet read
- `test_sensor_service.py` — not yet read
- `test_opencv_cam.py` — camera sanity check
- `webrtc_jetson.py`, `webrtc_send.py` — WebRTC streaming
- `jetson_webrtc.sh`, `jetson_webrtc_sender.sh` — launch scripts
- `record_camera.sh`, `record_start.sh` — video recording
- `blink_led.sh` — GPIO test
- `ws_test.py` — WebSocket test
- `requirements.txt`, `requirements.lock.txt` — Python deps
- `main` (no extension) — unknown, possibly binary
- `.git-credentials` — **CONTAINS PLAINTEXT GITHUB TOKEN — DO NOT COMMIT OR EXPOSE**

---

## Current ESP32 sensor firmware (provided by Mayra via email, IS UP TO DATE)

Arduino/ESP32 code that reads three sensors and outputs a CSV line every 3 seconds over USB serial:

- **DS18B20** temperature (1-Wire on GPIO 4)
- **TDS/Salinity** (analog on GPIO 1, with temperature compensation — cubic polynomial → EC → ppm → PPT)
- **Atlas Scientific EZO pH** (software UART GPIO 16/17 @ 9600 baud, validates 0 < pH < 14)

**Output format @ 115200 baud, every 3 seconds:**
```
TEMP:23.45,SAL:0.324,PH:7.12
```

No GPS, no IMU, no heading from ESP32 anymore — those moved to the Pixhawk's built-in M8N GPS and IMU.

**File:** `working-sensors-code.txt` in the Claude.ai project docs (John can upload if needed).

---

## THE CRITICAL UNKNOWN (what Claude Code needs to answer first)

**Does any Python script on the Jetson parse the current `TEMP:/SAL:/PH:` format?**

The two sensor scripts we've read (`esp32_sensor_reader.py`, `sensor_reader.py`) both look for the OLD format (`HEADING:`, `HEAD:`, `$GPRMC`). Neither matches the current firmware output. This means one of three scenarios:

1. **A newer script exists** in `aquabot/` or `AquaBotGUI_WebRTC/` or somewhere else we haven't looked — we need to find it
2. **No Jetson-side code exists** that parses the current format yet — this is a gap John/Jamie needs to fill
3. **The code exists but is inside a Docker container** — need to check `docker ps -a` and `docker images`

---

## IMMEDIATE NEXT STEPS FOR CLAUDE CODE

**Step 1 — SSH in and answer the critical unknown:**

```bash
ssh mayra@100.76.1.26 "grep -rIl --include='*.py' -E 'TEMP:|SAL:|PH:' /home/mayra 2>/dev/null"
```

This searches every Python file in mayra's home for anything referencing the current sensor CSV format.

- If files are returned → `cat` each one, analyze it, report to John
- If nothing returned → move to Step 2 (check Docker) before concluding there's no ingestion code

**Step 2 — Check Docker for containerized code:**

```bash
ssh mayra@100.76.1.26 "docker ps -a && echo '---' && docker images"
```

If there are containers/images, investigate their contents.

**Step 3 — Explore `aquabot/` directory structure:**

```bash
ssh mayra@100.76.1.26 "tree -L 3 /home/mayra/aquabot 2>/dev/null || find /home/mayra/aquabot -maxdepth 3"
```

This is the most promising unexplored directory — likely contains the main project code.

**Step 4 — Check git status and remote of `/home/mayra`:**

```bash
ssh mayra@100.76.1.26 "cd /home/mayra && git remote -v && git status && git log --oneline -20"
```

Tells us if the code is already pushed somewhere, and what the commit history looks like.

**Step 5 — Report back to John** with a clear summary:
- Does sensor ingestion code for the current firmware format exist? Yes/No/Unclear
- If yes: where is it, what does it do, does it publish/log/forward the data anywhere
- If no: confirm this gap and suggest next steps (probably: write a new `sensor_ingest.py` in `aquabot/`)
- Any surprises or red flags found during exploration

---

## Strategy for mirroring Jetson code to this repo

Once we know what's on the Jetson and it's stable, pull the source files into `C:\Users\johnr\AQUABOTS_GitHub\` organized sensibly:

- **Jetson Python code** → `integration/jetson/` (new subfolder if it doesn't exist)
- **ESP32 firmware from Mayra** (`working-sensors-code.txt`) → `firmware/sensors/` (rename to `sensors_main.ino` or similar)
- **Don't pull `.git-credentials`, `.ssh/`, `venv/`, `__pycache__`, `.vscode-server/`, or any of the backup folders** — they're either secrets, environment-specific, or junk

Use `scp` or `rsync` from local PowerShell to pull files:

```powershell
scp mayra@100.76.1.26:/home/mayra/aquabot/some_file.py C:\Users\johnr\AQUABOTS_GitHub\integration\jetson\
```

---

## John's working preferences

- **PowerShell** on Windows — use Select-String instead of grep for LOCAL commands; bash syntax on the Jetson is fine
- **Concise but informative** — explanations are welcome, walls of text are not
- **Critical/constructive feedback encouraged** — push back when John is wrong, call out scope creep, keep him on task. Do not default to agreement.
- **One step at a time** when troubleshooting multi-step processes
- John knows C/C++, Python, embedded systems well; no need to over-explain basics

---

## What's NOT in scope for today

- Don't touch the camera pipeline
- Don't run `apt upgrade` of any kind
- Don't modify Mayra's code without confirming with John first
- Don't push anything to GitHub until John approves the plan
- Don't fix the broken ESP-IDF Dev Container in VS Code (separate issue, deferred)
