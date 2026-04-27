"""Passive listen to a serial port for N seconds — proves the chip is alive."""
import serial, sys, time

port = sys.argv[1] if len(sys.argv) > 1 else "COM6"
secs = int(sys.argv[2]) if len(sys.argv) > 2 else 5

print(f"[listen] {port} for {secs}s", flush=True)
ser = serial.Serial()
ser.port = port
ser.baudrate = 115200
ser.timeout = 0.2
ser.write_timeout = 1.0
ser.rtscts = False
ser.dsrdtr = False
ser.open()
print("[listen] open ok", flush=True)
try:
    ser.dtr = False; ser.rts = False
except Exception:
    pass

start = time.time()
buf = b""
while time.time() - start < secs:
    chunk = ser.read(256)
    if chunk:
        buf += chunk
        sys.stdout.write(chunk.decode(errors="replace"))
        sys.stdout.flush()

print("\n[listen] done. total bytes:", len(buf), flush=True)
ser.close()
