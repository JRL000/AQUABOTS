#!/usr/bin/env bash
# Push local file(s) to the AquaBot Jetson and restart the matching systemd service.
# Run from this repo. Usage: ./push-to-jetson.sh <target>   (see --help)

set -euo pipefail

JETSON=jetson
APP_DIR=/home/mayra/AquaBotGUI_WebRTC

usage() {
  cat <<EOF
Usage: ./push-to-jetson.sh <target>

Targets:
  webrtc      jetson/webrtc_sender.py      -> ~/webrtc_jetson.py              (service: webrtc)
  app         jetson/app.py                -> ~/AquaBotGUI_WebRTC/app.py      (service: aquabot-app)
  signaling   jetson/signaling_server.py   -> ~/AquaBotGUI_WebRTC/            (service: signaling)
  mavproxy    jetson/mavproxy_launcher.py  -> ~/mavproxy_launcher.py          (service: mavproxy)
  ui          jetson/templates + static    -> ~/AquaBotGUI_WebRTC/            (service: aquabot-app)
  all         push every target above

Each target scp's the file(s), restarts the matching systemd --user service,
and prints the last 30 log lines so you can confirm it came up clean.

Jetson: $JETSON (Tailscale — Jetson must be online)
EOF
}

if [[ $# -eq 0 || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

cd "$(dirname "$0")/jetson"

restart_and_tail() {
  local unit="$1"
  ssh "$JETSON" "systemctl --user restart $unit && sleep 2 && journalctl --user -u $unit -n 30 --no-pager"
}

push_webrtc() {
  echo ">> webrtc_sender.py -> $JETSON:~/webrtc_jetson.py"
  scp webrtc_sender.py "$JETSON:/home/mayra/webrtc_jetson.py"
  restart_and_tail webrtc
}

push_app() {
  echo ">> app.py -> $JETSON:$APP_DIR/app.py"
  scp app.py "$JETSON:$APP_DIR/app.py"
  restart_and_tail aquabot-app
}

push_signaling() {
  echo ">> signaling_server.py -> $JETSON:$APP_DIR/"
  scp signaling_server.py "$JETSON:$APP_DIR/signaling_server.py"
  restart_and_tail signaling
}

push_mavproxy() {
  echo ">> mavproxy_launcher.py -> $JETSON:~/mavproxy_launcher.py"
  scp mavproxy_launcher.py "$JETSON:/home/mayra/mavproxy_launcher.py"
  restart_and_tail mavproxy
}

push_ui() {
  echo ">> templates/ + static/ -> $JETSON:$APP_DIR/"
  scp -r templates "$JETSON:$APP_DIR/"
  scp -r static    "$JETSON:$APP_DIR/"
  restart_and_tail aquabot-app
}

case "$1" in
  webrtc)    push_webrtc ;;
  app)       push_app ;;
  signaling) push_signaling ;;
  mavproxy)  push_mavproxy ;;
  ui)        push_ui ;;
  all)       push_webrtc; push_app; push_signaling; push_mavproxy; push_ui ;;
  *)         echo "unknown target: $1"; echo; usage; exit 1 ;;
esac

echo
echo "Done. Open http://100.76.1.26:5000 to verify."
