---
name: PINNED feature request — swarm formation + manual node separation
description: Multi-node formation control + on-demand node detach-to-waypoint with auto-rejoin fallback. User wants a PLAN only (no implementation yet) on branch `swarm-formation`.
type: project
---

**Status:** PINNED — pinned 2026-04-23 after the branch merge. Work continues on branch `swarm-formation` (created 2026-04-23, branched from `main` at db7c2ff). User wants a DESIGN PLAN only, no code yet.

**User's ask (verbatim intent):**
1. Formation control — pick a shape OR draw one on screen; leader node decides how to fit the swarm into that shape and coordinates positions.
2. Manual node separation — operator picks any number of nodes, sends them to a waypoint; on arrival the detached node(s) hold and await further orders.
3. Auto-rejoin fallback — if the swarm (or the nearest swarm node) drifts too far from a detached node, the detached node falls back into formation.
4. Safety — do it safely; user asked Claude to catch gaps and suggest missing functionality they didn't think of.

**How to apply:** When the user returns to this, produce a design doc (not code). Cover:
- Leader election, leader-loss fallback
- Inter-node comms (mesh? star through Jetson? RF range, latency budget)
- Shape-fitting algorithm (anchor to leader vs. centroid; rotation/scale based on swarm size)
- Safety layers: collision avoidance between nodes, per-node geofence, max-speed caps during formation, link-loss behavior per-node
- Operator UX: how to pick/draw shapes, how to select "these 3 nodes go detach", visual state per node in GUI
- State machine per node: IN_FORMATION / DETACHING / AT_DETACH_WAYPOINT / REJOINING / HOLD / FAILSAFE
- Gaps to flag: what happens if detached node loses GPS, what if rejoin path crosses geofence, what if two operators issue conflicting orders, battery-aware behavior, how leader handoff works if the current leader is one of the nodes being detached.
