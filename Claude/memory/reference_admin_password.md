---
name: AquaBot admin password storage
description: GUI admin password is loaded from an env file on the Jetson (not in git); set via aquabot-app.service's EnvironmentFile directive.
type: reference
---

The AquaBot GUI's admin features (Manual tab, pre-arm bypass) are gated by a password read from `AQUABOT_ADMIN_PW`. As of 2026-04-23, the password lives in:

- **File:** `/home/mayra/.config/aquabot.env` on the Jetson (chmod 600, mayra-owned)
- **Format:** `AQUABOT_ADMIN_PW=<password>` on a single line
- **Loaded by:** `jetson/systemd/aquabot-app.service` via `EnvironmentFile=-%h/.config/aquabot.env` (leading `-` = optional; service still starts if file missing, admin stays disabled)

**NOT in git** — that's the whole point of the env-file pattern. If a future session needs to update the password, edit the file on the Jetson and `systemctl --user restart aquabot-app`. Don't put the password in the committed .service file.

**Verify it's loaded:** `ssh jetson "systemctl --user show aquabot-app -p Environment"` — should list AQUABOT_ADMIN_PW with the value (the env is logged plaintext here, fine for local inspection).
