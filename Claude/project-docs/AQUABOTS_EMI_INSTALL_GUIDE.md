# MOVED — merged into AQUABOTS_EMI_INSTALL_PROCEDURE.md (Rev WG-2)

This document (originally Rev WG-3 / FAR-1, 2026-04-12) has been merged with the field-procedures EMI install checklist into a single comprehensive procedure. **The merged procedure has been corrected to WG-2 reality** — the FAR-1 converter consolidation captured here was a paper-only architecture change and was never installed.

**Current source of truth:** [`AQUABOTS_EMI_INSTALL_PROCEDURE.md`](./AQUABOTS_EMI_INSTALL_PROCEDURE.md) (Rev WG-2, 2026-04-26).

The merged procedure preserves everything from this guide that was correct under WG-2 (per-component placement spec, universal rules, soldering cheat sheet, total part counts) plus the per-section continuity gates and V1–V6 verification from the EMI checklist. It explicitly removes the FAR-1 wire-ID swaps (ESP32 on 12V buck, generic 5V buck → Pixhawk with C5b) — those never happened in hardware. Use the merged procedure during the install — do not flip back to this stub.
