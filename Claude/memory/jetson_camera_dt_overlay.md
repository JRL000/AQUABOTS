---
name: Jetson dual-IMX219 device tree overlay
description: The Jetson Orin Nano carrier was flashed to the "Camera IMX219 Dual" overlay on 2026-04-14 so both CSI ports can enumerate; sensor-id=0 = port A (broken clamp), sensor-id=1 = port C (working clamp).
type: project
originSessionId: 6350b94f-1a52-4fc2-ae1f-71e82b0851d6
---
On 2026-04-14, switched the Jetson's boot-time CSI device tree overlay from single-port (`imx219-A`) to dual-port (`imx219-dual`) so both carrier CSI connectors are declared at the kernel level.

**Hardware context:**
- Board: Jetson Orin Nano Developer Kit, carrier P3767 / module P3768.
- Overlay now in use: `/boot/tegra234-p3767-camera-p3768-imx219-dual.dtbo`
- Previous overlay: `/boot/tegra234-p3767-camera-p3768-imx219-A.dtbo`
- Tool used: `sudo /opt/nvidia/jetson-io/config-by-hardware.py -n 2="Camera IMX219 Dual"` (non-interactive sibling of `jetson-io.py`).

**Why:** The CAM0 / port-A FPC clamp is physically broken (see `hardware_camera_clamp.md`). The dual overlay lets the operator run on port C (working clamp) via `sensor-id=1` and keep port A as a manual-hold fallback via `sensor-id=0`. Without the dual overlay, only one module is declared and `sensor-id=1` returns "No cameras available" from argus regardless of which connector the ribbon is in.

**How to apply:**
- Expect `/proc/device-tree/tegra-camera-platform/modules/` to list both `module0` and `module1` after a reboot. Only one ribbon is typically connected; the other slot binds "ghost" (no sensor present → `-121` on that bus is normal and NOT a bug).
- `nvarguscamerasrc sensor-id=0` → port A; `sensor-id=1` → port C. This is the argus enumeration order the dual overlay produces; confirm with dmesg if ever in doubt.
- To revert to single-cam: `sudo /opt/nvidia/jetson-io/config-by-hardware.py -n 2="Camera IMX219-A"` OR restore from backup `/boot/extlinux/extlinux.conf.backup-20260414-180040` (+ reboot).
- Don't edit `/boot/extlinux/extlinux.conf` by hand; use `config-by-hardware.py` so jetson-io keeps its bookkeeping consistent.

**Known unknowns (2026-04-14 session end):** After applying the dual overlay and power-cycling the Jetson, it did not return to the tailnet within ~3 minutes. Could be unrelated (Tailscale reconnect, ribbon work in progress), could be an overlay-induced boot issue. Before assuming trouble, verify power LED and HDMI output. Fallback path if the kernel won't boot: boot from USB recovery, restore extlinux.conf backup.
