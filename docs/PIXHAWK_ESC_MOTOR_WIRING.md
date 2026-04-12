# Pixhawk 4X → Apisqueen 80A ESC → Apisqueen 5080 Motor
## Wiring & Verification Guide

**Date:** 04-08-2026 (Rev 1), reviewed 04-11-2026
**Status:** Wiring complete. Motor armed and throttled from GUI (MAVLink RC override) verified 04-10-2026 bench test. This guide is now a reference for rebuilds / replacements, not a live pre-wiring checklist.

---

## Critical Context: ESC Signal Source

**Pixhawk** handles all flight control — motor/ESC PWM, navigation, attitude, heading.
**ESP32** handles sensors and ESP-NOW inter-drone communication only.

The Pixhawk → ESC path described in this guide is the **final design**. The project summary (`AQUABOTS_PROJECT_SUMMARY.md` §2.4) is aligned with this as of Rev FAR-1.

---

## ESC Protocol Confirmation

**Apisqueen 80A ESC, 3–12S LiPo, 5V BEC** uses **standard PWM only**:

| Parameter | Value |
|-----------|-------|
| Protocol | Standard PWM |
| Min throttle | 1100 µs |
| Max throttle | 1900 µs |
| Frequency | 50 Hz |
| DSHOT / OneShot | Not supported |

Standard PWM is the simplest protocol — easiest to drive from Pixhawk and verify with basic tools.

### Before wiring, physically confirm on your ESC:

1. **Servo plug wire order** — Standard is: Signal (white/yellow) | +5V BEC (red) | GND (black).
   Verify this matches your ESC before plugging in — some units deviate.
2. **Motor bullet connector size** — Apisqueen 5080 uses **4mm bullet connectors**
   (female on motor, male on ESC). Confirm yours match.

---

## Wiring Connections

### 1. ESC Power Input (thick wires)

These follow the existing harness design:

| From | To | Wire | Fuse |
|------|----|------|------|
| (+) Busbar | ESC positive lead | 8 AWG red | MIDI 60A |
| (–) Busbar | ESC negative lead | 8 AWG black | — (return path) |

> **Do not connect battery until all signal wiring is verified (see Step 3 below).**

---

### 2. Pixhawk 4X → ESC Signal (3-pin servo connector)

Use the **I/O PWM OUT** port on the Pixhawk 4X — the 8-channel row labeled "MAIN OUT".  
Use **MAIN 3** (throttle output in ArduPilot Rover/Boat configuration).

```
Pixhawk MAIN 3            ESC Servo Plug
──────────────            ──────────────
S  (Signal)    ────────── Signal (white/yellow)
+  (5V rail)   ────────── +5V BEC (red)
-  (GND)       ────────── GND (black)
```

**On the +5V line:** The Pixhawk 4X servo rail (MAIN OUT) is **not powered by the power module** —
it is a floating bus by default. The ESC's 5V BEC output is what powers it. Connect the red wire.
Without it the servo rail is dead and no servos or peripherals on the rail will work.

**On GND:** Required for a common ground reference between Pixhawk and ESC. Do not skip.

**Wire spec:** 22 AWG, standard 3-pin servo connector (matches §2.4 signal interconnects).

---

### 3. ESC → Apisqueen 5080 Motor (3-phase)

| ESC Output | Motor Wire | Notes |
|------------|-----------|-------|
| Phase A (4mm bullet) | Motor wire 1 | Initial order arbitrary |
| Phase B (4mm bullet) | Motor wire 2 | |
| Phase C (4mm bullet) | Motor wire 3 | |

> **Direction:** If the motor spins the wrong way after first test, swap any two of the three
> phase wires. Do NOT reverse DC polarity to fix direction — swap phases only.

---

## Verification Sequence

> **Required tool:** A **servo tester** (~$10) — a standard multimeter cannot read 50 Hz PWM
> pulse width. An oscilloscope also works.

### Step 1 — Firmware Check

- Connect Pixhawk to QGroundControl via USB.
- Confirm firmware is **ArduPilot ArduRover** (for a surface boat).
  - If PX4 is installed instead, the output channel mapping differs — resolve this before continuing.
- Verify the vehicle frame is set to **Rover / Boat**.

### Step 2 — ESC Calibration (required before first use)

The ESC must learn the throttle endpoints from the Pixhawk before it will respond correctly.

1. Disconnect motor from ESC (do not have motor connected yet).
2. Disconnect battery.
3. Set throttle to **maximum** (radio or QGroundControl joystick).
4. Connect battery — ESC plays startup tone sequence.
5. When you hear a **double-beep**, move throttle to **minimum**.
6. ESC plays calibration confirmation tones.
7. Disconnect battery.

### Step 3 — Signal Verification with Servo Tester (no battery, no ESC)

1. Connect servo tester to Pixhawk **MAIN 3** (instead of ESC servo plug).
2. Power Pixhawk via USB only — no battery, no ESC connected.
3. In QGroundControl: temporarily disable arming checks for bench test.
4. Arm the vehicle (joystick or safety switch — see note below).
5. Sweep throttle input.

**Pass:** Servo tester arm sweeps. Pixhawk is outputting PWM on MAIN 3.  
**Fail:** Arm is stationary — check arming state, output channel mapping, and safety switch.

> **Safety switch note:** The Pixhawk 4X has an external safety button. Press and hold until
> it goes **solid** (stops blinking) before arming will work.

### Step 4 — ESC Connected, Motor Disconnected

1. Connect ESC servo plug to Pixhawk MAIN 3.
2. Connect battery through kill switch.
3. Motor **not connected** yet.
4. Arm and apply minimal throttle.
5. ESC should play initialization sequence: **3 beeps** (cell count detection) followed by a
   ready tone.

**Pass:** ESC initializes and responds to throttle input.  
**Fail:** No tones — check servo plug wire order, BEC +5V connection, and arming state.

### Step 5 — Full Chain Test (motor connected, no prop/load)

1. Connect the 3 motor phase wires to the ESC.
2. Keep motor unloaded — no propeller, no thruster attached.
3. Arm, advance throttle slowly from minimum.
4. Motor should spin smoothly.
5. If direction is wrong, swap any two phase wires and retest.

---

## Configuration Notes (Resolved as of 04-11-2026 bench test)

| Item | Current Setting |
|------|-----------------|
| Firmware | ArduPilot ArduRover (Rover / Boat frame) |
| ESC calibrated | Yes (bench test 04-10-2026) |
| Safety switch | Installed and pressed-solid before arming |
| Command source | QGroundControl joystick and operator-dashboard MAVLink RC override |

---

## Architecture Note

Pixhawk handles all flight control — motor/ESC PWM, navigation, attitude, heading.
ESP32 handles sensors (pH via UART, temp via 1-Wire, TDS/salinity via ADC, ultrasonic via UART) and ESP-NOW inter-drone communication. IMU and GPS are now the Pixhawk's built-ins (see `AQUABOTS_WIRING_GUIDE.md` Rev WG-3 — S7/S11 removed).
The Pixhawk → ESC connection above is the **final design**, not a temporary test path.
