from pymavlink import mavutil
import math

master = mavutil.mavlink_connection('/dev/ttyACM0', baud=57600)

print("Waiting for heartbeat...")
master.wait_heartbeat()
print("Connected to Pixhawk!")

while True:
    msg = master.recv_match(blocking=True, timeout=1)

    if not msg:
        continue

    msg_type = msg.get_type()

    if msg_type == "GLOBAL_POSITION_INT":
        lat = msg.lat / 1e7
        lon = msg.lon / 1e7
        print("GPS:", lat, lon)

    elif msg_type == "GPS_RAW_INT":
        print("RAW GPS fix:", msg.fix_type)

    elif msg_type == "ATTITUDE":
        yaw = (math.degrees(msg.yaw) + 360) % 360
        print("Heading:", yaw)

    elif msg_type == "VFR_HUD":
        print("Speed:", msg.groundspeed)
