#!/usr/bin/env python3
"""
mavproxy_launcher.py
Runs mavproxy with a pseudo-TTY so its readline console initialises
correctly. Strips ANSI escape sequences and forwards clean output
to stdout for systemd journal capture.
"""
import os
import re
import subprocess
import pty
import sys

CMD = [
    '/home/mayra/AquaBotGUI_WebRTC/venv/bin/mavproxy.py',
    '--master=/dev/ttyTHS1',           # UART (ttyACM0 = USB fallback)
    '--baudrate=57600',
    '--out=udp:100.78.157.73:14550',   # QGC on John's PC (Tailscale)
    '--out=udp:127.0.0.1:14552',       # app.py local UDP feed
    '--out=udp:127.0.0.1:14553',       # webrtc_jetson.py local UDP feed
    '--nowait',
]

ANSI = re.compile(rb'\x1b(?:[@-Z\-_]|\[[0-9;]*[ -/]*[@-~])')


def main():
    master_fd, slave_fd = pty.openpty()
    proc = subprocess.Popen(
        CMD,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        close_fds=True,
    )
    os.close(slave_fd)

    try:
        while True:
            try:
                data = os.read(master_fd, 4096)
            except OSError:
                break
            if not data:
                break
            clean = ANSI.sub(b'', data).replace(b'\r', b'')
            sys.stdout.buffer.write(clean)
            sys.stdout.flush()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        os.close(master_fd)


if __name__ == '__main__':
    main()
