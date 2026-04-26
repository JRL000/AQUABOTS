#!/usr/bin/env python3
"""
swarm_mock — pretends to be the on-board ESP32 swarm node so the Jetson
side can be tested end-to-end without flashing real hardware.

Wire-protocol identical to firmware/main/swarm_bridge.h: ASCII tag-prefixed
lines, newline-terminated.

Transport: TCP. The Jetson app connects with env var
    AQUABOT_ESP32_TCP=127.0.0.1:7790
and the mock impersonates an ESP32 on the other end.

Run:
    python jetson/tools/swarm_mock.py --scenario follower_3boat
    python jetson/tools/swarm_mock.py --scenario leader_3boat
    python jetson/tools/swarm_mock.py --scenario leader_silence_test
    python jetson/tools/swarm_mock.py --scenario stop_test

Each scenario is a script of timed events that produces realistic swarm
chatter (role, formation config, position assignments, leader GPS broadcasts).
The mock also ingests Jetson→ESP32 messages (ANCHOR_GPS / SET_FORMATION /
SWARM_ENABLE) and prints them so you can verify the round trip.
"""

from __future__ import annotations

import argparse
import math
import socket
import sys
import threading
import time
from typing import Callable

# Same directory layout — import sibling protocol module.
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
from swarm_protocol import (  # noqa: E402
    TAG_ROLE, TAG_TARGET, TAG_LEADER_GPS, TAG_FORMATION, TAG_STOP,
    parse_line,
)


# ---------------------------------------------------------------------------
# Default fake reference point — Tempe Town Lake, AZ. Pick anywhere; this
# only matters for the lat/lon math to produce sane numbers.
# ---------------------------------------------------------------------------
LEADER_LAT0 = 33.42746
LEADER_LON0 = -111.93584
LEADER_HEADING0 = 90.0     # facing east


# ---------------------------------------------------------------------------
# Pattern math (mirrors firmware/main/formation.c so the mock is realistic).
# Returns offset (x_mm, y_mm, h_offset_deg) for a node at index N of M.
# ---------------------------------------------------------------------------

def calc_offset(pattern: str, node_index: int, total_nodes: int,
                spacing_mm: int) -> tuple[int, int, int]:
    if pattern == "line":
        return (0, -node_index * spacing_mm, 0)
    if pattern == "wedge":
        if node_index == 0:
            return (0, 0, 0)
        row = (node_index + 1) // 2
        left = (node_index % 2 == 1)
        x = (row * spacing_mm) // 2
        return ((-x if left else x), -row * spacing_mm, 0)
    if pattern == "column":
        row = node_index // 2
        col = node_index % 2
        x = -(spacing_mm // 2) if col == 0 else (spacing_mm // 2)
        return (x, -row * spacing_mm, 0)
    if pattern == "circle":
        if total_nodes <= 1 or node_index == 0:
            return (0, 0, 0)
        nodes_on_circle = total_nodes - 1
        radius = max(spacing_mm, (nodes_on_circle * spacing_mm) // 6)
        a = (node_index - 1) * 2.0 * math.pi / nodes_on_circle
        return (int(radius * math.sin(a)), int(radius * math.cos(a)),
                int((a * 180.0 / math.pi)))
    return (0, 0, 0)


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------

class Scenario:
    """A scenario is a function that, given a sender callable, runs an event
    timeline. The sender takes a string line (already newline-terminated)
    and writes it to the connected Jetson."""

    def __init__(self, name: str, runner: Callable[[Callable[[str], None]], None]):
        self.name = name
        self.runner = runner

    def run(self, send: Callable[[str], None]):
        self.runner(send)


def _emit(send, tag, **kv):
    body = ",".join(f"{k}={v}" for k, v in kv.items())
    send(f"{tag}:{body}\n")


def scenario_follower_3boat(send):
    """This boat is node 1 in a 3-boat wedge with leader = node 2.
    Leader is stationary so the markers stop moving and the visual is
    easier to interpret."""
    pattern = "wedge"
    spacing = 2000
    total = 3
    my_index = 1     # index 1 = first follower (left side of wedge)

    _emit(send, TAG_ROLE, role="follower", leader_id=2, members=total, my_index=my_index)
    _emit(send, TAG_FORMATION, type=pattern, spacing=spacing, nodes=total)

    seq = 0
    while True:
        _emit(send, TAG_LEADER_GPS,
              lat=f"{LEADER_LAT0:.7f}", lon=f"{LEADER_LON0:.7f}",
              h=f"{LEADER_HEADING0:.1f}", age_ms=100)
        x, y, h = calc_offset(pattern, my_index, total, spacing)
        _emit(send, TAG_TARGET, x=x, y=y, h=h, seq=seq)
        seq += 1
        time.sleep(1.0)


def scenario_leader_3boat(send):
    """This boat is the leader (node 2). It does not receive a target offset
    (offset is 0 by definition for the leader); it only emits ROLE +
    FORMATION + occasional re-broadcasts."""
    _emit(send, TAG_ROLE, role="leader", leader_id=2, members=3, my_index=0)
    _emit(send, TAG_FORMATION, type="wedge", spacing=2000, nodes=3)

    seq = 0
    while True:
        # Leader's offset is always (0,0,0)
        _emit(send, TAG_TARGET, x=0, y=0, h=0, seq=seq)
        seq += 1
        time.sleep(2.0)


def scenario_leader_silence_test(send):
    """Same as follower_3boat, but the leader GPS goes silent after 15s
    so we can verify the stale-GPS HOLD trip."""
    pattern = "line"
    spacing = 2000
    total = 2
    my_index = 1

    _emit(send, TAG_ROLE, role="follower", leader_id=2, members=total, my_index=my_index)
    _emit(send, TAG_FORMATION, type=pattern, spacing=spacing, nodes=total)

    start = time.time()
    seq = 0
    while True:
        if time.time() - start < 15.0:
            _emit(send, TAG_LEADER_GPS,
                  lat=f"{LEADER_LAT0:.7f}", lon=f"{LEADER_LON0:.7f}",
                  h=f"{LEADER_HEADING0:.1f}", age_ms=100)
        x, y, h = calc_offset(pattern, my_index, total, spacing)
        _emit(send, TAG_TARGET, x=x, y=y, h=h, seq=seq)
        seq += 1
        time.sleep(1.0)


def scenario_stop_test(send):
    """Run as a follower for 10s, then leader sends emergency STOP."""
    pattern = "wedge"
    spacing = 2000
    total = 3
    my_index = 2

    _emit(send, TAG_ROLE, role="follower", leader_id=3, members=total, my_index=my_index)
    _emit(send, TAG_FORMATION, type=pattern, spacing=spacing, nodes=total)

    start = time.time()
    seq = 0
    stopped = False
    while True:
        _emit(send, TAG_LEADER_GPS,
              lat=f"{LEADER_LAT0:.7f}", lon=f"{LEADER_LON0:.7f}",
              h=f"{LEADER_HEADING0:.1f}", age_ms=100)
        x, y, h = calc_offset(pattern, my_index, total, spacing)
        _emit(send, TAG_TARGET, x=x, y=y, h=h, seq=seq)
        seq += 1
        if not stopped and time.time() - start > 10.0:
            _emit(send, TAG_STOP, reason="collision")
            stopped = True
        time.sleep(1.0)


SCENARIOS = {
    "follower_3boat": Scenario("follower_3boat", scenario_follower_3boat),
    "leader_3boat": Scenario("leader_3boat", scenario_leader_3boat),
    "leader_silence_test": Scenario("leader_silence_test", scenario_leader_silence_test),
    "stop_test": Scenario("stop_test", scenario_stop_test),
}


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

def serve(host: str, port: int, scenario: Scenario):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((host, port))
    s.listen(1)
    print(f"[mock] listening on {host}:{port}, scenario={scenario.name}")
    print("[mock] waiting for Jetson to connect...")

    while True:
        conn, addr = s.accept()
        print(f"[mock] connection from {addr}")
        try:
            run_session(conn, scenario)
        except (BrokenPipeError, ConnectionResetError):
            print("[mock] Jetson disconnected; waiting for next connect...")
        except KeyboardInterrupt:
            print("[mock] interrupted; closing")
            return
        finally:
            try:
                conn.close()
            except Exception:
                pass


def run_session(conn: socket.socket, scenario: Scenario):
    """One Jetson session: spawn a sender thread (the scenario) and read
    inbound bytes (ANCHOR_GPS / SET_FORMATION / SWARM_ENABLE) on this thread."""
    stop_flag = {"stop": False}

    def send(line: str):
        if stop_flag["stop"]:
            return
        try:
            conn.sendall(line.encode("utf-8"))
        except (BrokenPipeError, ConnectionResetError, OSError):
            stop_flag["stop"] = True

    sender_thread = threading.Thread(target=scenario.run, args=(send,), daemon=True)
    sender_thread.start()

    buf = b""
    while not stop_flag["stop"]:
        try:
            chunk = conn.recv(4096)
        except (ConnectionResetError, OSError):
            break
        if not chunk:
            break
        buf += chunk
        while b"\n" in buf:
            line, _, buf = buf.partition(b"\n")
            text = line.decode("utf-8", errors="ignore").strip()
            if not text:
                continue
            tag, fields = parse_line(text)
            if tag:
                print(f"[mock <-] {tag}: {fields}")
            else:
                print(f"[mock <-] (ignored) {text}")
    stop_flag["stop"] = True


def main():
    ap = argparse.ArgumentParser(description="ESP32 swarm node mock")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7790)
    ap.add_argument("--scenario", choices=sorted(SCENARIOS.keys()),
                    default="follower_3boat")
    args = ap.parse_args()
    serve(args.host, args.port, SCENARIOS[args.scenario])


if __name__ == "__main__":
    main()
