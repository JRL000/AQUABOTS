import serial
import asyncio
import websockets

clients = set()

async def handler(websocket):
    clients.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        clients.remove(websocket)

async def serial_reader():
    ser = serial.Serial('/dev/ttyUSB0', 115200)

    while True:
        line = ser.readline().decode(errors='ignore').strip()
        if line:
            print("ESP32:", line)

            for ws in clients:
                try:
                    await ws.send(line)
                except:
                    pass

async def main():
    server = await websockets.serve(handler, "0.0.0.0", 8766)
    print("Telemetry server running on 8766")

    await serial_reader()

asyncio.run(main())
