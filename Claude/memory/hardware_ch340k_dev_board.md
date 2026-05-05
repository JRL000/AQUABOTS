---
name: ESP32-S3 swarm board with CH340K USB-UART bridge — flash works, console needs sdkconfig patch
description: At least one swarm board variant uses a CH340K USB-UART bridge instead of relying on the chip's native USB Serial/JTAG. The default firmware build routes the IDF console to USB Serial/JTAG (silent on this board) and chip stays stuck in DOWNLOAD mode after flash. Workaround: patch sdkconfig to route console to UART0; physically press EN/RST after flash.
type: project
---
This is a hardware-side observation, not yet a fixed-in-code state. Documenting so the next person to flash boards has a fighting chance.

## Two board variants exist

The PC session that built `pixhawk_link` (commit `0ac5b6a`, 2026-05-03) was working with boards whose native USB Serial/JTAG enumerates cleanly — `idf.py monitor` over the chip's native USB shows the `swarm>` prompt, and the existing `sdkconfig.defaults` line `CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y` (added in commit `00facad` from 2026-04-27) is correct for those boards.

The laptop session (2026-05-05, mid-flash workflow per `Claude/NEXT_STEPS.md`) hit a board whose native USB **does not** enumerate cleanly — Windows reports `Unknown USB Device (Device Descriptor Request Failed)` with VID/PID `0000/0002`, balloon "device not recognized." Same board has a working CH340K USB-UART bridge (VID `1A86`, PID `7522`) on its primary USB-C connector that flashes fine but gives no console output with the default firmware build.

Both variants are "ESP32-S3" — the difference is in the dev kit's USB wiring, not the chip. The PC and laptop sessions probably have different physical board models.

## Required workaround on the laptop's CH340K board

1. Edit `firmware/sdkconfig` (the runtime file, **not** `sdkconfig.defaults` — that goes to git and would break the PC's working boards):
   ```
   # CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG is not set
   CONFIG_ESP_CONSOLE_UART_DEFAULT=y
   CONFIG_ESP_CONSOLE_UART_NUM=0
   # CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG_ENABLED is not set
   ```
2. `idf.py build`
3. `idf.py -p COM<N> flash` over the CH340K port

`firmware/sdkconfig` is gitignored (`.gitignore` line 13), so this patch never reaches origin.

## Open issue not resolved 2026-05-05 — chip stays in DOWNLOAD mode after flash

After successful flash, the chip's next boot was repeatedly:

```
ESP-ROM:esp32s3-20210327
rst:0x1 (POWERON), boot:0x0 (DOWNLOAD(USB/UART0))
waiting for download
```

`boot:0x0` = both GPIO0 and GPIO46 strap pins low at reset → ROM download mode, not the flashed firmware. esptool's `--after hard_reset` and pyserial DTR/RTS pulses (both polarities) failed to drop the chip into normal-boot. The CH340K auto-reset transistor circuit on this board's wiring evidently does not match the polarity esptool expects.

**Untested next step: physically press the dev board's EN/RST button after the flash command finishes.** That bypasses the auto-reset circuit entirely. User went away mid-session before this could be tried.

## How to identify which variant a board is

```powershell
Get-PnpDevice -Class Ports -PresentOnly | Format-List FriendlyName, Status
```

- `USB-SERIAL CH340K (COM<N>)` with Status OK → laptop variant; apply the workaround above.
- `Espressif USB JTAG/serial debug unit (COM<N>)` or VID `303A` → PC variant; default sdkconfig works.

`[System.IO.Ports.SerialPort]::GetPortNames()` is **not reliable** on this Windows install — it returns stale entries (saw a "phantom COM5" persist after the device was unplugged). Use `Get-PnpDevice` for authoritative state.

## Outstanding cleanup

- Decide whether the project should support both board variants in `sdkconfig.defaults` via a build-time flag, or just standardize on one. Today the firmware default (`USB_SERIAL_JTAG`) is right for the PC's boards and wrong for the laptop's.
- If the boards getting flashed for the demo are actually a mix of both variants, this needs to be solved before anyone re-flashes from scratch.
