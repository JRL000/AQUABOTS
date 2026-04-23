---
title: "AQUABOTS — EMI Filtering Install Checklist (FAR-1)"
subtitle: "Team 26061 · ENGR 498B Spring 2026"
author: "Owner: John"
date: "Install date: 2026-04-23"
geometry: "margin=0.7in"
fontsize: 10pt
---

# AQUABOTS — EMI Filtering Install Checklist (FAR-1 patched)

**Date:** 2026-04-23 · **Owner:** John · **Team 26061**
**Reference:** `AQUABOTS_WIRING_GUIDE.md` Rev WG-3 + `AQUABOTS_EMI_INSTALL_GUIDE.md` Rev WG-3/FAR-1
**BOM:** `AQUABOTS_EMI_FILTERING_BOM.pdf` Rev ISR-4b — note deviations at end of doc
**Patched:** 2026-04-22 — realigned to FAR-1 converter consolidation (ESP32 moved onto 12V buck rail; 5V buck replaces Pixhawk Power Module; pH is UART not I²C)

**Goal:** Physically install all EMI filtering components (caps, ferrites, copper tape). Parts are on hand. None installed yet. Must be done before extended motor testing or any auto-mode water test — motor EMF will destroy compass/GPS data otherwise.

**Estimated time:** 2–3 hours including soldering, continuity checks, and shielding.

**Tools:** Soldering iron + fine solder + flux, heat shrink assortment, wire strippers, multimeter (continuity + voltage), zip ties, hot glue gun (optional), copper tape roll, automotive self-adhesion (electrical) tape, scissors.

**Prereqs:**

- [ ] Main battery DISCONNECTED at kill switch. Verify with multimeter across busbar (<0.1V).
- [ ] All converters off. No LEDs lit anywhere.
- [ ] Have the wiring guide (WG-3) and the install guide open for cross-reference.
- [ ] BOM PDF (Rev ISR-4b) nearby — some rows are stale; see "Deviations from BOM" at end.

---

## RULES (read once, apply everywhere)

1. **Polarity on electrolytics:** long lead = (+), stripe = (−). Getting this wrong pops the cap, potentially violently.
2. **Leads as short as physically possible.** Every mm of extra lead kills high-frequency filtering. Ceramic caps with 2" leads are useless.
3. **Ferrite clip-ons = ONE wire only** (the positive lead) — EXCEPT F4 which takes both wires for common-mode.
4. **Ferrite toroid (F1) = single pass** through the core. Do not wrap multiple turns at these currents.
5. **Copper tape shield = grounded at ONE end only** (source end). Both ends grounded = ground loop. No ends grounded = antenna.
6. **Install order matters:** busbar → ESC → buck inputs → buck outputs → sensor filters → copper tape last.
7. **After each section**, multimeter continuity check between (+) and (−) at the install point — must be NOT shorted before re-energizing.
8. **Secure everything** with zip ties or hot glue. This is a marine vehicle; vibration will break unsecured joints.

---

## SECTION 1 — Busbar Bypass (DO THIS FIRST)

Highest-priority filter. Catches ESC switching noise at the source bus.

- [ ] **1.1** Verify busbar is dead (multimeter <0.1V across studs).
- [ ] **1.2** Prepare **C1 (1000µF / 35V+ electrolytic):** crimp ring terminals to leads, leads <1".
- [ ] **1.3** Mount C1 across (+) and (−) busbar studs. **Polarity:** long lead / no stripe → (+) stud.
- [ ] **1.4** Prepare **C2 (100nF / 50V+ ceramic):** leads trimmed to <0.5".
- [ ] **1.5** Mount C2 in PARALLEL with C1 — same two studs. No polarity.
- [ ] **1.6** Zip-tie both caps so they can't swing.
- [ ] **1.7** Continuity check: (+) to (−) busbar should read **open (>1 MΩ)**. If shorted, stop and inspect.
- [ ] **1.8** Update power system changelog with install date.

---

## SECTION 2 — ESC / Motor Branch (F1 + C3 + C2)

Single biggest noise source in the whole system.

- [ ] **2.1** Identify the **8 AWG RED (+)** lead (**P5**) between MIDI 60A fuse and ESC input.
- [ ] **2.2** Disconnect ESC end. Thread 8 AWG wire through **F1 (Hondark 38×19×13mm MnZn toroid)** — **single pass, one time through.**
- [ ] **2.3** Position F1 within 2" of ESC power input. Zip-tie F1 to 8 AWG or adjacent structure so it can't slide.
- [ ] **2.4** Reconnect 8 AWG to ESC (+) terminal.
- [ ] **2.5** Prepare **C3 (470µF / 35V+ LOW-ESR electrolytic** — this is the only cap where low-ESR matters). Leads <0.5".
- [ ] **2.6** Solder C3 directly across ESC (+) and (−) power input terminals. **Polarity matters.**
- [ ] **2.7** Solder C2 (100nF ceramic, 50V+) in PARALLEL with C3 — same terminals.
- [ ] **2.8** Heat shrink or conformal coat the solder joints. Secure with zip tie.
- [ ] **2.9** Continuity check ESC (+) to (−): **open**, not shorted.

---

## SECTION 3 — 12V Buck / ESP32 Branch (FAR-1: ESP32 now on 12V rail)

> **FAR-1 change from original checklist:** ESP32 no longer has its own 5V buck. The 12V buck (P9 input) now feeds Jetson + fan + ESP32 VIN together. F2 here is the **same ferrite** you'll reuse conceptually for the branch that previously fed ESP32, but it's physically on **P9** (12V buck input), not P13. F4 moved from P21 → **P20** (12V buck output pair to ESP32).

ESP32's 2.4 GHz radio + analog ADC inputs are still the most EMI-sensitive loads. This branch gets **two ferrites** (input F2, output F4) plus output caps at each load.

### Input side (busbar → 12V buck)

- [ ] **3.1** On **12 AWG RED (+) wire (P9)** between **ATO 3A SB fuse** and 12V buck input: snap **F2 (Raogoodcx 13mm clip-on)** around the RED wire **only**. Within 2" of buck input.
- [ ] **3.2** Close clip-on, secure with tape or zip tie.

### Output side — common-mode filter on ESP32 pair

- [ ] **3.3** On **22 AWG pair (P20)** between 12V buck output and ESP32-S3 breakout VIN: snap **F4 (13mm clip-on)** around **BOTH wires together** (common-mode filter). Within 2" of ESP32 board.
- [ ] **3.4** Close clip-on, secure.

### Output caps at ESP32 VIN

- [ ] **3.5** Prepare **C4 (10µF / 25V+ electrolytic)** + **C2 (100nF ceramic)**. Leads as short as possible.
  - **WARNING — C4 voltage rating = 25V+ minimum.** ESP32 VIN sees 12V now (post-FAR-1), not 5V. A 10V-rated cap on a 12V rail will fail.
- [ ] **3.6** Solder C4 + C2 in PARALLEL across ESP32 VIN (+) and GND pins. C4 polarity matters. Within 0.5" of ESP32 header pins.
- [ ] **3.7** Continuity check VIN to GND: **open**, not shorted.

### Output caps at Jetson DC barrel (same 12V buck rail)

- [ ] **3.8** Prepare **C5 (100µF / 50V electrolytic, on hand)** + **C2 (100nF ceramic)**.
- [ ] **3.9** Solder C5 + C2 in PARALLEL across Jetson 12V DC barrel input (on the pigtail, before the barrel plug). C5 polarity matters. Within 1" of barrel.
- [ ] **3.10** Continuity check Jetson 12V input to GND: **open**.

> Fan runs off the same 12V output via its JST connector — no extra filtering.

---

## SECTION 4 — 5V Buck / Pixhawk POWER Branch (NEW in FAR-1)

> **NEW vs original checklist.** The dedicated 5V Power Module on the Pixhawk POWER port is **removed** under FAR-1; a generic 5V buck now feeds Pixhawk POWER (DF13 6-pin). The old Power Module had internal filtering; the generic buck does not — so this branch now needs its own bulk + HF bypass caps.

### Input side (busbar → 5V buck)

- [ ] **4.1** On **12 AWG RED (+) wire (P11)** between **ATO 2A SB fuse** and 5V buck input: snap **F2 (Raogoodcx 13mm clip-on)** around the RED wire **only**. Within 2" of buck input.
- [ ] **4.2** Close clip-on, secure.

### Output caps at Pixhawk POWER connector

- [ ] **4.3** Prepare **C5b (47µF / 10V+ electrolytic)** + **C2 (100nF ceramic)**. Leads as short as possible.
- [ ] **4.4** Solder C5b + C2 in PARALLEL across +5V and GND pins of the **DF13 6-pin Pixhawk POWER connector** (or on the harness pair <1" from the connector). C5b polarity matters.
- [ ] **4.5** Continuity check +5V to GND at connector: **open**, not shorted.

> **Brownout watch:** If the Pixhawk resets during ESC arm / calibration, the generic buck is sagging under inrush. Add a Schottky series diode + larger bulk cap at the POWER input, or revert this branch to a dedicated Pixhawk Power Module.

---

## SECTION 5 — Starlink Branch

- [ ] **5.1** On **12 AWG RED (+) wire (P7)** between ATO 7.5A SB fuse and Starlink DC input: snap **F3 (13mm clip-on)** around RED wire only. Within 3" of fuse block.
- [ ] **5.2** Prepare **C7 (100µF / 50V electrolytic, on hand)** + **C2 (100nF ceramic)**.
- [ ] **5.3** Solder C7 + C2 in PARALLEL at Starlink DC input connector. C7 polarity matters. Within 1" of connector.
- [ ] **5.4** Continuity check: **open**.

---

## SECTION 6 — BEC / Servo Branch (output caps only, no ferrite)

- [ ] **6.1** Prepare **C6 (100µF / 50V electrolytic, on hand)** + **C2 (100nF ceramic)**.
- [ ] **6.2** Solder C6 + C2 in PARALLEL at BEC output / servo connector. C6 polarity matters. Within 1" of servo plug.
- [ ] **6.3** Continuity check: **open**.

> BEC/servo branch has no input ferrite by design. The servo is the noise source, and the output cap absorbs it.

---

## SECTION 7 — Sensor Signal Filtering

> **Updated from original checklist:** pH sensor path is **UART @ 9600 baud** (per `firmware/main/sensor_bridge.c`), not I²C. F5 ferrite beads on SDA/SCL are **NOT** installed up-front. Do not cut and splice inline beads at this stage. If pool-test reveals noise, retrofit a clip-on ferrite on the CAT6 bundle at the ESP32 end.

### Critical — TDS analog

- [ ] **7.1** Solder **C2 (100nF ceramic)** pin-to-GND at **TDS analog input (S10)** on ESP32 ADC pin. Within 0.25" of pin. **This is critical** — TDS is the most noise-vulnerable signal on the boat.

### Optional / pool-test-gated

- [ ] **7.2** (**SKIP up-front**) pH UART noise filtering — do NOT install F5 beads inline on SDA/SCL (protocol is UART now, not I²C). If pool-test motor-on run shows framing errors on pH, add a single 13mm clip-on ferrite on the CAT6 at the ESP32 end. Document and re-verify.
- [ ] **7.3** (Optional, defer unless visible noise) 100nF ceramic pin-to-GND on **1-Wire DS18B20 (S9)** — within 0.5" of ESP32 pin.
- [ ] **7.4** S7 (IMU) and S11 (GPS) — **DO NOT install anything.** Both sensors removed in WG-2; Pixhawk built-in IMU and M8N GPS replace them.

---

## SECTION 8 — Copper Tape Shielding (DO LAST)

Shielding goes on AFTER all filter components are installed and bench-verified.

### Cable shielding

- [ ] **8.1** **P20** (12V buck → ESP32, 22 AWG pair) — wrap length of cable with copper tape. Leave a ~2" drain tail at the **12V buck (source) end**. Solder drain to 12V buck GND. Leave ESP32 end floating.
- [ ] **8.2** **S1** (ESP32 UART → Pixhawk, JST-SH 4-pin) — wrap with copper tape. Drain tail at **ESP32 (source) end** → ESP32 GND. Pixhawk end floating.
- [ ] **8.3** **S10 TDS** — already inside the CAT6 foil bundle. **SKIP** individual wrap.
- [ ] **8.4** **CAT6 sensor bundle** — verify foil shield drain is landed at **ESP32 GND only**. Bow end floating. (Should already be correct per wiring guide.)

### Component body shielding (NEW — WG-2, all to (−) busbar)

- [ ] **8.5** Wrap **ESC body** with copper tape (avoid heatsink fins — don't thermally trap the ESC). Drain to **(−) busbar** via short wire. One end only.
- [ ] **8.6** Wrap **BEC body** with copper tape. Drain to (−) busbar. One end only.
- [ ] **8.7** Wrap **12V buck converter body** with copper tape. Drain to (−) busbar. One end only.
- [ ] **8.8** Wrap **5V buck converter body** with copper tape. Drain to (−) busbar. One end only.

> **Never daisy-chain drains.** One drain per body → its own short run to (−) busbar.

### After any copper tape install

- [ ] **8.9** Cover exposed copper tape with **automotive self-adhesion tape (SH2)** so it can't short against neighbor components.
- [ ] **8.10** Continuity check: each shielded cable — drain wire to destination GND = **closed** (through ground path), drain to (+) rail = **open**.

---

## POST-INSTALL VERIFICATION

- [ ] **V1.** Visual inspection: no loose solder, no pinched wires, all caps secured, no copper tape touching unintended surfaces.
- [ ] **V2.** Full busbar continuity: (+) to (−) = **open (>1 MΩ)**. If shorted anywhere, stop and find it before re-energizing.
- [ ] **V3.** Reconnect battery at kill switch. Look for smoke. (Yes, really.)
- [ ] **V4.** Voltage check each branch output:
  - Busbar ~22–26V
  - 5V buck output (to Pixhawk POWER) = **5.0 ±0.1V**
  - 12V buck output (to Jetson + ESP32 + fan) = **12.0 ±0.2V**
  - BEC output = per BEC spec (5.5V or 6V typical)
  - *(Removed vs original checklist: "Pixhawk 5V rail from Power Module" — the Power Module was removed in FAR-1. Pixhawk POWER is now fed by the 5V buck above.)*
- [ ] **V5.** Power on motor briefly (prop removed, low throttle). No smoke, no abnormal buzz, no voltage sag > 0.5V on any rail.
- [ ] **V6.** Check compass heading in QGC — should be stable with motor OFF. With motor running at low throttle, heading should shift **<2°** from static value. If >5° shift, EMI is still a problem.

---

## UPDATE DOCS AFTER INSTALL

- Update `AQUABOTS_EMI_FILTERING_BOM.pdf` status column: ORDER → INSTALLED for each part. (Deferred — BOM Rev ISR-5 regen is a separate task.)
- Update `AQUABOTS_POWER_SYSTEM_CHANGELOG.md` with install date and append Rev ISR-5 block.
- Bump `AQUABOTS_WIRING_GUIDE.md` WG-3 → WG-4 with summary: "EMI filtering installed. Production DSServo + new BEC wired. Compass + accel recalibrated post-install."
- Record SERVO1 calibration values (MIN/MAX/TRIM/REVERSED) in wiring guide or a new `PIXHAWK_SERVO_CONFIG.md`.

---

## KNOWN DEVIATIONS FROM BOM Rev ISR-4b

| BOM says | Actual install | Reason |
|---|---|---|
| 4 ferrite beads (2 pH + 2 IMU) | **0 beads up-front** (add one CAT6 clip-on if pool-test shows noise) | S7 IMU removed in WG-2 (Pixhawk built-in IMU). pH moved from I²C to UART per `sensor_bridge.c`. |
| Copper tape: P21, S10, sensor bundle, optional S1/S2 | P20 (not P21) + S1 + **ESC body + BEC body + 2× buck bodies** | FAR-1 moved ESP32 to 12V buck (P21→P20). WG-2 added component-body wraps for radiated emission. |
| 5V Power Module on Pixhawk POWER | Generic 5V buck + new caps (C5b 47µF/10V+ in parallel with C2) | FAR-1 consolidation — Power Module removed, buck does not include internal filtering. |
| C4 = 10µF / 10V+ on ESP32 VIN | **C4 = 10µF / 25V+** | ESP32 VIN now 12V (FAR-1), not 5V. 10V-rated cap would fail. |

These deviations feed into BOM Rev ISR-5 regeneration (separate task, not in scope for today's install).

---

## DO-NOT-DO LIST

- Do NOT energize anything until ALL continuity checks pass.
- Do NOT ground both ends of any shield. Source end only.
- Do NOT multi-turn the F1 toroid. Single pass only.
- Do NOT swap the F4 common-mode ferrite for a single-wire install — the common-mode topology is intentional.
- Do NOT skip the 100nF ceramic in any parallel pair. The electrolytic alone covers low frequencies only.
- Do NOT cut and solder F5 beads inline on pH SDA/SCL — pH is UART, not I²C.
- Do NOT use a 10V-rated cap on the ESP32 VIN rail — it's 12V post-FAR-1.
- Do NOT skip C5b at the Pixhawk POWER connector — the old Power Module's internal filtering is gone.
