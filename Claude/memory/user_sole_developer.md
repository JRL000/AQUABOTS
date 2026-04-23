---
name: User is the sole active developer on the AQUABOTS repo
description: John is the only person pushing to this repo — teammates have access but choose not to use git. Merges/pushes to main don't need cross-team coordination.
type: user
---

John is the only person actively using the AQUABOTS git repo as of 2026-04-23. Teammates on the capstone have repo access but have declined to adopt git as a workflow.

**How to apply:** When a planned action touches shared branches (push to main, force-push, branch deletion, etc.), no need to ask "is anyone else working on this?" — there isn't. Still warn before destructive ops (force-push, reset --hard, branch delete), but don't gate them on teammate coordination.
