import asyncio
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

pixhawk_lock = threading.Lock()
mission_uploading = threading.Event()

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

# ESP32
try:
    ser = serial.Serial('/dev/ttyACM1', 115200, timeout=1)
    print('[ESP32] Serial connected on /dev/ttyACM1')
except serial.SerialException:
    ser = None
    print('[ESP32] /dev/ttyACM1 not found — sensor data unavailable')

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

def upload_mission_sync(waypoints_latlon):
    """
    Upload a mission to the Pixhawk via MAVLink.
    waypoints_latlon: list of [lat, lon] pairs (floats)
    Returns (success: bool, message: str)
    """
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
                        return True, f"Mission uploaded: {len(waypoints_latlon)} waypoints + RTL"
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
armed = False
mode = "UNKNOWN"
last_statustext = ""
last_statustext_sev = 6  # MAV_SEVERITY: 0=EMERGENCY..6=INFO
current_wp = 0  # MAV_SEVERITY: 0=EMERGENCY..6=INFO
home_set = False  # flips True on first HOME_POSITION — AUTO mode requires this

temp = 0
sal = 0
ph = 0

# CSV logging
tucson = pytz.timezone("America/Phoenix")
start_time = datetime.now(tucson).strftime("%Y-%m-%d_%H-%M-%S")
file = open(f"/home/mayra/videos/telemetry_{start_time}.csv", "a")
file.write("TIME,LAT,LON,HEAD,SPD,TEMP,SAL,PH\n")
file.flush()

# =====================================================
# FLASK
# =====================================================
app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")

# =====================================================
# ESP32 THREAD
# =====================================================
def read_esp32():
    global temp, sal, ph

    if ser is None:
        print('[ESP32] No serial connection — read_esp32 thread idle')
        return

    while True:
        try:
            line = ser.readline().decode('utf-8', errors='ignore').strip()
            if line.startswith("TEMP:"):
                print("ESP32:", line)
                parts = line.split(',')
                for p in parts:
                    if ':' in p:
                        k, v = p.split(':')
                        if k == "TEMP":
                            temp = float(v)
                        elif k == "SAL":
                            sal = float(v)
                        elif k == "PH":
                            ph = float(v)
        except Exception as e:
            print("ESP32 error:", e)

# =====================================================
# PIXHAWK THREAD
# =====================================================
def read_pixhawk():
    global lat, lon, heading, speed, armed, mode, last_statustext, last_statustext_sev, current_wp, home_set

    print("Pixhawk: waiting for heartbeat...")
    pixhawk.wait_heartbeat()
    print("Pixhawk connected!")

    ts = pixhawk.target_system
    tc = pixhawk.target_component

    print("Configuring Pixhawk for demo mode...")
    pixhawk.mav.param_set_send(ts, tc, b'BRD_SAFETYENABLE', 0,
                               mavutil.mavlink.MAV_PARAM_TYPE_INT32)
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
            elif msg_type == "ATTITUDE":
                heading = (math.degrees(msg.yaw) + 360) % 360
            elif msg_type == "VFR_HUD":
                speed = msg.groundspeed
            elif msg_type == "HEARTBEAT":
                armed = (msg.base_mode & 0b10000000) != 0
                mm = pixhawk.mode_mapping()
                if mm:
                    mode = {v: k for k, v in mm.items()}.get(msg.custom_mode, str(msg.custom_mode))
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
    while True:
        global last_statustext
        timestamp = datetime.now(tucson).strftime("%H:%M:%S")
        data = {
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
            "SLOW_MODE": slow_mode_enabled
        }
        last_statustext = ""
        message = json.dumps(data)
        for client in list(telemetry_clients):
            try:
                await client.send(message)
            except:
                telemetry_clients.discard(client)
        file.write(f"{timestamp},{lat},{lon},{heading},{speed},{temp},{sal},{ph}\n")
        file.flush()
        print("SENT:", data)
        await asyncio.sleep(3)

# =====================================================
# START SERVERS
# =====================================================
async def start_telemetry():
    await websockets.serve(telemetry_handler, "0.0.0.0", TELEMETRY_PORT)
    await websockets.serve(control_handler, "0.0.0.0", CONTROL_PORT)
    print(f"Telemetry running on {TELEMETRY_PORT}")
    print(f"Control running on {CONTROL_PORT}")
    asyncio.create_task(telemetry_broadcast())
    await asyncio.Future()

def run_async():
    asyncio.run(start_telemetry())

# =====================================================
# MAIN
# =====================================================
if __name__ == "__main__":
    threading.Thread(target=run_async, daemon=True).start()
    threading.Thread(target=read_pixhawk, daemon=True).start()
    threading.Thread(target=read_esp32, daemon=True).start()
    app.run(host="0.0.0.0", port=5000)
