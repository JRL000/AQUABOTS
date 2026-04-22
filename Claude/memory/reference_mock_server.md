# Mock server — no-hardware GUI testing

`jetson/tools/mock_server.py` serves the real `templates/index.html` + `static/` from the repo and fakes the Pixhawk+ESP32 side, so the whole GUI can be exercised in a browser without any Jetson/Pixhawk hardware.

## Run
```
pip install flask websockets
python3 jetson/tools/mock_server.py
# -> http://localhost:5000
```

Opens three websockets: `:8766` telemetry broadcast, `:8770` control, `:8765` signaling stub (so the browser doesn't error-loop on the WebRTC socket).

## Admin password
Hard-coded as `demo` — enough to unlock the Manual tab and the pre-arm bypass flow. Do not copy this into the real Jetson config.

## What the simulation does
- Battery decays (faster while armed).
- Vehicle drives a ~10 m circle when armed in AUTO; heads toward home in RTL; zero speed in HOLD; small drift in MANUAL.
- Sensor values oscillate with small noise.
- GPS reaches 3D fix at ~2 s, HOME sets at ~5 s.
- All link-age counters stay near zero (mock is the source).

## What it can't test
- Real video stream (video panel stays black).
- Actual RC override response on the Pixhawk.
- Fence-action enforcement (the mock ACKs upload but has no Pixhawk to enforce).

## Flask template caching gotcha
If you edit `index.html` or anything under `templates/` while the mock is running, the Jinja environment caches the compiled template. The mock has `TEMPLATES_AUTO_RELOAD = True` + `app.jinja_env.auto_reload = True` set, so this should pick up edits automatically — but if it ever stops working, restart the process.

## Sibling tool
`jetson/tools/ws_peek.py` — CLI that connects to `:8766` and pretty-prints the telemetry dict. Useful over SSH when you have the Jetson but no browser access. `--raw` for pipe-friendly output, `--keys K1,K2` to filter.
