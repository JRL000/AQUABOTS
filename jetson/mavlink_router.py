"""
mavlink_router.py — Bidirectional MAVLink bridge: Pixhawk serial <-> QGC UDP

Connects to the Pixhawk over USB serial and forwards MAVLink traffic to/from
QGroundControl (or any GCS) over UDP.

Usage:
    python3 mavlink_router.py [--port /dev/ttyACM0] [--baud 57600] [--udp 14550]

QGC setup (on laptop):
    Application Settings -> Comm Links -> Add
    Type: UDP
    Listening Port: (leave blank or use 14550)
    Target Host: <Jetson Tailscale IP>   (e.g. 100.76.1.26)
    Target Port: 14550
"""

import serial
import socket
import threading
import argparse
import sys
import time

SERIAL_PORT  = '/dev/ttyACM0'
SERIAL_BAUD  = 57600
UDP_PORT     = 14550      # standard MAVLink GCS port
CHUNK_SIZE   = 512        # bytes to read from serial per loop
SOCK_TIMEOUT = 0.05       # seconds

qgc_addr = None
addr_lock = threading.Lock()
running   = True


def serial_to_udp(ser, sock):
    """Forward raw bytes from Pixhawk serial -> QGC UDP."""
    global qgc_addr
    while running:
        try:
            data = ser.read(CHUNK_SIZE)
            if data:
                with addr_lock:
                    dest = qgc_addr
                if dest:
                    try:
                        sock.sendto(data, dest)
                    except OSError:
                        pass
        except serial.SerialException as e:
            print(f"[router] Serial read error: {e}")
            time.sleep(0.5)


def udp_to_serial(ser, sock):
    """Forward raw bytes from QGC UDP -> Pixhawk serial.
       Also captures QGC's address so we know where to send telemetry.
    """
    global qgc_addr
    while running:
        try:
            data, addr = sock.recvfrom(1024)
            with addr_lock:
                if qgc_addr != addr:
                    qgc_addr = addr
                    print(f"[router] QGC connected from {addr[0]}:{addr[1]}")
            try:
                ser.write(data)
            except serial.SerialException as e:
                print(f"[router] Serial write error: {e}")
        except socket.timeout:
            pass
        except OSError:
            pass


def main():
    global running

    parser = argparse.ArgumentParser(description='MAVLink serial-UDP bridge')
    parser.add_argument('--port', default=SERIAL_PORT)
    parser.add_argument('--baud', type=int, default=SERIAL_BAUD)
    parser.add_argument('--udp',  type=int, default=UDP_PORT,
                        help='UDP port to listen on (default 14550)')
    args = parser.parse_args()

    print(f"[router] Opening serial {args.port} @ {args.baud} baud")
    try:
        ser = serial.Serial(args.port, args.baud, timeout=0.1)
    except serial.SerialException as e:
        print(f"[router] ERROR opening serial port: {e}")
        sys.exit(1)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('0.0.0.0', args.udp))
    sock.settimeout(SOCK_TIMEOUT)
    print(f"[router] Listening for QGC on UDP port {args.udp}")
    print(f"[router] In QGC: Comm Links > Add > UDP, Target {args.port} port {args.udp}")
    print(f"[router] Waiting for Pixhawk and QGC... (Ctrl+C to stop)")

    t1 = threading.Thread(target=serial_to_udp, args=(ser, sock), daemon=True)
    t2 = threading.Thread(target=udp_to_serial, args=(ser, sock), daemon=True)
    t1.start()
    t2.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[router] Stopping.")
        running = False

    ser.close()
    sock.close()


if __name__ == '__main__':
    main()
