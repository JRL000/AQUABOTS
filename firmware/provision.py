"""
Provision an ESP32-S3 node by setting its node_id via the firmware console.

Usage: python provision.py <COM_PORT> <NODE_ID>
"""
import serial
import sys
import time

def log(msg):
    print(msg, flush=True)

if len(sys.argv) != 3:
    log("Usage: python provision.py <COM_PORT> <NODE_ID>")
    sys.exit(1)

port = sys.argv[1]
node_id = int(sys.argv[2])

log(f"[provision] opening {port} @ 115200")
# rtscts=False, dsrdtr=False so we don't toggle DTR/RTS and reset the chip on open
ser = serial.Serial()
ser.port = port
ser.baudrate = 115200
ser.timeout = 0.5
ser.rtscts = False
ser.dsrdtr = False
ser.open()
log("[provision] port open")

# Drop DTR/RTS so the chip isn't held in reset
try:
    ser.dtr = False
    ser.rts = False
except Exception as e:
    log(f"[provision] (info) couldn't toggle dtr/rts: {e}")

# Wait for the chip to come up, then drain anything in the buffer
time.sleep(2.0)
ser.reset_input_buffer()

# Send a newline to provoke a prompt
log("[provision] poking for prompt")
ser.write(b"\r\n")
time.sleep(0.3)
ser.write(b"help\r\n")
time.sleep(0.6)
poke = ser.read(2048).decode(errors="replace")
log("--- poke output ---")
log(poke)
log("--- end poke ---")

log(f"[provision] sending: set_node_id {node_id}")
ser.write(f"set_node_id {node_id}\r\n".encode())
time.sleep(1.0)
ser.write(b"get_node_id\r\n")
time.sleep(0.5)
ser.write(b"info\r\n")
time.sleep(0.8)

data = ser.read(4096).decode(errors="replace")
log("--- console output ---")
log(data)
log("--- end ---")

ser.close()
log("[provision] done. Run hard reset to apply.")
