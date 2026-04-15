---
name: CSI camera clamp physically broken
description: The Jetson's single usable CSI port has a broken FPC latch; camera only works if ribbon is held down by hand or wedged, and any power-cycle typically dislodges it.
type: project
originSessionId: 6350b94f-1a52-4fc2-ae1f-71e82b0851d6
---
The Jetson carrier's CSI connector for the active camera port (driven by `nvarguscamerasrc sensor-id=0`, the only module declared in the device tree — `module0` / `jakku_front_RBP194`) has a **broken FPC clamp/latch**. The ribbon cannot be locked down reliably.

Symptoms in dmesg when the clamp slips:
- `imx219 9-0010: imx219_board_setup: error during i2c read probe (-121)`
- `probe of 9-0010 failed with error -121`
- `/dev/video0` missing
- nvargus-daemon: `SCF: Error BadParameter: Sensor could not be opened.`
- GStreamer: `No cameras available`

**Why:** User confirmed on 2026-04-14 that the clamp is physically broken. Sessions when the camera "worked" were cases where they held the ribbon down by hand during the boot probe. Power-cycles almost always knock it loose again.

**How to apply:**
- When either CSI port fails with `-121` after a reboot, do NOT assume it's software. It's the clamp. Advise reseating and physically holding the ribbon until dmesg confirms `imx219 N-0010 bound`.
- Specifically: the carrier's **CAM0/port-A clamp is broken**; **CAM1/port-C clamp is intact**. Default plan is to run on CAM1 (with dual-IMX219 DT overlay, select via `nvarguscamerasrc sensor-id=1`). CAM0 is the fallback and only usable by manually holding the ribbon.
- Any hardware fix plan for this boat should include replacing the carrier board, soldering a new FPC connector on port A, or adding a mechanical wedge/fixture to retain the ribbon.
- Don't pin the camera failure mode on ribbon orientation (UC-376 vs UC-440 conversation) — the root cause here is the broken latch, not the cable type.
- Software-level retry in `webrtc_sender.py` only paints over this: the camera subsystem will stay dead until the ribbon makes contact, then needs a reboot/service restart to re-probe.
