#!/usr/bin/env python3
from pymavlink import mavutil
import math
import asyncio
import json
import cv2
import numpy as np
import websockets
import serial
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiortc.mediastreams import VideoFrame
from datetime import datetime

Gst.init(None)

# ============================================
# SERVERS
# ============================================

SIGNALING_SERVER = "ws://100.76.1.26:8765"
TELEMETRY_SERVER = "ws://100.76.1.26:8766"

# ============================================
# GLOBAL STATE
# ============================================

zoom_level = 1.0
is_recording = False
video_writer = None

# Telemetry logging globals
telemetry_file = None
telemetry_filename = None

# ============================================
# TELEMETRY SERIAL
# ============================================

try:
    ser = serial.Serial(
        '/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0',
        115200,
        timeout=0
    )
    print("Telemetry serial connected.")
except Exception as e:
    ser = None
    print("⚠️ Telemetry serial not found:", e)

# ============================================
# PIXHAWK MAVLINK
# ============================================

try:
    mav = mavutil.mavlink_connection('/dev/ttyACM0', baud=57600)
    print("Waiting for Pixhawk heartbeat...")
    # Bounded wait so this module import can't hang forever when the
    # Pixhawk USB hasn't enumerated yet on boot. Telemetry fields will
    # just be blank until mav is (re)opened — better than blocking
    # webrtc startup and flapping under systemd Restart=.
    hb = mav.wait_heartbeat(timeout=5)
    if hb is None:
        mav = None
        print("⚠️ Pixhawk heartbeat timeout — continuing without Pixhawk telemetry")
    else:
        print("✅ Pixhawk connected")
except Exception as e:
    mav = None
    print("⚠️ Pixhawk not found:", e)

# Store latest values
pixhawk_data = {
    "LAT": "",
    "LON": "",
    "HEAD": "",
    "SPD": ""
}

# ============================================
# CAMERA TRACK — PyGObject GStreamer backend
# Bypasses OpenCV's broken NvBufSurfaceFromFd
# on JetPack 6.2 (dmabuf_fd = -1 issue)
# ============================================

# Physical carrier port CAM1 (working clamp) maps to argus sensor-id=0 under
# the dual-IMX219 device-tree overlay. Silkscreen labels do NOT match argus
# sensor-ids — the mapping is carrier-specific. Keep this pinned to the port
# we actually route the ribbon to.
CAM1_SENSOR_ID = 0

class CameraVideoTrack(VideoStreamTrack):
    def __init__(self):
        super().__init__()

        self._pipeline = Gst.parse_launch(
            f"nvarguscamerasrc sensor-id={CAM1_SENSOR_ID} ! "
            "video/x-raw(memory:NVMM), width=1280, height=720, framerate=60/1 ! "
            "nvvidconv flip-method=2 ! "
            "video/x-raw, width=640, height=480, format=BGRx ! "
            "videoconvert ! video/x-raw, format=BGR ! "
            "appsink name=sink max-buffers=1 drop=true sync=false"
        )
        self._sink = self._pipeline.get_by_name('sink')
        ret = self._pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            # Surface argus/sensor open failures instead of silently running
            # a dead pipeline. Exiting lets systemd Restart=on-failure kick
            # us again after nvargus-daemon or the sensor comes up.
            self._pipeline.set_state(Gst.State.NULL)
            raise RuntimeError(
                "nvarguscamerasrc failed to start — check dmesg for imx219 "
                "probe, ribbon seating, and nvargus-daemon status"
            )
        print("[CAM] GStreamer pipeline started")

    def _pull_frame(self):
        sample = self._sink.emit('pull-sample')
        if sample is None:
            return np.zeros((480, 640, 3), dtype=np.uint8)
        buf = sample.get_buffer()
        success, info = buf.map(Gst.MapFlags.READ)
        if not success:
            return np.zeros((480, 640, 3), dtype=np.uint8)
        frame = np.frombuffer(info.data, dtype=np.uint8).reshape(480, 640, 3).copy()
        buf.unmap(info)
        return frame

    async def recv(self):
        global zoom_level, is_recording, video_writer

        pts, time_base = await self.next_timestamp()
        frame = self._pull_frame()

        # DIGITAL ZOOM (UNCHANGED)
        h, w, _ = frame.shape
        zw = int(w / zoom_level)
        zh = int(h / zoom_level)
        x1 = (w - zw) // 2
        y1 = (h - zh) // 2
        roi = frame[y1:y1+zh, x1:x1+zw]
        frame = cv2.resize(roi, (w, h))

        # RECORDING (UNCHANGED)
        if is_recording:
            if video_writer is None:
                filename = f"/home/mayra/videos/record_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.mp4"
                video_writer = cv2.VideoWriter(
                    filename,
                    cv2.VideoWriter_fourcc(*"mp4v"),
                    30,
                    (w, h),
                )
                print(f"🎥 Started recording: {filename}")

            video_writer.write(frame)
        else:
            if video_writer is not None:
                print("🛑 Stopped recording")
                video_writer.release()
                video_writer = None

        f = VideoFrame.from_ndarray(frame, format="bgr24")
        f.pts = pts
        f.time_base = time_base
        return f

# ============================================
# TELEMETRY SENDER + RECORDING (WITH PIXHAWK)
# ============================================
async def telemetry_sender():
    global ser, telemetry_file, telemetry_filename, is_recording

    if ser is None:
        return

    from datetime import datetime, timedelta

    buffer = ""

    while True:
        try:
            async with websockets.connect(TELEMETRY_SERVER) as ws:
                print("Connected to telemetry server.")

                while True:

                    # =========================
                    # Read Pixhawk MAVLink
                    # =========================
                    if mav is not None:
                        msg = mav.recv_match(blocking=False)

                        if msg:
                            mtype = msg.get_type()

                            if mtype == "GPS_RAW_INT":
                                pixhawk_data["LAT"] = msg.lat / 1e7
                                pixhawk_data["LON"] = msg.lon / 1e7

                            elif mtype == "ATTITUDE":
                                pixhawk_data["HEAD"] = math.degrees(msg.yaw)

                            elif mtype == "VFR_HUD":
                                pixhawk_data["SPD"] = msg.groundspeed

                    # =========================
                    # Read ESP32 serial
                    # =========================
                    if ser.in_waiting > 0:
                        chunk = ser.read(ser.in_waiting).decode(errors='ignore')
                        buffer += chunk

                        # Process full lines only
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            line = line.strip()

                            if not line:
                                continue

                            parts = line.split(',')
                            data = {}

                            for p in parts:
                                if ':' in p:
                                    key, value = p.split(':', 1)
                                    data[key] = value

                            # =========================
                            # Convert UTC → Tucson time
                            # =========================
                            utc_time = data.get("TIME", "")
                            local_time = utc_time

                            if utc_time and len(utc_time) >= 6:
                                try:
                                    hh = int(utc_time[0:2])
                                    mm = int(utc_time[2:4])
                                    ss = int(float(utc_time[4:]))

                                    utc_dt = datetime(2000, 1, 1, hh, mm, ss)
                                    tucson_dt = utc_dt - timedelta(hours=7)

                                    local_time = tucson_dt.strftime("%H:%M:%S")
                                except:
                                    pass

                            # Replace TIME
                            data["TIME"] = local_time

                            # =========================
                            # Merge Pixhawk into data
                            # =========================
                            data["LAT"] = pixhawk_data["LAT"]
                            data["LON"] = pixhawk_data["LON"]
                            data["HEAD"] = pixhawk_data["HEAD"]
                            data["SPD"] = pixhawk_data["SPD"]

                            # =========================
                            # Send telemetry to GUI
                            # =========================
                            await ws.send(json.dumps(data))

                            # =========================
                            # Record telemetry
                            # =========================
                            if is_recording:

                                if telemetry_file is None:
                                    telemetry_filename = f"/home/mayra/videos/telemetry_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.csv"
                                    telemetry_file = open(telemetry_filename, "w")
                                    telemetry_file.write("timestamp,HEAD,LAT,LON,SPD,TEMP,SAL,PH\n")
                                    print(f"📡 Started telemetry recording: {telemetry_filename}")

                                telemetry_file.write(
                                    f"{local_time},"
                                    f"{data.get('HEAD','')},"
                                    f"{data.get('LAT','')},"
                                    f"{data.get('LON','')},"
                                    f"{data.get('SPD','')},"
                                    f"{data.get('TEMP','')},"
                                    f"{data.get('SAL','')},"
                                    f"{data.get('PH','')}\n"
                                )

                            else:
                                if telemetry_file is not None:
                                    print("📡 Stopped telemetry recording")
                                    telemetry_file.close()
                                    telemetry_file = None

                    await asyncio.sleep(0.01)

        except Exception as e:
            print("Telemetry reconnecting...", e)
            await asyncio.sleep(2)


# ============================================
# MAIN WEBRTC LOGIC (UNCHANGED)
# ============================================

async def run():
    global zoom_level, is_recording

    asyncio.create_task(telemetry_sender())

    # Retry signaling connect with backoff. systemd After=signaling.service
    # only guarantees the unit started, not that its socket is listening —
    # without this loop, webrtc flaps at boot when it races ahead.
    print(f"Connecting to signaling: {SIGNALING_SERVER}")
    backoff = 1
    while True:
        try:
            ws = await websockets.connect(SIGNALING_SERVER)
            break
        except (OSError, ConnectionRefusedError) as e:
            print(f"Signaling not ready ({e}); retry in {backoff}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 10)

    try:
        print("Connected to signaling server")

        pc = RTCPeerConnection()
        camera_track = CameraVideoTrack()
        pc.addTrack(camera_track)

        async for msg in ws:
            data = json.loads(msg)

            if "offer" in data:
                offer = RTCSessionDescription(
                    sdp=data["offer"]["sdp"],
                    type="offer"
                )

                await pc.setRemoteDescription(offer)
                answer = await pc.createAnswer()
                await pc.setLocalDescription(answer)

                await ws.send(json.dumps({
                    "answer": {
                        "type": pc.localDescription.type,
                        "sdp": pc.localDescription.sdp,
                    }
                }))

            elif "ice" in data:
                try:
                    await pc.addIceCandidate(data["ice"])
                except:
                    pass

            elif "command" in data:
                cmd = data["command"]
                print(f"📩 Received command: {cmd}")

                if cmd == "zoom_in":
                    zoom_level = min(3.0, zoom_level + 0.1)

                elif cmd == "zoom_out":
                    zoom_level = max(1.0, zoom_level - 0.1)

                elif cmd == "start_record":
                    is_recording = True
                    await ws.send(json.dumps({"recording": True}))
                    print("🎥 Recording ON")

                elif cmd == "stop_record":
                    is_recording = False
                    await ws.send(json.dumps({"recording": False}))
                    print("🛑 Recording OFF")
    finally:
        await ws.close()

asyncio.run(run())

