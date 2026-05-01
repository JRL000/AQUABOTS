import asyncio
import hashlib
import hmac
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import websockets
from flask import Flask, render_template
import serial
import json
from datetime import datetime
import pytz
from pymavlink import mavutil
import math

import swarm_protocol
from swarm_coordinator import SwarmCoordinator

pixhawk_lock = threading.Lock()
mission_uploading = threading.Event()
telemetry_ready = threading.Event()

# =====================================================
# CONFIG
# =====================================================
TELEMETRY_PORT = 8766
CONTROL_PORT = 8770

# =====================================================
# SAFETY LIMITS  (written to Pixhawk flash at startup)
# =====================================================
# Throttle ramp rate — percent per second.
# 25 = takes 4 seconds to go from 0 → 100%. Prevents shaft shock on start.
MOTOR_SLEWRATE = 25

# Maximum speed in AUTO mode — meters per second.
# 1.5 m/s ≈ 3 knots. Adjust up after confirming the shaft survives.
WP_SPEED_MS = 1.5
telemetry_clients = set()

# ESP32 serial is opened inside read_esp32() with retry — don't open at
# module scope, because if /dev/ttyACM1 isn't enumerated yet at boot we'd
# be stuck with ser=None for the whole process lifetime and never recover.

# Pixhawk
pixhawk = mavutil.mavlink_connection('udp:0.0.0.0:14552')

# =====================================================
# MOTOR / MODE / ARM CONTROL
# =====================================================
current_throttle = 0

# Slow-mode cap — uniformly caps Pixhawk's throttle output via MOT_THR_MAX.
# False (default) = full power (100%). True = capped at SLOW_MODE_THR_MAX (30%).
SLOW_MODE_THR_MAX = 30
slow_mode_enabled = False

# =====================================================
# ADMIN AUTH (Phases B3 / C1)
# =====================================================
# Password is supplied via the AQUABOT_ADMIN_PW env var at service startup
# (set it in the systemd unit so the plaintext never touches disk). If unset,
# admin features are disabled — the Manual tab stays locked and pre-arm cannot
# be bypassed. Sessions are opaque tokens kept in-memory only.
_admin_pw = os.environ.get("AQUABOT_ADMIN_PW", "")
_admin_pw_hash = hashlib.sha256(_admin_pw.encode()).hexdigest() if _admin_pw else None
admin_sessions = set()   # active token strings
admin_lock = threading.Lock()

def admin_login(password):
    """Return (ok, token_or_reason). Uses constant-time compare."""
    if not _admin_pw_hash:
        return False, "admin disabled (AQUABOT_ADMIN_PW not set)"
    candidate = hashlib.sha256((password or "").encode()).hexdigest()
    if not hmac.compare_digest(candidate, _admin_pw_hash):
        return False, "invalid password"
    token = secrets.token_urlsafe(24)
    with admin_lock:
        admin_sessions.add(token)
    print(f"[ADMIN] login ok — token ...{token[-6:]}")
    return True, token

def admin_check(token):
    if not token:
        return False
    with admin_lock:
        return token in admin_sessions

def admin_logout(token):
    with admin_lock:
        admin_sessions.discard(token)

# =====================================================
# LINK-LOSS FAILSAFE (Phase B1)
# =====================================================
# Browser sends {"action":"gcs_heartbeat"} every 1s over the control WS.
# If no heartbeat for GCS_WATCHDOG_TIMEOUT seconds AND vehicle is armed,
# fire the configured failsafe action on the Pixhawk.
# HOLD is the safer default on water — DISARM leaves the boat drifting with
# no steering authority, RTL requires a clean compass.
GCS_WATCHDOG_TIMEOUT = 8.0
GCS_WATCHDOG_ACTION = "HOLD"   # one of: HOLD, RTL, DISARM
last_gcs_heartbeat_ts = 0.0
failsafe_tripped = False        # latches True while watchdog active; resets when link returns

def set_throttle(percent):
    pwm = int(1100 + (percent / 100.0) * 800)
    print(f"Throttle {percent}% → PWM {pwm}")
    with pixhawk_lock:
        pixhawk.mav.rc_channels_override_send(
            pixhawk.target_system,
            pixhawk.target_component,
            65535, 65535, pwm, 65535, 65535, 65535, 65535, 65535
        )

def set_slow_mode(enabled):
    """Toggle slow-mode throttle cap on the Pixhawk (MOT_THR_MAX param)."""
    global slow_mode_enabled
    value = float(SLOW_MODE_THR_MAX) if enabled else 100.0
    print(f"Slow mode {'ON' if enabled else 'OFF'} → MOT_THR_MAX={value}")
    with pixhawk_lock:
        pixhawk.mav.param_set_send(
            pixhawk.target_system,
            pixhawk.target_component,
            b'MOT_THR_MAX',
            value,
            mavutil.mavlink.MAV_PARAM_TYPE_REAL32
        )
    slow_mode_enabled = bool(enabled)

def set_mode(mode):
    print(f"Setting mode: {mode}")
    mode_id = pixhawk.mode_mapping().get(mode)
    if mode_id is None:
        print("Mode not found:", mode)
        return
    with pixhawk_lock:
        # MAV_CMD_DO_SET_MODE is the reliable path for ArduPilot 4.x
        pixhawk.mav.command_long_send(
            pixhawk.target_system,
            pixhawk.target_component,
            mavutil.mavlink.MAV_CMD_DO_SET_MODE,
            0,
            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            mode_id,
            0, 0, 0, 0, 0
        )

def arm_vehicle():
    print("ARMING VEHICLE")
    set_mode("MANUAL")
    with pixhawk_lock:
        pixhawk.mav.command_long_send(
            pixhawk.target_system,
            pixhawk.target_component,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            0, 1, 0, 0, 0, 0, 0, 0
        )

def disarm_vehicle():
    print("DISARMING VEHICLE")
    with pixhawk_lock:
        pixhawk.mav.command_long_send(
            pixhawk.target_system,
            pixhawk.target_component,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            0, 0, 0, 0, 0, 0, 0, 0
        )

def start_mission():
    """
    Arm, switch to AUTO, confirm the mode change, then trigger MISSION_START.
    Returns (success: bool, message: str).

    AUTO requires EKF origin + HOME. With ARMING_CHECK=0 the arm succeeds
    immediately, but ArduRover still refuses AUTO until HOME is set — the
    old version ignored the rejection and sent MISSION_START anyway,
    leaving the rover armed in MANUAL with no throttle/servo output.
    """
    print("Starting mission: ARM + AUTO + MISSION_START")

    # Nudge ArduPilot to (re)emit HOME_POSITION in case we started after it was already set.
    with pixhawk_lock:
        pixhawk.mav.command_long_send(
            pixhawk.target_system,
            pixhawk.target_component,
            mavutil.mavlink.MAV_CMD_GET_HOME_POSITION,
            0,
            0, 0, 0, 0, 0, 0, 0
        )

    wait_deadline = time.time() + 30
    while not home_set and time.time() < wait_deadline:
        time.sleep(0.2)
    if not home_set:
        msg = "HOME not set after 30s — wait for GPS/EKF lock, then retry"
        print(f"[MISSION] {msg}")
        return False, msg

    arm_vehicle()
    time.sleep(1)

    set_mode("AUTO")
    mode_deadline = time.time() + 3
    while mode != "AUTO" and time.time() < mode_deadline:
        time.sleep(0.1)
    if mode != "AUTO":
        msg = f"Mode change to AUTO rejected (still {mode}) — mission not started"
        print(f"[MISSION] {msg}")
        return False, msg

    with pixhawk_lock:
        pixhawk.mav.command_long_send(
            pixhawk.target_system,
            pixhawk.target_component,
            mavutil.mavlink.MAV_CMD_MISSION_START,
            0,
            0, 0, 0, 0, 0, 0, 0
        )
    print("MISSION_START command sent")
    return True, "Mission started: ARM + AUTO + MISSION_START"

# Local copy of the active fence — the Pixhawk owns the source of truth, but
# we keep the polygon here so the swarm coordinator can refuse waypoints that
# would land outside it (catching them earlier than the Pixhawk's own check).
_fence_polygon_latlon = []
_fence_enabled = False


def _point_in_polygon(lat, lon, polygon):
    """Even-odd ray-cast point-in-polygon test. polygon: list of [lat, lon]."""
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        yi, xi = polygon[i]
        yj, xj = polygon[j]
        if ((yi > lat) != (yj > lat)) and \
           (lon < (xj - xi) * (lat - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def upload_fence_sync(polygon_latlon, return_lat, return_lon, action="HOLD"):
    """
    Upload a polygonal inclusion fence to the Pixhawk using the legacy
    FENCE_POINT protocol (still the most reliable path on ArduPilot 4.x).

    polygon_latlon: list of [lat, lon] vertices, ordered, at least 3.
    return_lat/lon: "return point" — required; typically the home position.
                    Ignored at runtime for polygon fences but still required
                    by the protocol.
    action: HOLD | RTL | REPORT — mapped to FENCE_ACTION.
    """
    if not polygon_latlon or len(polygon_latlon) < 3:
        return False, "Polygon needs at least 3 vertices"

    # ArduPilot fence actions: 0=Report, 1=RTL/Land, 2=Always Land, 3=SmartRTL,
    # 4=Brake-Hold (rovers treat BRAKE as HOLD), 5=SmartRTL-or-Land.
    action_map = {"REPORT": 0, "RTL": 1, "HOLD": 4, "BRAKE": 4, "LAND": 2}
    fence_action = action_map.get(action.upper(), 4)

    n = len(polygon_latlon)
    total = n + 1  # +1 for the mandatory return point at index 0
    try:
        with pixhawk_lock:
            ts, tc = pixhawk.target_system, pixhawk.target_component

            # Fence types on ArduPilot: bitmask. 1=altitude-max, 2=polygon,
            # 4=circle. 6 = polygon + circle. We want polygon only for now.
            pixhawk.mav.param_set_send(ts, tc, b'FENCE_TYPE',  2,
                                        mavutil.mavlink.MAV_PARAM_TYPE_INT32)
            pixhawk.mav.param_set_send(ts, tc, b'FENCE_ACTION', fence_action,
                                        mavutil.mavlink.MAV_PARAM_TYPE_INT32)
            pixhawk.mav.param_set_send(ts, tc, b'FENCE_TOTAL', total,
                                        mavutil.mavlink.MAV_PARAM_TYPE_INT32)

            # Return point (idx 0) — ArduPilot requires it even for polygon
            # fences. Using home is the least-surprising default.
            pixhawk.mav.fence_point_send(ts, tc, 0, total,
                                          float(return_lat), float(return_lon))
            # Polygon vertices at indices 1..n
            for i, (lat, lon) in enumerate(polygon_latlon):
                pixhawk.mav.fence_point_send(ts, tc, i + 1, total,
                                              float(lat), float(lon))
                time.sleep(0.05)  # modest pacing so the autopilot keeps up

            # Finally, enable the fence. Do this last — a half-loaded fence
            # with FENCE_ENABLE=1 is worse than no fence.
            pixhawk.mav.param_set_send(ts, tc, b'FENCE_ENABLE', 1,
                                        mavutil.mavlink.MAV_PARAM_TYPE_INT32)

        global _fence_polygon_latlon, _fence_enabled
        _fence_polygon_latlon = list(polygon_latlon)
        _fence_enabled = True
        return True, f"Fence uploaded: {n} vertices, action={action}"
    except Exception as e:
        return False, f"Fence upload error: {e}"


def set_fence_enable(enabled):
    global _fence_enabled
    _fence_enabled = bool(enabled)
    val = 1 if enabled else 0
    with pixhawk_lock:
        pixhawk.mav.param_set_send(pixhawk.target_system, pixhawk.target_component,
                                    b'FENCE_ENABLE', val,
                                    mavutil.mavlink.MAV_PARAM_TYPE_INT32)


def upload_swarm_waypoint(target_lat, target_lon, target_heading_deg):
    """
    Push a single GUIDED-mode position target to the Pixhawk. Used by the
    swarm coordinator each time a follower's assigned slot moves.
    Does NOT touch the loaded mission. Returns True on success.
    """
    try:
        with pixhawk_lock:
            ts = pixhawk.target_system
            tc = pixhawk.target_component
            # type_mask: ignore velocity, accel, force, yaw_rate. Use position + yaw.
            # Bit positions: 1=px,2=py,4=pz, 8=vx,16=vy,32=vz, 64=ax,128=ay,256=az,
            # 512=force, 1024=yaw, 2048=yaw_rate.
            ignore_mask = (8 | 16 | 32 | 64 | 128 | 256 | 512 | 2048)
            pixhawk.mav.set_position_target_global_int_send(
                0,                                                  # time_boot_ms
                ts, tc,
                mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
                ignore_mask,
                int(target_lat * 1e7),
                int(target_lon * 1e7),
                0.0,                                                # alt (boat)
                0, 0, 0, 0, 0, 0,                                   # vel + accel ignored
                math.radians(target_heading_deg),                   # yaw
                0,                                                  # yaw_rate ignored
            )
        return True
    except Exception as e:
        print(f"[SWARM] waypoint upload error: {e}")
        return False


def swarm_geofence_check(lat, lon):
    """Refuse swarm waypoint if the active fence is enabled and the target
    falls outside its polygon. If no fence is set, all points are accepted."""
    if not _fence_enabled or not _fence_polygon_latlon:
        return True
    return _point_in_polygon(lat, lon, _fence_polygon_latlon)


# Coordinator instance — populated by main(), referenced by read_esp32() and
# by the control_handler for swarm_enable / swarm_set_pattern.
swarm = SwarmCoordinator(
    upload_waypoint=upload_swarm_waypoint,
    set_mode=lambda m: set_mode(m),
    geofence_check=swarm_geofence_check,
)


def upload_mission_sync(waypoints_latlon):
    """
    Upload a mission to the Pixhawk via MAVLink.
    waypoints_latlon: list of [lat, lon] pairs (floats)
    Returns (success: bool, message: str)
    """
    global wp_total
    if not waypoints_latlon:
        return False, "No waypoints provided"

    # Pause read_pixhawk so it doesn't consume MISSION_REQUEST messages
    mission_uploading.set()
    time.sleep(0.3)  # wait for any in-progress recv_match to finish

    try:
        with pixhawk_lock:
            ts = pixhawk.target_system
            tc = pixhawk.target_component

            # Clear existing mission
            pixhawk.mav.mission_clear_all_send(ts, tc)
            ack = pixhawk.recv_match(type='MISSION_ACK', blocking=True, timeout=3)
            if not ack:
                return False, "No ACK after MISSION_CLEAR_ALL — check Pixhawk connection"

            # Build mission item list
            items = []
            for i, wp in enumerate(waypoints_latlon):
                items.append((
                    i,                                               # seq
                    mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,  # frame
                    mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,           # command
                    1 if i == 0 else 0,                             # current
                    1,                                              # autocontinue
                    0.0,                                            # param1: hold time (s)
                    3.0,                                            # param2: acceptance radius (m)
                    0.0,                                            # param3: pass radius
                    0.0,                                            # param4: yaw (0=auto)
                    int(float(wp[0]) * 1e7),                        # x = lat * 1e7
                    int(float(wp[1]) * 1e7),                        # y = lon * 1e7
                    0.0,                                            # z = altitude (boat: irrelevant)
                ))
            n = len(items)
            items.append((
                n,
                mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT,
                mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH,
                0, 1,
                0.0, 0.0, 0.0, 0.0,
                0, 0, 0.0,
            ))

            total = len(items)
            pixhawk.mav.mission_count_send(ts, tc, total)

            # Handle request-response handshake
            for _ in range(total + 5):
                req = pixhawk.recv_match(
                    type=['MISSION_REQUEST', 'MISSION_REQUEST_INT', 'MISSION_ACK'],
                    blocking=True, timeout=5
                )
                if req is None:
                    return False, "Timeout during upload — Pixhawk stopped responding"

                rtype = req.get_type()

                if rtype == 'MISSION_ACK':
                    if req.type == 0:
                        wp_total = len(waypoints_latlon)
                        return True, f"Mission uploaded: {wp_total} waypoints + RTL"
                    else:
                        return False, f"Mission rejected by Pixhawk (MAVLink error {req.type})"

                seq = req.seq
                if seq >= total:
                    return False, f"Pixhawk requested unexpected seq {seq} (total={total})"

                s = items[seq]
                pixhawk.mav.mission_item_int_send(
                    ts, tc,
                    s[0], s[1], s[2], s[3], s[4],
                    s[5], s[6], s[7], s[8],
                    s[9], s[10], s[11],
                    mavutil.mavlink.MAV_MISSION_TYPE_MISSION
                )

            return False, "Upload loop ended without MISSION_ACK"

    except Exception as e:
        return False, f"Upload error: {e}"
    finally:
        mission_uploading.clear()

# =====================================================
# GLOBAL TELEMETRY DATA
# =====================================================
lat = 0
lon = 0
heading = 0
speed = 0
throttle_pct = 0  # VFR_HUD.throttle (0..100)
armed = False
mode = "UNKNOWN"
last_statustext = ""
last_statustext_sev = 6  # MAV_SEVERITY: 0=EMERGENCY..6=INFO
current_wp = 0
wp_total = 0  # set after a successful mission upload
home_set = False  # flips True on first HOME_POSITION — AUTO mode requires this

# Servo / actuator outputs (PWM in µs, 1100–1900). Populated from SERVO_OUTPUT_RAW.
servo1_pwm = 0  # steering
servo2_pwm = 0
servo3_pwm = 0  # throttle
servo4_pwm = 0

# Battery (populated from SYS_STATUS / BATTERY_STATUS; -1 = unknown)
battery_voltage = 0.0   # volts
battery_current = 0.0   # amps (may be negative while charging)
battery_remaining = -1  # percent, -1 if Pixhawk can't estimate

# GPS health (populated from GPS_RAW_INT)
gps_fix_type = 0   # 0=no fix, 2=2D, 3=3D, 4=DGPS, 5=RTK float, 6=RTK fixed
gps_sats = 0
gps_hdop = 99.99

# EKF health (populated from EKF_STATUS_REPORT). Lower = better; >1.0 is suspect.
ekf_compass_variance = 0.0
ekf_pos_variance = 0.0
ekf_velocity_variance = 0.0

# Attitude (populated from ATTITUDE). Useful for spotting wave/wind push.
roll_deg = 0.0
pitch_deg = 0.0

# Navigation telemetry (populated from NAV_CONTROLLER_OUTPUT). These are what
# the autopilot is computing while it's trying to reach the active waypoint.
nav_target_bearing = 0.0   # absolute bearing to active WP (deg from north)
nav_desired_bearing = 0.0  # desired course Pixhawk wants to fly
nav_wp_dist_m = 0          # distance to active WP (meters)
nav_xtrack_error_m = 0.0   # cross-track error: signed perp distance from intended track

# Link freshness — wall-clock seconds since epoch of the most recent message.
# Used for age-based link-quality indicators in the GUI.
last_heartbeat_ts = 0.0
last_gps_ts = 0.0
last_esp32_ts = 0.0

temp = 0
sal = 0
ph = 0

# CSV logging (legacy format — unchanged so downstream tools keep working)
tucson = pytz.timezone("America/Phoenix")
start_time = datetime.now(tucson).strftime("%Y-%m-%d_%H-%M-%S")
log_dir = "/home/mayra/videos"
os.makedirs(log_dir, exist_ok=True)
file = open(f"{log_dir}/telemetry_{start_time}.csv", "a")
file.write("TIME,LAT,LON,HEAD,SPD,TEMP,SAL,PH\n")
file.flush()

# Black-box JSONL log — full per-tick broadcast dict. One JSON object per line.
# Captures everything the GUI sees, so a post-mission replay can reconstruct
# exactly what the operator saw at any instant (PWM, battery, EKF, link age…).
blackbox = open(f"{log_dir}/blackbox_{start_time}.jsonl", "a")

# =====================================================
# FLASK
# =====================================================
app = Flask(__name__)

@app.route("/")
def index():
    # MAPBOX_TOKEN — optional. If set in env, the dashboard exposes Mapbox
    # Satellite + Outdoors layers (max zoom 22, much sharper than Esri).
    return render_template("index.html",
                           mapbox_token=os.environ.get("MAPBOX_TOKEN", ""))

# =====================================================
# ESP32 THREAD
# =====================================================
def trigger_failsafe(reason):
    """
    Fire the configured failsafe action. Idempotent while failsafe_tripped latched.
    Called from the GCS watchdog and from the E-stop handler.
    """
    global failsafe_tripped
    action = (GCS_WATCHDOG_ACTION or "HOLD").upper()
    print(f"[FAILSAFE] Triggered ({reason}) → {action}")
    failsafe_tripped = True
    if action == "DISARM":
        disarm_vehicle()
    elif action == "RTL":
        set_mode("RTL")
    else:
        set_mode("HOLD")


def gcs_watchdog():
    """
    Background thread: if the browser stops sending GCS heartbeats while the
    vehicle is armed, fire the configured failsafe so the boat doesn't run off
    when the operator's link dies.
    """
    global failsafe_tripped
    while True:
        try:
            time.sleep(0.5)
            # No heartbeats yet at boot — nothing to check until the GUI
            # actually connects the first time.
            if last_gcs_heartbeat_ts == 0:
                continue
            age = time.time() - last_gcs_heartbeat_ts
            if armed and age > GCS_WATCHDOG_TIMEOUT and not failsafe_tripped:
                trigger_failsafe(f"no GCS heartbeat for {age:.1f}s")
            # Clear the latch once the operator reconnects so they can
            # regain control without restarting the Jetson app.
            if failsafe_tripped and age < 2.0:
                print("[FAILSAFE] GCS link restored — clearing latch")
                failsafe_tripped = False
        except Exception as e:
            print("[FAILSAFE] watchdog error:", e)


class _TcpLink:
    """Duck-types serial.Serial enough for read_esp32's needs.

    Uses raw recv() with manual line buffering instead of makefile('rb').
    Why: when the buffered file object's underlying socket times out, the
    file object enters a permanently-poisoned state and any further read
    raises 'cannot read from timed out object' as a plain OSError —
    indistinguishable from a real disconnect. With raw recv we can
    distinguish: socket.timeout = transient (return empty), 0 bytes or
    other OSError = real disconnect (raise)."""
    def __init__(self, host, port):
        self._sock = socket.create_connection((host, port), timeout=10)
        self._sock.settimeout(1.0)
        self._buf = b""
    def readline(self):
        while b"\n" not in self._buf:
            try:
                chunk = self._sock.recv(4096)
            except (socket.timeout, TimeoutError):
                return b""
            if not chunk:
                raise OSError("connection closed by peer")
            self._buf += chunk
        line, _, self._buf = self._buf.partition(b"\n")
        return line + b"\n"
    def write(self, data):
        self._sock.sendall(data)
    def close(self):
        try: self._sock.close()
        except Exception: pass


def _open_esp32_link():
    """
    Open the link to the on-board ESP32. Real hardware uses /dev/ttyACM1.
    For mock/dev testing, set AQUABOT_ESP32_TCP=host:port and a swarm_mock.py
    server gets used instead. Retries forever; never raises.
    """
    tcp_addr = os.environ.get("AQUABOT_ESP32_TCP")
    if tcp_addr:
        host, _, port_s = tcp_addr.partition(":")
        port = int(port_s) if port_s else 7790
        while True:
            try:
                link = _TcpLink(host, port)
                print(f"[ESP32] TCP mock connected on {host}:{port}")
                return link
            except (ConnectionRefusedError, socket.timeout, OSError) as e:
                print(f"[ESP32] TCP mock not up yet ({e}); retrying in 3s")
                time.sleep(3)
    while True:
        try:
            link = serial.Serial('/dev/ttyACM1', 115200, timeout=1)
            print('[ESP32] Serial connected on /dev/ttyACM1')
            return link
        except serial.SerialException:
            time.sleep(10)


def read_esp32():
    """
    Reader thread for the on-board ESP32 link. Handles TWO line families:
      - legacy "TEMP:..." sensor lines -> updates global temp/sal/ph
      - swarm-bridge tagged lines      -> forwarded to swarm_coordinator
    Also drains the coordinator's outbound queue and writes those lines back.
    """
    global temp, sal, ph, last_esp32_ts

    link = None
    while True:
        if link is None:
            link = _open_esp32_link()

        try:
            raw = link.readline()
            if raw:
                line = raw.decode('utf-8', errors='ignore').strip()
                if line.startswith("TEMP:"):
                    print("ESP32:", line)
                    parts = line.split(',')
                    for p in parts:
                        if ':' in p:
                            k, v = p.split(':')
                            if k == "TEMP":   temp = float(v)
                            elif k == "SAL":  sal = float(v)
                            elif k == "PH":   ph = float(v)
                    last_esp32_ts = time.time()
                elif line:
                    # Anything else: try the swarm-bridge dispatcher.
                    swarm.feed_serial_line(line)
                    last_esp32_ts = time.time()

            # Drain outbound queue (ANCHOR_GPS / SET_FORMATION / SWARM_ENABLE)
            for _ in range(8):  # batch; don't starve the read side
                outline = swarm.get_outbound_line(timeout=0.0)
                if outline is None:
                    break
                try:
                    link.write(outline.encode('utf-8'))
                except Exception as e:
                    print(f"[ESP32] write error ({e}) — reconnecting")
                    try: link.close()
                    except Exception: pass
                    link = None
                    break
        except (serial.SerialException, OSError, socket.error) as e:
            print(f"[ESP32] link error ({e}) — reconnecting")
            try: link.close()
            except Exception: pass
            link = None
        except Exception as e:
            print("ESP32 error:", e)

# =====================================================
# PIXHAWK THREAD
# =====================================================
def read_pixhawk():
    global lat, lon, heading, speed, throttle_pct, armed, mode
    global last_statustext, last_statustext_sev, current_wp, home_set
    global servo1_pwm, servo2_pwm, servo3_pwm, servo4_pwm
    global battery_voltage, battery_current, battery_remaining
    global gps_fix_type, gps_sats, gps_hdop
    global ekf_compass_variance, ekf_pos_variance, ekf_velocity_variance
    global roll_deg, pitch_deg
    global nav_target_bearing, nav_desired_bearing, nav_wp_dist_m, nav_xtrack_error_m
    global last_heartbeat_ts, last_gps_ts

    print("Pixhawk: waiting for heartbeat...")
    pixhawk.wait_heartbeat()
    print("Pixhawk connected!")

    ts = pixhawk.target_system
    tc = pixhawk.target_component

    print("Configuring Pixhawk for demo mode...")
    # BRD_SAFETY_DEFLT (newer ArduPilot) replaced BRD_SAFETYENABLE: 0 = boot with
    # safety off so motor outputs are live without holding the physical button.
    # Only takes effect at the next autopilot boot.
    pixhawk.mav.param_set_send(ts, tc, b'BRD_SAFETY_DEFLT', 0,
                               mavutil.mavlink.MAV_PARAM_TYPE_INT8)
    pixhawk.mav.param_set_send(ts, tc, b'ARMING_CHECK', 0,
                               mavutil.mavlink.MAV_PARAM_TYPE_INT32)
    pixhawk.mav.param_set_send(ts, tc, b'FS_THR_ENABLE', 0,
                               mavutil.mavlink.MAV_PARAM_TYPE_INT32)

    print(f"Safety limits: slewrate={MOTOR_SLEWRATE}%/s  wp_speed={WP_SPEED_MS}m/s")
    # MOT_SLEWRATE: throttle ramp rate in %/sec. Prevents 0→100% shock on mission start.
    pixhawk.mav.param_set_send(ts, tc, b'MOT_SLEWRATE', float(MOTOR_SLEWRATE),
                               mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
    # WP_SPEED: max navigation speed in AUTO mode (m/s).
    pixhawk.mav.param_set_send(ts, tc, b'WP_SPEED', float(WP_SPEED_MS),
                               mavutil.mavlink.MAV_PARAM_TYPE_REAL32)
    # Reset MOT_THR_MAX to 100% on every boot so the param isn't stuck at
    # whatever value slow_mode was left at last session. Slow mode is a
    # runtime toggle, not a persistent config.
    set_slow_mode(False)

    while True:
        try:
            # Yield to mission upload — don't consume MAVLink messages during handshake
            if mission_uploading.is_set():
                time.sleep(0.1)
                continue

            with pixhawk_lock:
                msg = pixhawk.recv_match(blocking=True, timeout=0.1)

            if not msg:
                continue

            msg_type = msg.get_type()

            if msg_type == "GLOBAL_POSITION_INT":
                lat = msg.lat / 1e7
                lon = msg.lon / 1e7
                # Feed the swarm coordinator so the leader can broadcast
                # this boat's GPS, and the follower paths know we have a fix.
                swarm.feed_pixhawk_gps(lat, lon, heading, gps_fix_type, int(time.time()))
            elif msg_type == "ATTITUDE":
                heading = (math.degrees(msg.yaw) + 360) % 360
                roll_deg = math.degrees(msg.roll)
                pitch_deg = math.degrees(msg.pitch)
            elif msg_type == "NAV_CONTROLLER_OUTPUT":
                nav_target_bearing  = msg.target_bearing
                nav_desired_bearing = msg.nav_bearing
                nav_wp_dist_m       = msg.wp_dist
                nav_xtrack_error_m  = msg.xtrack_error
            elif msg_type == "VFR_HUD":
                speed = msg.groundspeed
                throttle_pct = msg.throttle  # -100..100 (sign = direction on rovers)
            elif msg_type == "HEARTBEAT":
                armed = (msg.base_mode & 0b10000000) != 0
                mm = pixhawk.mode_mapping()
                if mm:
                    mode = {v: k for k, v in mm.items()}.get(msg.custom_mode, str(msg.custom_mode))
                last_heartbeat_ts = time.time()
            elif msg_type == "STATUSTEXT":
                print("PIXHAWK:", msg.text)
                last_statustext = msg.text
                last_statustext_sev = msg.severity
            elif msg_type == "MISSION_CURRENT":
                current_wp = msg.seq
            elif msg_type == "HOME_POSITION":
                if not home_set:
                    print("[MISSION] HOME set — EKF/GPS ready; AUTO mode unlocked")
                home_set = True
            elif msg_type == "SERVO_OUTPUT_RAW":
                # Rover: SERVO1=steering, SERVO3=throttle (see Pixhawk params).
                servo1_pwm = msg.servo1_raw
                servo2_pwm = msg.servo2_raw
                servo3_pwm = msg.servo3_raw
                servo4_pwm = msg.servo4_raw
            elif msg_type == "SYS_STATUS":
                # voltage_battery: mV, current_battery: 10 mA units (-1 if unknown)
                battery_voltage = msg.voltage_battery / 1000.0
                battery_current = (msg.current_battery / 100.0) if msg.current_battery != -1 else 0.0
                battery_remaining = msg.battery_remaining  # -1 if unknown
            elif msg_type == "BATTERY_STATUS":
                # Preferred over SYS_STATUS when multi-battery. voltages[0] in mV.
                if msg.voltages and msg.voltages[0] != 0xFFFF:
                    battery_voltage = msg.voltages[0] / 1000.0
                if msg.current_battery != -1:
                    battery_current = msg.current_battery / 100.0
                if msg.battery_remaining != -1:
                    battery_remaining = msg.battery_remaining
            elif msg_type == "GPS_RAW_INT":
                gps_fix_type = msg.fix_type
                gps_sats = msg.satellites_visible
                gps_hdop = msg.eph / 100.0  # eph is cm; HDOP * 100
                last_gps_ts = time.time()
            elif msg_type == "EKF_STATUS_REPORT":
                ekf_compass_variance = msg.compass_variance
                ekf_pos_variance = msg.pos_horiz_variance
                ekf_velocity_variance = msg.velocity_variance

        except Exception as e:
            print("Pixhawk error:", e)

# =====================================================
# TELEMETRY SERVER
# =====================================================
async def telemetry_handler(websocket):
    telemetry_clients.add(websocket)
    print("Telemetry client connected")
    try:
        while True:
            await asyncio.sleep(100)
    except Exception as e:
        print("Telemetry error:", e)
    finally:
        telemetry_clients.discard(websocket)
        print("Telemetry client disconnected")

# =====================================================
# CONTROL SERVER (ARM / DISARM / THROTTLE / MISSION)
# =====================================================
async def control_handler(websocket):
    print("Control client connected")
    try:
        async for message in websocket:
            msg = message.strip()
            print("CONTROL:", msg)

            # JSON commands (mission control)
            try:
                data = json.loads(msg)
                action = data.get("action")

                if action == "upload_mission":
                    waypoints = data.get("waypoints", [])
                    loop = asyncio.get_event_loop()
                    success, result = await loop.run_in_executor(
                        None, upload_mission_sync, waypoints
                    )
                    await websocket.send(json.dumps({
                        "status": "ok" if success else "error",
                        "message": result
                    }))
                    continue

                elif action == "go":
                    loop = asyncio.get_event_loop()
                    success, result = await loop.run_in_executor(
                        None, start_mission
                    )
                    await websocket.send(json.dumps({
                        "status": "ok" if success else "error",
                        "message": result
                    }))
                    continue

                elif action == "hold":
                    set_mode("HOLD")
                    await websocket.send(json.dumps({
                        "status": "ok",
                        "message": "HOLD mode set"
                    }))
                    continue

                elif action == "resume":
                    set_mode("AUTO")
                    await websocket.send(json.dumps({
                        "status": "ok",
                        "message": "Resuming mission"
                    }))
                    continue

                elif action == "abort":
                    disarm_vehicle()
                    await websocket.send(json.dumps({
                        "status": "ok",
                        "message": "Mission aborted — disarmed"
                    }))
                    continue

                elif action == "rth":
                    set_mode("RTL")
                    await websocket.send(json.dumps({
                        "status": "ok",
                        "message": "Returning to home (RTL)"
                    }))
                    continue

                elif action == "slow_mode":
                    enabled = bool(data.get("enabled", False))
                    set_slow_mode(enabled)
                    await websocket.send(json.dumps({
                        "status": "ok",
                        "message": f"Slow mode {'ON (30% cap)' if enabled else 'OFF (100%)'}"
                    }))
                    continue

                elif action == "gcs_heartbeat":
                    # Browser keepalive. No response needed — watchdog thread
                    # reads the timestamp. Silent by design to avoid WS spam.
                    global last_gcs_heartbeat_ts
                    last_gcs_heartbeat_ts = time.time()
                    continue

                elif action == "set_watchdog":
                    global GCS_WATCHDOG_TIMEOUT, GCS_WATCHDOG_ACTION
                    t = data.get("timeout")
                    a = data.get("failsafe_action")
                    if t is not None:
                        try:
                            GCS_WATCHDOG_TIMEOUT = max(2.0, float(t))
                        except (TypeError, ValueError):
                            pass
                    if a in ("HOLD", "RTL", "DISARM"):
                        GCS_WATCHDOG_ACTION = a
                    await websocket.send(json.dumps({
                        "status": "ok",
                        "message": f"Watchdog: timeout={GCS_WATCHDOG_TIMEOUT}s action={GCS_WATCHDOG_ACTION}"
                    }))
                    continue

                elif action == "estop":
                    # Emergency stop — always disarms, regardless of watchdog config.
                    # Logged prominently so the post-mortem is obvious.
                    print("[ESTOP] Operator pressed emergency stop")
                    disarm_vehicle()
                    await websocket.send(json.dumps({
                        "status": "ok",
                        "message": "E-STOP: vehicle disarmed"
                    }))
                    continue

                elif action == "admin_login":
                    ok, info = admin_login(data.get("password", ""))
                    await websocket.send(json.dumps({
                        "status": "ok" if ok else "error",
                        "message": info if not ok else "admin ok",
                        "token":   info if ok else None,
                    }))
                    continue

                elif action == "admin_logout":
                    admin_logout(data.get("token"))
                    await websocket.send(json.dumps({"status": "ok", "message": "logged out"}))
                    continue

                elif action == "admin_check":
                    ok = admin_check(data.get("token"))
                    await websocket.send(json.dumps({"status": "ok" if ok else "error",
                                                     "message": "valid" if ok else "invalid"}))
                    continue

                elif action == "manual_rc":
                    # Admin-gated RC override. ch1=steering, ch3=throttle (ArduRover
                    # convention — matches SERVO1_FUNCTION=26, SERVO3_FUNCTION=70).
                    # Values are PWM µs (1100..1900, 1500 = neutral). 65535 disables
                    # override on that channel.
                    if not admin_check(data.get("token")):
                        await websocket.send(json.dumps({"status": "error", "message": "admin required"}))
                        continue
                    try:
                        ch1 = int(data.get("ch1", 65535))
                        ch3 = int(data.get("ch3", 65535))
                    except (TypeError, ValueError):
                        await websocket.send(json.dumps({"status": "error", "message": "invalid channel values"}))
                        continue
                    # Clamp to the documented safe PWM range unless explicitly releasing.
                    def _clamp(v):
                        return v if v == 65535 else max(1000, min(2000, v))
                    ch1, ch3 = _clamp(ch1), _clamp(ch3)
                    with pixhawk_lock:
                        pixhawk.mav.rc_channels_override_send(
                            pixhawk.target_system, pixhawk.target_component,
                            ch1, 65535, ch3, 65535, 65535, 65535, 65535, 65535
                        )
                    # Silent by default — this arrives at up to 20 Hz during joystick use.
                    continue

                elif action == "set_mode":
                    # Admin-gated generic mode setter — used by the manual tab.
                    # Public modes (HOLD/RTL/AUTO) already have dedicated handlers;
                    # this covers the ones the operator might want during recovery
                    # (MANUAL/LOITER/ACRO/STEERING/GUIDED/...).
                    if not admin_check(data.get("token")):
                        await websocket.send(json.dumps({"status": "error", "message": "admin required"}))
                        continue
                    m = (data.get("mode") or "").upper()
                    if not m:
                        await websocket.send(json.dumps({"status": "error", "message": "missing mode"}))
                        continue
                    set_mode(m)
                    await websocket.send(json.dumps({"status": "ok", "message": f"Mode set: {m}"}))
                    continue

                elif action == "upload_fence":
                    # Polygon upload. Returns a single ack with success/message.
                    polygon = data.get("polygon", [])
                    action_type = data.get("fence_action", "HOLD")
                    rlat = data.get("return_lat", polygon[0][0] if polygon else 0.0)
                    rlon = data.get("return_lon", polygon[0][1] if polygon else 0.0)
                    loop = asyncio.get_event_loop()
                    success, result = await loop.run_in_executor(
                        None, upload_fence_sync, polygon, rlat, rlon, action_type
                    )
                    await websocket.send(json.dumps({
                        "status": "ok" if success else "error",
                        "message": result,
                    }))
                    continue

                elif action == "fence_enable":
                    set_fence_enable(bool(data.get("enabled", False)))
                    await websocket.send(json.dumps({
                        "status": "ok",
                        "message": f"Fence {'enabled' if data.get('enabled') else 'disabled'}"
                    }))
                    continue

                elif action == "swarm_enable":
                    if not admin_check(data.get("token")):
                        await websocket.send(json.dumps({"status": "error", "message": "admin required"}))
                        continue
                    on = bool(data.get("on", False))
                    # Mock-mode skips the Pixhawk pre-arm gates so the dev
                    # box can drive the GUI end-to-end without a flight
                    # controller attached.
                    mock_mode = bool(os.environ.get("AQUABOT_ESP32_TCP"))
                    if on and not mock_mode:
                        if gps_fix_type < 3:
                            await websocket.send(json.dumps({
                                "status": "error",
                                "message": "Swarm mode refused: GPS needs 3D fix",
                            }))
                            continue
                        if not home_set:
                            await websocket.send(json.dumps({
                                "status": "error",
                                "message": "Swarm mode refused: HOME not set",
                            }))
                            continue
                    swarm.set_enabled(on)
                    await websocket.send(json.dumps({
                        "status": "ok",
                        "message": f"Swarm mode {'ON' if on else 'OFF'}",
                    }))
                    continue

                elif action == "mock_set_scenario":
                    if not admin_check(data.get("token")):
                        await websocket.send(json.dumps({"status": "error", "message": "admin required"}))
                        continue
                    scenario = (data.get("scenario") or "").strip()
                    ok = _spawn_mock_subprocess(scenario=scenario)
                    await websocket.send(json.dumps({
                        "status": "ok" if ok else "error",
                        "message": (f"Mock scenario set to {scenario}" if ok
                                    else f"Unknown scenario {scenario}"),
                    }))
                    continue

                elif action == "mock_set_members":
                    if not admin_check(data.get("token")):
                        await websocket.send(json.dumps({"status": "error", "message": "admin required"}))
                        continue
                    n = int(data.get("members", 3))
                    ok = _spawn_mock_subprocess(members=n)
                    await websocket.send(json.dumps({
                        "status": "ok" if ok else "error",
                        "message": (f"Simulating {_mock_members}-boat swarm" if ok
                                    else "Failed to set swarm size"),
                    }))
                    continue

                elif action == "swarm_set_pattern":
                    # Pattern + spacing are configuration, not motion.
                    # No admin needed — anyone can rearrange the formation
                    # before the leader actually arms swarm mode.
                    pattern = (data.get("pattern") or "none").lower()
                    spacing = int(data.get("spacing_mm", 2000))
                    swarm.set_pattern(pattern, spacing)
                    await websocket.send(json.dumps({
                        "status": "ok",
                        "message": f"Pattern: {pattern}, spacing {spacing/1000:.1f} m",
                    }))
                    continue

                elif action == "manual_release":
                    # Drop all RC overrides so Pixhawk's autonomous or RC inputs take back over.
                    if not admin_check(data.get("token")):
                        await websocket.send(json.dumps({"status": "error", "message": "admin required"}))
                        continue
                    with pixhawk_lock:
                        pixhawk.mav.rc_channels_override_send(
                            pixhawk.target_system, pixhawk.target_component,
                            65535, 65535, 65535, 65535, 65535, 65535, 65535, 65535
                        )
                    await websocket.send(json.dumps({"status": "ok", "message": "RC override released"}))
                    continue

            except (json.JSONDecodeError, TypeError):
                pass  # not JSON, fall through to string commands

            # Plain string commands (existing ARM / DISARM / throttle)
            if msg == "ARM":
                arm_vehicle()
                continue

            if msg == "DISARM":
                disarm_vehicle()
                continue

            try:
                percent = float(msg)
                set_throttle(percent)
            except ValueError:
                print("Invalid control:", msg)

    except Exception as e:
        print("Control error:", e)

# =====================================================
# BROADCAST LOOP
# =====================================================
async def telemetry_broadcast():
    """
    1 Hz fan-out of vehicle state to all connected GUI clients.

    Link-age fields (*_AGE_MS) are seconds-since-last-message converted to ms.
    A stale age (e.g. HB_AGE_MS > 3000) is the GUI's signal that the underlying
    link is gone even though the websocket is still open.
    """
    while True:
        global last_statustext
        now = time.time()
        timestamp = datetime.now(tucson).strftime("%H:%M:%S")

        hb_age_ms = int((now - last_heartbeat_ts) * 1000) if last_heartbeat_ts else -1
        gps_age_ms = int((now - last_gps_ts) * 1000) if last_gps_ts else -1
        esp32_age_ms = int((now - last_esp32_ts) * 1000) if last_esp32_ts else -1
        gcs_age_ms = int((now - last_gcs_heartbeat_ts) * 1000) if last_gcs_heartbeat_ts else -1

        data = {
            # Legacy keys — keep identical shape/names so existing dashboard code
            # continues to work without modification.
            "TIME": timestamp,
            "LAT": lat,
            "LON": lon,
            "HEAD": heading,
            "SPD": speed,
            "TEMP": temp,
            "SAL": sal,
            "PH": ph,
            "ARMED": armed,
            "MODE": mode,
            "STATUS": last_statustext,
            "STATUS_SEV": last_statustext_sev,
            "SLOW_MODE": slow_mode_enabled,
            # New in Phase A.
            "CURRENT_WP": current_wp,
            "WP_TOTAL": wp_total,
            "HOME_SET": home_set,
            "THROTTLE_PCT": throttle_pct,
            "SERVO1": servo1_pwm,
            "SERVO2": servo2_pwm,
            "SERVO3": servo3_pwm,
            "SERVO4": servo4_pwm,
            "BAT_V": round(battery_voltage, 2),
            "BAT_A": round(battery_current, 2),
            "BAT_PCT": battery_remaining,
            "GPS_FIX": gps_fix_type,
            "GPS_SATS": gps_sats,
            "GPS_HDOP": round(gps_hdop, 2),
            "EKF_COMPASS_VAR": round(ekf_compass_variance, 3),
            "EKF_POS_VAR": round(ekf_pos_variance, 3),
            "EKF_VEL_VAR": round(ekf_velocity_variance, 3),
            # Attitude
            "ROLL":  round(roll_deg, 1),
            "PITCH": round(pitch_deg, 1),
            # Navigation: where the autopilot thinks the next waypoint is and
            # what it's trying to do about it. NAV_CONTROLLER_OUTPUT-derived.
            "NAV_TARGET_BEARING":  round(nav_target_bearing, 1),
            "NAV_DESIRED_BEARING": round(nav_desired_bearing, 1),
            "NAV_WP_DIST_M":       int(nav_wp_dist_m),
            "NAV_XTRACK_ERROR_M":  round(nav_xtrack_error_m, 2),
            # Heading error: how many degrees off from target_bearing the
            # boat's actual heading is, normalised to [-180, +180].
            "NAV_HEADING_ERROR":   round(((nav_target_bearing - heading + 540) % 360) - 180, 1),
            # Servo deflection as a percentage of full travel from neutral
            # 1500 µs (so -100% = full left/reverse, +100% = full right/forward).
            "STEER_DEFLECTION_PCT":    round((servo1_pwm - 1500) / 4.0, 1) if servo1_pwm else 0,
            "THROTTLE_DEFLECTION_PCT": round((servo3_pwm - 1500) / 4.0, 1) if servo3_pwm else 0,
            "HB_AGE_MS": hb_age_ms,
            "GPS_AGE_MS": gps_age_ms,
            "ESP32_AGE_MS": esp32_age_ms,
            "GCS_AGE_MS": gcs_age_ms,
            "WATCHDOG_TIMEOUT": GCS_WATCHDOG_TIMEOUT,
            "WATCHDOG_ACTION": GCS_WATCHDOG_ACTION,
            "FAILSAFE_TRIPPED": failsafe_tripped,
            "SWARM": swarm.snapshot(),
            "MOCK_MODE": bool(os.environ.get("AQUABOT_ESP32_TCP")),
            "MOCK_SCENARIO": _mock_scenario,
            "MOCK_SCENARIOS": list(_mock_available_scenarios),
            "MOCK_MEMBERS": _mock_members,
        }
        last_statustext = ""
        message = json.dumps(data)
        for client in list(telemetry_clients):
            try:
                await client.send(message)
            except:
                telemetry_clients.discard(client)

        # Legacy CSV — unchanged schema so anything parsing it keeps working.
        file.write(f"{timestamp},{lat},{lon},{heading},{speed},{temp},{sal},{ph}\n")
        file.flush()

        # Full black-box — one JSON object per line, flushed each tick.
        blackbox.write(message + "\n")
        blackbox.flush()

        await asyncio.sleep(1)

# =====================================================
# START SERVERS
# =====================================================
async def start_telemetry():
    await websockets.serve(telemetry_handler, "0.0.0.0", TELEMETRY_PORT)
    await websockets.serve(control_handler, "0.0.0.0", CONTROL_PORT)
    print(f"Telemetry running on {TELEMETRY_PORT}")
    print(f"Control running on {CONTROL_PORT}")
    # Signal main thread that both sockets are bound. Without this,
    # Flask can start serving index.html before the dashboard's WS
    # endpoints exist — browser sees permanently-red indicators.
    telemetry_ready.set()
    asyncio.create_task(telemetry_broadcast())
    await asyncio.Future()

def run_async():
    asyncio.run(start_telemetry())

# =====================================================
# MAIN
# =====================================================
_mock_proc = None
_mock_scenario = os.environ.get("AQUABOT_MOCK_SCENARIO", "follower_3boat")
_mock_members = 3
_mock_lock = threading.Lock()
_mock_available_scenarios = (
    "follower_3boat", "leader_3boat", "leader_silence_test", "stop_test"
)


def _spawn_mock_subprocess(scenario=None, members=None):
    """Start (or restart) the mock ESP32 subprocess with the given config.
    Either argument can be None to keep the current value.
    Idempotent: kills any existing one first. Returns True on success."""
    global _mock_proc, _mock_scenario, _mock_members
    s = scenario if scenario is not None else _mock_scenario
    m = members if members is not None else _mock_members
    if s not in _mock_available_scenarios:
        return False
    m = max(2, min(50, int(m)))
    with _mock_lock:
        if _mock_proc is not None:
            try:
                _mock_proc.terminate()
                _mock_proc.wait(timeout=3)
            except Exception:
                try: _mock_proc.kill()
                except Exception: pass
            _mock_proc = None
        try:
            _mock_proc = subprocess.Popen(
                [sys.executable, "-u", "tools/swarm_mock.py",
                 "--scenario", s, "--members", str(m)],
                stdout=sys.stdout, stderr=sys.stderr,
            )
            _mock_scenario = s
            _mock_members = m
            print(f"[MOCK] spawned scenario={s} members={m} pid={_mock_proc.pid}")
            return True
        except Exception as e:
            print(f"[MOCK] spawn error: {e}")
            return False


def _mock_pixhawk_feeder():
    """Dev-only thread: when AQUABOT_ESP32_TCP is set we typically don't have
    a real Pixhawk on UDP 14552. Park the local boat ~5m east of the leader
    so the markers don't overlap. When swarm mode is enabled and a target
    is known, lerp the boat toward its assigned slot at 0.5 m/s — that way
    the operator can see the simulated swarm actually move."""
    global lat, lon, heading, gps_fix_type, gps_sats, home_set, last_heartbeat_ts, last_gps_ts, mode, armed
    lat = 33.42746
    lon = -111.93584 + (5.0 / (111111.0 * math.cos(math.radians(33.42746))))
    heading = 270.0
    gps_fix_type = 3
    gps_sats = 12
    home_set = True
    mode = "GUIDED"
    armed = True

    TICK_S = 0.2          # smoother motion than 1 Hz
    SPEED_MS = 0.5        # 0.5 m/s — matches the WP_SPEED_MS default

    while True:
        snap = swarm.snapshot()
        target = snap.get('target_latlon')
        if snap.get('enabled') and target and snap.get('role') == 'follower':
            tlat, tlon, _thead = target
            # Compute great-circle delta in meters using small-angle approximation.
            dlat_m = (tlat - lat) * 111111.0
            dlon_m = (tlon - lon) * 111111.0 * math.cos(math.radians(lat))
            dist = math.hypot(dlat_m, dlon_m)
            if dist > 0.05:
                step = min(SPEED_MS * TICK_S, dist)
                lat += (dlat_m / dist) * step / 111111.0
                lon += (dlon_m / dist) * step / (111111.0 * math.cos(math.radians(lat)))
                # Heading = bearing toward target (deg clockwise from north)
                heading = (math.degrees(math.atan2(dlon_m, dlat_m)) + 360) % 360

        last_heartbeat_ts = time.time()
        last_gps_ts = time.time()
        swarm.feed_pixhawk_gps(lat, lon, heading, gps_fix_type, int(time.time()))
        time.sleep(TICK_S)


if __name__ == "__main__":
    swarm.start()
    threading.Thread(target=run_async, daemon=True).start()
    if os.environ.get("AQUABOT_ESP32_TCP"):
        print("[MOCK] AQUABOT_ESP32_TCP set — using fake Pixhawk feed")
        threading.Thread(target=_mock_pixhawk_feeder, daemon=True).start()
        # Also spawn the mock ESP32 subprocess so the user doesn't have to
        # run a second terminal. Default scenario can be changed from the GUI.
        _spawn_mock_subprocess(_mock_scenario)
    else:
        threading.Thread(target=read_pixhawk, daemon=True).start()
    threading.Thread(target=read_esp32, daemon=True).start()
    threading.Thread(target=gcs_watchdog, daemon=True).start()
    if not telemetry_ready.wait(timeout=10):
        print("⚠️ Telemetry servers didn't signal ready in 10s — starting Flask anyway")
    app.run(host="0.0.0.0", port=5000)
