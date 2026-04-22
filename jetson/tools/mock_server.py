#!/usr/bin/env python3
"""
mock_server.py — local stand-in for the Jetson so you can exercise the GUI
without any hardware.

Serves the real index.html + static/ and emits synthesized telemetry on the
same websockets (8766 broadcast, 8770 control, 8765 signaling stub). Every
button in the GUI will fire a real message at this server; the server logs
what it received and replies as the real Jetson would.

Run:
    pip install flask websockets
    python3 jetson/tools/mock_server.py
Then open http://localhost:5000

Admin password is baked in as "demo" — enough to unlock the Manual tab and
pre-arm bypass so you can walk through those flows.
"""
import asyncio
import hashlib
import hmac
import json
import math
import os
import random
import secrets
import threading
import time

from flask import Flask, render_template

try:
    import websockets
except ImportError:
    raise SystemExit("Missing dependency — run:  pip install websockets flask")


# ------------------------------------------------------------------
# App — point Flask at the real templates/ and static/ directories.
# ------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
app = Flask(
    __name__,
    template_folder=os.path.join(ROOT, "templates"),
    static_folder=os.path.join(ROOT, "static"),
)


@app.route("/")
def index():
    return render_template("index.html")


# ------------------------------------------------------------------
# Admin auth — hardcoded password for the mock. Do not copy to prod.
# ------------------------------------------------------------------
ADMIN_PW = "demo"
ADMIN_HASH = hashlib.sha256(ADMIN_PW.encode()).hexdigest()
admin_sessions = set()

def admin_login(password):
    candidate = hashlib.sha256((password or "").encode()).hexdigest()
    if not hmac.compare_digest(candidate, ADMIN_HASH):
        return False, "invalid password"
    token = secrets.token_urlsafe(24)
    admin_sessions.add(token)
    return True, token


# ------------------------------------------------------------------
# Simulated vehicle state. Tuned so the GUI looks alive: vehicle drives
# a slow circle when armed, battery drops, mode transitions realistic.
# ------------------------------------------------------------------
state = {
    "lat": 32.2319, "lon": -110.9501,
    "home_lat": 32.2319, "home_lon": -110.9501,
    "heading": 0.0,
    "speed": 0.0,
    "throttle_pct": 0,
    "armed": False,
    "mode": "MANUAL",
    "slow": False,
    "current_wp": 0,
    "wp_total": 0,
    "home_set": False,
    "bat_v": 12.6, "bat_a": 0.0, "bat_pct": 95,
    "gps_fix": 0, "gps_sats": 4, "gps_hdop": 2.5,
    "ekf_cmp": 0.8, "ekf_pos": 0.3, "ekf_vel": 0.2,
    "temp": 23.4, "sal": 0.15, "ph": 7.2,
    "servo1": 1500, "servo3": 1500,
    "last_statustext": "", "last_statustext_sev": 6,
    "failsafe_tripped": False,
    "watchdog_timeout": 8.0,
    "watchdog_action": "HOLD",
    "last_gcs_hb": 0.0,
    "last_px_hb": 0.0,
    "last_gps_msg": 0.0,
    "last_esp32_msg": 0.0,
}

start_time = time.time()

def update_sim():
    """Advance the simulated vehicle one tick (~1 Hz)."""
    now = time.time()
    dt = 1.0

    # GPS/EKF warmup — HOME sets after 5 s.
    elapsed = now - start_time
    if elapsed > 2:
        state["gps_fix"]  = 3
        state["gps_sats"] = 10
        state["gps_hdop"] = max(0.6, 2.5 - elapsed * 0.05)
    if elapsed > 5 and not state["home_set"]:
        state["home_set"] = True
        state["last_statustext"]    = "HOME set — EKF/GPS ready"
        state["last_statustext_sev"] = 6

    # Battery slowly drops; faster when armed.
    drain = 0.003 if state["armed"] else 0.0005
    state["bat_v"] = max(10.5, state["bat_v"] - drain * dt)
    state["bat_pct"] = max(0, int((state["bat_v"] - 10.5) / (12.6 - 10.5) * 100))
    state["bat_a"]   = round(random.uniform(2, 6) if state["armed"] else random.uniform(0.2, 0.6), 2)

    # Motion model by mode.
    if state["armed"]:
        if state["mode"] == "AUTO":
            # Drive a small circle of radius ~10 m.
            target_speed = 0.8 * (0.3 if state["slow"] else 1.0)
            state["heading"] = (state["heading"] + 6) % 360
        elif state["mode"] == "RTL":
            # Head toward home.
            dlat = state["home_lat"] - state["lat"]
            dlon = state["home_lon"] - state["lon"]
            brng = math.degrees(math.atan2(dlon, dlat)) % 360
            state["heading"] = brng
            target_speed = 0.6
            if abs(dlat) < 1e-5 and abs(dlon) < 1e-5:
                state["armed"] = False
                state["mode"]  = "MANUAL"
                state["last_statustext"]     = "Reached home — disarming"
                state["last_statustext_sev"] = 6
        elif state["mode"] == "HOLD":
            target_speed = 0.0
        else:  # MANUAL / others
            target_speed = 0.3

        # Smooth speed toward target; convert to degrees-per-tick movement.
        state["speed"] += (target_speed - state["speed"]) * 0.2
        m_per_deg_lat = 111320
        dist_m = state["speed"] * dt
        hdg_rad = math.radians(state["heading"])
        state["lat"] += (dist_m * math.cos(hdg_rad)) / m_per_deg_lat
        state["lon"] += (dist_m * math.sin(hdg_rad)) / (m_per_deg_lat * math.cos(math.radians(state["lat"])))
        state["throttle_pct"] = int(min(100, state["speed"] * 100))
    else:
        state["speed"] = 0.0
        state["throttle_pct"] = 0

    # Servo PWM follows steering/throttle loosely.
    state["servo1"] = 1500 + int(math.sin(elapsed) * 60)
    state["servo3"] = 1500 + int(state["throttle_pct"] * 4)

    # Sensor jitter so the telemetry row isn't static.
    state["temp"] = round(23.4 + math.sin(elapsed/10) * 0.3, 2)
    state["sal"]  = round(0.15 + random.uniform(-0.01, 0.01), 3)
    state["ph"]   = round(7.2 + random.uniform(-0.05, 0.05), 2)

    # Pretend fresh heartbeats every tick.
    state["last_px_hb"]    = now
    state["last_gps_msg"]  = now
    state["last_esp32_msg"] = now


def build_broadcast():
    now = time.time()
    ts = time.strftime("%H:%M:%S")

    def age_ms(t): return int((now - t) * 1000) if t else -1

    msg = state["last_statustext"] or ""
    state["last_statustext"] = ""

    return {
        "TIME": ts,
        "LAT": round(state["lat"], 7),
        "LON": round(state["lon"], 7),
        "HEAD": round(state["heading"], 1),
        "SPD": round(state["speed"], 2),
        "TEMP": state["temp"],
        "SAL":  state["sal"],
        "PH":   state["ph"],
        "ARMED": state["armed"],
        "MODE":  state["mode"],
        "STATUS": msg,
        "STATUS_SEV": state["last_statustext_sev"],
        "SLOW_MODE": state["slow"],
        "CURRENT_WP": state["current_wp"],
        "WP_TOTAL":   state["wp_total"],
        "HOME_SET":   state["home_set"],
        "THROTTLE_PCT": state["throttle_pct"],
        "SERVO1": state["servo1"], "SERVO2": 1500,
        "SERVO3": state["servo3"], "SERVO4": 1500,
        "BAT_V":   round(state["bat_v"], 2),
        "BAT_A":   state["bat_a"],
        "BAT_PCT": state["bat_pct"],
        "GPS_FIX":  state["gps_fix"],
        "GPS_SATS": state["gps_sats"],
        "GPS_HDOP": round(state["gps_hdop"], 2),
        "EKF_COMPASS_VAR": state["ekf_cmp"],
        "EKF_POS_VAR":     state["ekf_pos"],
        "EKF_VEL_VAR":     state["ekf_vel"],
        "HB_AGE_MS":    age_ms(state["last_px_hb"]),
        "GPS_AGE_MS":   age_ms(state["last_gps_msg"]),
        "ESP32_AGE_MS": age_ms(state["last_esp32_msg"]),
        "GCS_AGE_MS":   age_ms(state["last_gcs_hb"]),
        "WATCHDOG_TIMEOUT": state["watchdog_timeout"],
        "WATCHDOG_ACTION":  state["watchdog_action"],
        "FAILSAFE_TRIPPED": state["failsafe_tripped"],
    }


# ------------------------------------------------------------------
# Websocket handlers
# ------------------------------------------------------------------
telemetry_clients = set()

async def telemetry_handler(ws):
    telemetry_clients.add(ws)
    print("[ws:8766] telemetry client connected")
    try:
        await ws.wait_closed()
    finally:
        telemetry_clients.discard(ws)
        print("[ws:8766] telemetry client gone")


async def control_handler(ws):
    print("[ws:8770] control client connected")
    try:
        async for raw in ws:
            raw = raw.strip()
            if raw in ("ARM", "DISARM"):
                state["armed"] = (raw == "ARM")
                if state["armed"]: state["mode"] = "MANUAL"
                print(f"[ctl] {raw}")
                continue
            # Plain float = throttle % (legacy path)
            try:
                float(raw)
                print(f"[ctl] throttle {raw}")
                continue
            except ValueError:
                pass
            try:
                d = json.loads(raw)
            except json.JSONDecodeError:
                print(f"[ctl] unknown: {raw[:80]}")
                continue

            action = d.get("action")

            # Most actions just acknowledge — the sim state reacts where it makes sense.
            if action == "gcs_heartbeat":
                state["last_gcs_hb"] = time.time()
                continue  # silent

            if action == "upload_mission":
                wps = d.get("waypoints", [])
                state["wp_total"] = len(wps)
                state["current_wp"] = 0
                await ws.send(json.dumps({"status": "ok",
                                          "message": f"Mission uploaded: {len(wps)} waypoints + RTL"}))
                continue

            if action == "go":
                if not state["home_set"]:
                    await ws.send(json.dumps({"status": "error",
                                              "message": "HOME not set — wait for GPS lock"}))
                    continue
                state["armed"] = True
                state["mode"]  = "AUTO"
                state["current_wp"] = 0
                await ws.send(json.dumps({"status": "ok",
                                          "message": "Mission started"}))
                continue

            if action in ("hold", "resume", "rth", "abort"):
                mode_map = {"hold": "HOLD", "resume": "AUTO", "rth": "RTL", "abort": "MANUAL"}
                state["mode"] = mode_map[action]
                if action == "abort": state["armed"] = False
                await ws.send(json.dumps({"status": "ok", "message": f"{action} mocked"}))
                continue

            if action == "slow_mode":
                state["slow"] = bool(d.get("enabled", False))
                await ws.send(json.dumps({"status": "ok",
                                          "message": f"Slow mode {'ON' if state['slow'] else 'OFF'}"}))
                continue

            if action == "estop":
                state["armed"] = False
                state["mode"]  = "MANUAL"
                await ws.send(json.dumps({"status": "ok", "message": "E-STOP: vehicle disarmed"}))
                continue

            if action == "set_watchdog":
                if d.get("timeout") is not None:
                    try: state["watchdog_timeout"] = max(2.0, float(d["timeout"]))
                    except (TypeError, ValueError): pass
                if d.get("failsafe_action") in ("HOLD", "RTL", "DISARM"):
                    state["watchdog_action"] = d["failsafe_action"]
                await ws.send(json.dumps({"status": "ok",
                                          "message": f"Watchdog: t={state['watchdog_timeout']}s action={state['watchdog_action']}"}))
                continue

            if action == "admin_login":
                ok, info = admin_login(d.get("password", ""))
                await ws.send(json.dumps({
                    "status": "ok" if ok else "error",
                    "message": info if not ok else "admin ok",
                    "token":   info if ok else None,
                }))
                print(f"[admin] login {'ok' if ok else 'failed'}")
                continue

            if action == "admin_logout":
                admin_sessions.discard(d.get("token"))
                await ws.send(json.dumps({"status": "ok", "message": "logged out"}))
                continue

            if action == "admin_check":
                ok = d.get("token") in admin_sessions
                await ws.send(json.dumps({"status": "ok" if ok else "error",
                                          "message": "valid" if ok else "invalid"}))
                continue

            if action == "set_mode":
                if d.get("token") not in admin_sessions:
                    await ws.send(json.dumps({"status": "error", "message": "admin required"}))
                    continue
                state["mode"] = (d.get("mode") or "MANUAL").upper()
                await ws.send(json.dumps({"status": "ok", "message": f"Mode set: {state['mode']}"}))
                continue

            if action == "manual_rc":
                if d.get("token") not in admin_sessions:
                    await ws.send(json.dumps({"status": "error", "message": "admin required"}))
                    continue
                # No ack — stream is 20 Hz.
                continue

            if action == "manual_release":
                if d.get("token") not in admin_sessions:
                    await ws.send(json.dumps({"status": "error", "message": "admin required"}))
                    continue
                await ws.send(json.dumps({"status": "ok", "message": "RC override released"}))
                continue

            if action == "upload_fence":
                n = len(d.get("polygon", []))
                await ws.send(json.dumps({"status": "ok",
                                          "message": f"Fence uploaded: {n} vertices (mock)"}))
                continue

            if action == "fence_enable":
                await ws.send(json.dumps({"status": "ok",
                                          "message": f"Fence {'enabled' if d.get('enabled') else 'disabled'} (mock)"}))
                continue

            # Unknown JSON action — echo.
            await ws.send(json.dumps({"status": "error", "message": f"unknown action: {action}"}))
    except websockets.ConnectionClosed:
        pass
    finally:
        print("[ws:8770] control client gone")


async def signaling_stub_handler(ws):
    """Accepts the WebRTC signaling socket so the browser doesn't error-loop.
    We never reply with a real SDP answer so the video stays blank — which is
    expected in the mock."""
    print("[ws:8765] signaling client connected (stub)")
    try:
        async for _ in ws:
            pass
    except websockets.ConnectionClosed:
        pass


async def telemetry_broadcast():
    while True:
        update_sim()
        payload = json.dumps(build_broadcast())
        for c in list(telemetry_clients):
            try: await c.send(payload)
            except Exception: telemetry_clients.discard(c)
        await asyncio.sleep(1)


async def start_servers():
    await websockets.serve(telemetry_handler,      "0.0.0.0", 8766)
    await websockets.serve(control_handler,        "0.0.0.0", 8770)
    await websockets.serve(signaling_stub_handler, "0.0.0.0", 8765)
    print("[mock] telemetry ws -> 8766")
    print("[mock] control   ws -> 8770")
    print("[mock] signaling ws -> 8765 (stub)")
    asyncio.create_task(telemetry_broadcast())
    await asyncio.Future()


def run_async():
    asyncio.run(start_servers())


if __name__ == "__main__":
    print("=" * 60)
    print("AquaBot GUI mock server")
    print("  HTTP:         http://localhost:5000")
    print(f"  admin pw:     {ADMIN_PW}")
    print("=" * 60)
    threading.Thread(target=run_async, daemon=True).start()
    # small pause so WS sockets bind before Flask starts handing out pages
    time.sleep(0.3)
    # Pick up template edits without needing a server restart. Safe in the
    # mock since we also disable the reloader (it would re-spawn our threads).
    app.config["TEMPLATES_AUTO_RELOAD"] = True
    app.jinja_env.auto_reload = True
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)
