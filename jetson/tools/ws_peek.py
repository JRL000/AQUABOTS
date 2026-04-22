#!/usr/bin/env python3
"""
ws_peek.py — subscribe to the AquaBot telemetry websocket and pretty-print it.

Use this over SSH when you can't open the browser dashboard. It connects to
the same ws://HOST:8766 stream the GUI uses and shows the live fields with
link-age coloring so you can verify Pixhawk/ESP32 data is flowing.

Usage:
    python3 ws_peek.py                      # localhost, pretty mode
    python3 ws_peek.py --raw                # dump raw JSON lines
    python3 ws_peek.py --host 100.76.1.26   # connect to a remote host
    python3 ws_peek.py --keys BAT_V,MODE    # only show listed keys
"""
import argparse
import asyncio
import json
import sys

try:
    import websockets
except ImportError:
    sys.exit("Missing 'websockets' package. On the Jetson: pip3 install websockets")


# ANSI colors — skip if stdout isn't a tty so piping to a file stays clean.
def _c(code, s):
    return s if not sys.stdout.isatty() else f"\x1b[{code}m{s}\x1b[0m"


GREEN = lambda s: _c("32", s)
YELLOW = lambda s: _c("33", s)
RED = lambda s: _c("31", s)
DIM = lambda s: _c("2", s)
BOLD = lambda s: _c("1", s)


def age_color(age_ms, warn_ms, stale_ms):
    """Color an age integer by freshness. -1 means never-seen."""
    if age_ms is None or age_ms < 0:
        return RED(f"{age_ms if age_ms is not None else '-'}")
    if age_ms > stale_ms:
        return RED(f"{age_ms}")
    if age_ms > warn_ms:
        return YELLOW(f"{age_ms}")
    return GREEN(f"{age_ms}")


def render(d, keys_filter=None):
    """Render one telemetry dict as a compact multi-line block."""
    if keys_filter:
        subset = {k: d.get(k) for k in keys_filter}
        return "  ".join(f"{k}={subset[k]}" for k in keys_filter)

    mode = d.get("MODE", "?")
    armed = "ARMED" if d.get("ARMED") else "disarmed"
    hb = age_color(d.get("HB_AGE_MS", -1), 1500, 3000)
    gps = age_color(d.get("GPS_AGE_MS", -1), 2000, 5000)
    esp = age_color(d.get("ESP32_AGE_MS", -1), 5000, 15000)

    lines = [
        BOLD(f"[{d.get('TIME','--')}] {mode}  {armed}  slow={d.get('SLOW_MODE')}"),
        f"  pos:    lat={d.get('LAT')}  lon={d.get('LON')}  hdg={d.get('HEAD')}  spd={d.get('SPD')} m/s",
        f"  gps:    fix={d.get('GPS_FIX')}  sats={d.get('GPS_SATS')}  hdop={d.get('GPS_HDOP')}  home_set={d.get('HOME_SET')}",
        f"  mission:wp={d.get('CURRENT_WP')}/{d.get('WP_TOTAL')}",
        f"  servo:  s1={d.get('SERVO1')}  s3={d.get('SERVO3')}  thr%={d.get('THROTTLE_PCT')}",
        f"  batt:   {d.get('BAT_V')} V  {d.get('BAT_A')} A  {d.get('BAT_PCT')}%",
        f"  ekf:    cmp_var={d.get('EKF_COMPASS_VAR')}  pos_var={d.get('EKF_POS_VAR')}",
        f"  sensors:temp={d.get('TEMP')}  sal={d.get('SAL')}  ph={d.get('PH')}",
        f"  age_ms: hb={hb}  gps={gps}  esp32={esp}",
    ]
    status = d.get("STATUS")
    if status:
        sev = d.get("STATUS_SEV", 6)
        color = RED if sev <= 3 else YELLOW if sev <= 4 else DIM
        lines.append(f"  {color('status: ' + status)}")
    return "\n".join(lines) + "\n"


async def run(host, port, raw, keys_filter):
    url = f"ws://{host}:{port}"
    print(DIM(f"connecting to {url} ..."))
    async with websockets.connect(url, ping_interval=20, ping_timeout=10) as ws:
        print(DIM("connected; Ctrl-C to quit."))
        async for raw_msg in ws:
            if raw:
                print(raw_msg, flush=True)
                continue
            try:
                d = json.loads(raw_msg)
            except json.JSONDecodeError:
                print(DIM(f"non-JSON: {raw_msg[:80]}"))
                continue
            print(render(d, keys_filter), flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--raw", action="store_true", help="print raw JSON lines (pipe-friendly)")
    ap.add_argument("--keys", default="", help="comma-separated keys to show instead of the full block")
    args = ap.parse_args()
    keys_filter = [k.strip() for k in args.keys.split(",") if k.strip()] or None
    try:
        asyncio.run(run(args.host, args.port, args.raw, keys_filter))
    except KeyboardInterrupt:
        print(DIM("\nbye."))
    except Exception as e:
        sys.exit(f"error: {e}")


if __name__ == "__main__":
    main()
