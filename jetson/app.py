import asyncio
import threading
import websockets
from flask import Flask, render_template
import serial
import json
from datetime import datetime
import pytz
from pymavlink import mavutil
import math

pixhawk_lock = threading.Lock()
# =====================================================
# CONFIG
# =====================================================
TELEMETRY_PORT = 8766
telemetry_clients = set()

# ESP32
ser = serial.Serial('/dev/ttyACM1', 115200, timeout=1)

# Pixhawk
pixhawk = mavutil.mavlink_connection('/dev/ttyACM0', baud=57600)

# =====================================================
# MOTOR CONTROL
# =====================================================
current_throttle = 0

def set_throttle(percent):

    pwm = int(1100 + (percent / 100.0) * 800)

    print(f"🚤 Throttle {percent}% → PWM {pwm}")

    with pixhawk_lock:
        pixhawk.mav.rc_channels_override_send(
            pixhawk.target_system,
            pixhawk.target_component,
            65535,  # CH1
            65535,  # CH2
            pwm,    # ✅ CH3 (THROTTLE)
            65535,  # CH4
            65535,  # CH5
            65535,  # CH6
            65535,  # CH7
            65535   # CH8
        )

def set_mode(mode):
    print(f"🔁 Setting mode: {mode}")

    mode_id = pixhawk.mode_mapping().get(mode)

    if mode_id is None:
        print("❌ Mode not found")
        return

    with pixhawk_lock:
        pixhawk.mav.set_mode_send(
            pixhawk.target_system,
            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            mode_id
        )

def arm_vehicle():
    print("🔓 ARMING VEHICLE")

    set_mode("MANUAL")

    with pixhawk_lock:
        pixhawk.mav.command_long_send(
            pixhawk.target_system,
            pixhawk.target_component,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            0,
            1, 0, 0, 0, 0, 0, 0
        )

def disarm_vehicle():
    print("🔒 DISARMING VEHICLE")

    with pixhawk_lock:
        pixhawk.mav.command_long_send(
            pixhawk.target_system,
            pixhawk.target_component,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
            0,
            0, 0, 0, 0, 0, 0, 0
        )
# GLOBAL DATA (shared)
lat = 0
lon = 0
heading = 0
speed = 0
armed = False

temp = 0
sal = 0
ph = 0

# Recording
tucson = pytz.timezone("America/Phoenix")
start_time = datetime.now(tucson).strftime("%Y-%m-%d_%H-%M-%S")

file = open(f"/home/mayra/videos/telemetry_{start_time}.csv", "a")

# ✅ ADD HEADER (ONLY ONCE)
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
# =====================================================
# PIXHAWK THREAD
# =====================================================
def read_pixhawk():
    global lat, lon, heading, speed, armed

    print("Pixhawk: waiting for heartbeat...")
    pixhawk.wait_heartbeat()
    print("Pixhawk connected!")

    # 🔥 CONFIG FOR DEMO MODE (ADD HERE)
    print("⚙️ Configuring Pixhawk for demo mode...")

    # Disable safety switch
    pixhawk.mav.param_set_send(
        pixhawk.target_system,
        pixhawk.target_component,
        b'BRD_SAFETYENABLE',
        0,
        mavutil.mavlink.MAV_PARAM_TYPE_INT32
    )

    # Disable all arming checks
    pixhawk.mav.param_set_send(
        pixhawk.target_system,
        pixhawk.target_component,
        b'ARMING_CHECK',
        0,
        mavutil.mavlink.MAV_PARAM_TYPE_INT32
    )

    # Disable radio failsafe
    pixhawk.mav.param_set_send(
        pixhawk.target_system,
        pixhawk.target_component,
        b'FS_THR_ENABLE',
        0,
        mavutil.mavlink.MAV_PARAM_TYPE_INT32
    )

    while True:
        try:
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

            elif msg_type == "STATUSTEXT":
                print("PIXHAWK:", msg.text)

        except Exception as e:
            print("Pixhawk error:", e)

# =====================================================
# TELEMETRY SERVER
# =====================================================
async def telemetry_handler(websocket):
    telemetry_clients.add(websocket)
    print("📊 Telemetry client connected")

    try:
        while True:
            await asyncio.sleep(100)  # keeps connection alive

    except Exception as e:
        print("Telemetry error:", e)

    finally:
        telemetry_clients.remove(websocket)
        print("❌ Telemetry client disconnected")
# =====================================================
# CONTROL SERVER (THROTTLE + ARM)
# =====================================================
CONTROL_PORT = 8770

async def control_handler(websocket):
    print("🎮 Control client connected")

    try:
        while True:
            try:
                message = await websocket.recv()
                msg = message.strip()

                print("CONTROL:", msg)

                # 🔐 ARM / DISARM
                if msg == "ARM":
                    arm_vehicle()
                    continue

                if msg == "DISARM":
                    disarm_vehicle()
                    continue

                # 🚤 THROTTLE
                try:
                    percent = float(msg)
                    set_throttle(percent)
                    continue   # ✅ prevents "Invalid control" bug
                except ValueError:
                    print("Invalid control:", msg)

            except Exception as inner_e:
                print("⚠️ Command error:", inner_e)

    except Exception as e:
        print("❌ Control connection closed:", e)

    finally:
        print("❌ Control client disconnected")

# =====================================================
# FLASK
# =====================================================
app = Flask(__name__)

@app.route("/")
def index():
    return render_template("index.html")



# =====================================================
# BROADCAST LOOP (SYNCED)
# =====================================================
async def telemetry_broadcast():
    while True:

        # ✅ FIXED: create Tucson timestamp here
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
            "ARMED": armed
        }

        message = json.dumps(data)

        # SEND TO GUI
        for client in list(telemetry_clients):
            try:
                await client.send(message)
            except:
                telemetry_clients.remove(client)

        # SAVE (synced with same timestamp)
        file.write(f"{timestamp},{lat},{lon},{heading},{speed},{temp},{sal},{ph}\n")
        file.flush()

        print("SENT:", data)

        await asyncio.sleep(3)

# =====================================================
# START SERVER (TELEMETRY + CONTROL)
# =====================================================
CONTROL_PORT = 8770

async def control_handler(websocket):
    print("🎮 Control client connected")

    try:
        async for message in websocket:
            msg = message.strip()
            print("CONTROL:", msg)

            if msg == "ARM":
                arm_vehicle()
                continue

            if msg == "DISARM":
                disarm_vehicle()
                continue

            try:
                percent = float(msg)
                set_throttle(percent)
            except:
                print("Invalid control:", msg)

    except Exception as e:
        print("Control error:", e)


async def start_telemetry():
    await websockets.serve(
        telemetry_handler, "0.0.0.0", TELEMETRY_PORT
    )

    await websockets.serve(
        control_handler, "0.0.0.0", CONTROL_PORT
    )

    print("📡 Telemetry running on 8766")
    print("🎮 Control running on 8770")

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
