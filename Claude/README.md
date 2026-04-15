# Claude memory snapshot

This folder mirrors Claude Code's project memory for the AQUABOTS repo. It's kept here so you can move it between machines (the live copy lives under `%USERPROFILE%\.claude\projects\...\memory\` which doesn't sync automatically between PCs).

## Files
- `MEMORY.md` — index of memory entries (this is what Claude loads into context each turn).
- `memory/*.md` — the actual memory content files referenced from `MEMORY.md`.

## To install on another PC
1. Open Claude Code in the AQUABOTS repo at least once so the harness creates the project folder under `%USERPROFILE%\.claude\projects\<hashed-repo-path>\`.
2. Copy `MEMORY.md` from here to that folder's root.
3. Copy everything in `memory/` here into the corresponding `memory/` subfolder there (create it if missing).
4. Start a new Claude Code session in the repo; you should see the entries when Claude accesses memory.

## Keeping it in sync
This folder is **tracked by git** (it was un-gitignored in this repo). After any session where memory or session notes change, mirror the live files over the copies here and commit them along with the rest of your work. On another PC, just `git pull` and run the "install on another PC" steps to rehydrate `%USERPROFILE%\.claude\projects\...\` from these files.

Easiest one-liner (PowerShell / Git Bash, run from the repo root after a memory change):
```
cp -r "$USERPROFILE/.claude/projects/C--Users-ual-laptop-Documents-AQUABOTS/MEMORY.md" Claude/
cp -r "$USERPROFILE/.claude/projects/C--Users-ual-laptop-Documents-AQUABOTS/memory/"* Claude/memory/
```
