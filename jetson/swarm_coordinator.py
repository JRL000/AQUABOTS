"""
swarm_coordinator
=================

Bridges the on-board ESP32 swarm node to the Pixhawk autopilot.

The ESP32 handles the radio mesh (membership, leader election, formation
math). This module turns the ESP32's "your assigned offset is (x_mm, y_mm)"
into "Pixhawk, fly to this lat/lon" via MAVLink waypoints, and turns
"emergency stop" into a HOLD-mode switch.

Coordinate frame (matches firmware/main/formation.c):
    +Y = forward (direction the leader is facing)
    +X = right of the leader
    heading_offset = degrees clockwise from leader heading

This module is I/O-agnostic: the host (jetson/app.py) feeds it inbound
serial lines and Pixhawk GPS, and drains outbound serial lines from it.
The host also supplies two callbacks: upload_waypoint() and set_mode().
"""

from __future__ import annotations

import math
import queue
import threading
import time
from collections import deque
from typing import Callable, Optional

from swarm_protocol import (
    TAG_ROLE, TAG_TARGET, TAG_LEADER_GPS, TAG_FORMATION, TAG_STOP,
    encode_anchor_gps, encode_set_formation, encode_enable,
)


# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

ANCHOR_GPS_TX_HZ          = 1.0    # how often the leader pushes its GPS down
LEADER_GPS_STALE_S        = 5.0    # follower switches to HOLD after this
WAYPOINT_RESEND_MIN_S     = 2.0    # don't spam Pixhawk; respect this gap
WAYPOINT_MOVE_THRESHOLD_M = 0.5    # don't resend if target shifted < this much
GPS_FIX_3D                = 3      # MAVLink GPS_FIX_TYPE_3D_FIX
EARTH_M_PER_DEG           = 111111.0


# ---------------------------------------------------------------------------
# STATE
# ---------------------------------------------------------------------------

class SwarmState:
    """All mutable state. Mutex-protected; access via the coordinator."""

    def __init__(self):
        # User-facing toggle (set by GUI via SWARM_ENABLE)
        self.enabled = False

        # Role
        self.role: str = "unknown"        # "leader" | "follower" | "unknown"
        self.leader_id: Optional[int] = None
        self.my_index: Optional[int] = None
        self.member_count: int = 0

        # Formation
        self.pattern: str = "none"
        self.spacing_mm: int = 2000

        # Latest assignment from ESP32 (offset)
        self.target_offset_mm: Optional[tuple[int, int, int]] = None  # (x, y, h_deg)
        self.target_seq: int = -1

        # Latest leader GPS (formation center)
        self.leader_gps: Optional[tuple[float, float, float]] = None  # (lat, lon, heading)
        self.leader_gps_received_at: float = 0.0

        # Local boat GPS (from Pixhawk)
        self.my_gps: Optional[tuple[float, float, float, int]] = None  # (lat, lon, heading, fix)
        self.my_gps_t: float = 0.0

        # Computed target for THIS boat
        self.target_latlon: Optional[tuple[float, float, float]] = None  # (lat, lon, heading)
        self.last_waypoint_uploaded_at: float = 0.0
        self.last_waypoint_target: Optional[tuple[float, float]] = None

        # Stop latch
        self.stopped: bool = False
        self.stop_reason: str = ""

        # Status / diagnostics
        self.last_event: str = ""

        # Activity log (most recent N events for the GUI)
        self.events: deque = deque(maxlen=20)


# ---------------------------------------------------------------------------
# GEOMETRY
# ---------------------------------------------------------------------------

def offset_to_latlon(leader_lat: float, leader_lon: float,
                     leader_heading_deg: float,
                     offset_x_mm: int, offset_y_mm: int,
                     heading_offset_deg: int) -> tuple[float, float, float]:
    """
    Convert a formation offset (relative to leader, in mm) to absolute lat/lon
    using a small-angle flat-earth approximation. Good enough for hundreds
    of meters at temperate latitudes; we are operating at pond scale.

    Formation frame:
        +Y_form = forward (direction leader is facing)
        +X_form = right of leader

    Earth frame:
        +north, +east
    """
    h_rad = math.radians(leader_heading_deg)
    # Heading is degrees clockwise from north. In (north, east) world coords:
    #   forward unit vector = (cos H,  sin H)
    #   right   unit vector = forward rotated 90° clockwise = (-sin H, cos H)
    # World position = offset_y * forward + offset_x * right
    north_m = (offset_y_mm * math.cos(h_rad) - offset_x_mm * math.sin(h_rad)) / 1000.0
    east_m  = (offset_y_mm * math.sin(h_rad) + offset_x_mm * math.cos(h_rad)) / 1000.0

    delta_lat = north_m / EARTH_M_PER_DEG
    delta_lon = east_m  / (EARTH_M_PER_DEG * max(math.cos(math.radians(leader_lat)), 1e-6))

    target_lat = leader_lat + delta_lat
    target_lon = leader_lon + delta_lon
    target_heading = (leader_heading_deg + heading_offset_deg) % 360.0
    return target_lat, target_lon, target_heading


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters. Used for waypoint-move thresholding."""
    r = 6371000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


# ---------------------------------------------------------------------------
# COORDINATOR
# ---------------------------------------------------------------------------

class SwarmCoordinator:
    def __init__(self,
                 upload_waypoint: Callable[[float, float, float], bool],
                 set_mode: Callable[[str], None],
                 geofence_check: Optional[Callable[[float, float], bool]] = None):
        """
        upload_waypoint(lat, lon, heading_deg) -> bool
            Push a single AUTO waypoint to the Pixhawk. Return True on success.

        set_mode(mode_name)
            "AUTO", "HOLD", "MANUAL", "RTL".

        geofence_check(lat, lon) -> bool
            Optional. Return True if the point is inside the active geofence.
            If None, all points are accepted.
        """
        self.state = SwarmState()
        self._lock = threading.Lock()
        self._outbound: queue.Queue[str] = queue.Queue()

        self._upload_waypoint = upload_waypoint
        self._set_mode = set_mode
        self._geofence_check = geofence_check

        self._last_anchor_tx = 0.0
        self._stop_thread = False
        self._tick_thread: Optional[threading.Thread] = None

    # ----- lifecycle ------------------------------------------------------

    def start(self):
        if self._tick_thread is not None:
            return
        self._tick_thread = threading.Thread(target=self._tick_loop, daemon=True)
        self._tick_thread.start()

    def stop(self):
        self._stop_thread = True

    # ----- public API: outbound queue (drained by the serial writer) -----

    def get_outbound_line(self, timeout: float = 0.1) -> Optional[str]:
        try:
            return self._outbound.get(timeout=timeout)
        except queue.Empty:
            return None

    # ----- public API: GUI commands --------------------------------------

    def set_enabled(self, on: bool):
        with self._lock:
            self.state.enabled = on
            self.state.stopped = False  # clear latch on re-enable
            self._log(f"swarm mode {'ENABLED' if on else 'DISABLED'} by GUI")
        self._enqueue(encode_enable(on))
        if not on:
            self._set_mode("HOLD")

    def set_pattern(self, pattern: str, spacing_mm: int):
        spacing_mm = max(500, min(10000, int(spacing_mm)))
        if pattern not in ("none", "line", "wedge", "circle", "column"):
            return
        self._enqueue(encode_set_formation(pattern, spacing_mm))
        with self._lock:
            self._log(f"requested pattern={pattern} spacing={spacing_mm}mm")

    # ----- public API: feeds from app.py ---------------------------------

    def feed_pixhawk_gps(self, lat: float, lon: float, heading_deg: float,
                         fix_type: int, t_unix: int):
        """Called by app.py whenever a fresh Pixhawk GPS reading is available."""
        with self._lock:
            self.state.my_gps = (lat, lon, heading_deg, fix_type)
            self.state.my_gps_t = time.time()

    def feed_serial_line(self, line: str):
        """Called by app.py for each newline-stripped line from the ESP32."""
        from swarm_protocol import parse_line
        tag, fields = parse_line(line)
        if not tag:
            return
        try:
            if tag == TAG_ROLE:
                self._on_role(fields)
            elif tag == TAG_TARGET:
                self._on_target(fields)
            elif tag == TAG_LEADER_GPS:
                self._on_leader_gps(fields)
            elif tag == TAG_FORMATION:
                self._on_formation(fields)
            elif tag == TAG_STOP:
                self._on_stop(fields)
        except (ValueError, KeyError) as e:
            with self._lock:
                self._log(f"bad {tag} line: {e}")

    # ----- public API: GUI status snapshot --------------------------------

    def snapshot(self) -> dict:
        with self._lock:
            s = self.state
            return {
                "enabled": s.enabled,
                "role": s.role,
                "leader_id": s.leader_id,
                "my_index": s.my_index,
                "member_count": s.member_count,
                "pattern": s.pattern,
                "spacing_mm": s.spacing_mm,
                "target_offset_mm": s.target_offset_mm,
                "target_seq": s.target_seq,
                "target_latlon": s.target_latlon,
                "leader_gps": s.leader_gps,
                "leader_gps_age_s": (time.time() - s.leader_gps_received_at)
                                    if s.leader_gps_received_at else None,
                "stopped": s.stopped,
                "stop_reason": s.stop_reason,
                "events": list(s.events),
            }

    # ----- inbound handlers ----------------------------------------------

    def _on_role(self, f: dict):
        with self._lock:
            self.state.role = f.get("role", "unknown")
            self.state.leader_id = int(f["leader_id"]) if "leader_id" in f else None
            self.state.member_count = int(f.get("members", 0))
            self.state.my_index = int(f["my_index"]) if "my_index" in f else None
            self._log(f"role={self.state.role} leader={self.state.leader_id} "
                      f"members={self.state.member_count}")

    def _on_target(self, f: dict):
        x = int(f["x"]); y = int(f["y"])
        h = int(f.get("h", 0)); seq = int(f.get("seq", 0))
        with self._lock:
            if seq == self.state.target_seq and self.state.target_offset_mm == (x, y, h):
                return  # duplicate
            self.state.target_offset_mm = (x, y, h)
            self.state.target_seq = seq
            self._log(f"target offset=({x},{y})mm h={h}° seq={seq}")
        self._maybe_recompute_and_command()

    def _on_leader_gps(self, f: dict):
        lat = float(f["lat"]); lon = float(f["lon"])
        heading = float(f.get("h", 0.0))
        with self._lock:
            self.state.leader_gps = (lat, lon, heading)
            self.state.leader_gps_received_at = time.time()
        self._maybe_recompute_and_command()

    def _on_formation(self, f: dict):
        with self._lock:
            self.state.pattern = f.get("type", "none")
            self.state.spacing_mm = int(f.get("spacing", 2000))
            self.state.member_count = int(f.get("nodes", self.state.member_count))
            self._log(f"formation={self.state.pattern} spacing={self.state.spacing_mm}mm "
                      f"nodes={self.state.member_count}")

    def _on_stop(self, f: dict):
        reason = f.get("reason", "?")
        with self._lock:
            self.state.stopped = True
            self.state.stop_reason = reason
            self._log(f"SWARM_STOP reason={reason} -> HOLD")
        self._set_mode("HOLD")

    # ----- main loop ------------------------------------------------------

    def _tick_loop(self):
        while not self._stop_thread:
            self._tick()
            time.sleep(0.1)

    def _tick(self):
        now = time.time()

        # If we're the leader, push our GPS to the ESP32 at ANCHOR_GPS_TX_HZ
        with self._lock:
            is_leader = (self.state.role == "leader" and self.state.enabled)
            my = self.state.my_gps
            my_t = self.state.my_gps_t
            leader_age = (now - self.state.leader_gps_received_at) \
                         if self.state.leader_gps_received_at else None
            is_follower = (self.state.role == "follower" and self.state.enabled)

        if is_leader and my is not None and (now - self._last_anchor_tx) >= 1.0 / ANCHOR_GPS_TX_HZ:
            lat, lon, heading, fix = my
            if fix >= GPS_FIX_3D:
                self._enqueue(encode_anchor_gps(lat, lon, heading, fix, int(my_t)))
                self._last_anchor_tx = now

        # If we're a follower and the leader's GPS has gone stale, HOLD.
        if is_follower and leader_age is not None and leader_age > LEADER_GPS_STALE_S:
            with self._lock:
                if not self.state.stopped:
                    self.state.stopped = True
                    self.state.stop_reason = f"leader GPS stale ({leader_age:.1f}s)"
                    self._log(self.state.stop_reason + " -> HOLD")
            self._set_mode("HOLD")

    def _maybe_recompute_and_command(self):
        """If we have a leader GPS and an offset, compute target and push.

        Computing the target_latlon happens whenever inputs are available
        (so the GUI can show the ghost marker as a preview). The actual
        waypoint upload + mode switch are gated on the enable + stop flags."""
        with self._lock:
            if self.state.role != "follower":
                return
            if self.state.leader_gps is None or self.state.target_offset_mm is None:
                return
            lat0, lon0, h_lead = self.state.leader_gps
            x, y, h_off = self.state.target_offset_mm
            target_lat, target_lon, target_heading = offset_to_latlon(
                lat0, lon0, h_lead, x, y, h_off)
            self.state.target_latlon = (target_lat, target_lon, target_heading)

            if not self.state.enabled or self.state.stopped:
                return
            if (time.time() - self.state.leader_gps_received_at) > LEADER_GPS_STALE_S:
                return
            now = time.time()
            since_last = now - self.state.last_waypoint_uploaded_at
            last = self.state.last_waypoint_target
            distance_moved = (haversine_m(last[0], last[1], target_lat, target_lon)
                              if last else 1e9)
            should_resend = (since_last >= WAYPOINT_RESEND_MIN_S
                             and distance_moved >= WAYPOINT_MOVE_THRESHOLD_M)

        if not should_resend:
            return

        # Geofence check
        if self._geofence_check is not None and not self._geofence_check(target_lat, target_lon):
            with self._lock:
                self._log(f"target ({target_lat:.6f},{target_lon:.6f}) outside geofence; HOLD")
                self.state.stopped = True
                self.state.stop_reason = "target outside geofence"
            self._set_mode("HOLD")
            return

        ok = self._upload_waypoint(target_lat, target_lon, target_heading)
        with self._lock:
            if ok:
                self.state.last_waypoint_uploaded_at = time.time()
                self.state.last_waypoint_target = (target_lat, target_lon)
                self._log(f"waypoint uploaded ({target_lat:.6f},{target_lon:.6f})")
            else:
                self._log("waypoint upload FAILED")
        if ok:
            self._set_mode("GUIDED")

    # ----- helpers --------------------------------------------------------

    def _enqueue(self, line: str):
        self._outbound.put(line)

    def _log(self, msg: str):
        self.state.last_event = msg
        self.state.events.append((time.time(), msg))
        print(f"[SWARM] {msg}")
