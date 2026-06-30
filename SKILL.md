---
name: session-find
description: Find, query, and locate past Claude Code sessions — use whenever the user wants to find an old session, resume one, find which session discussed a topic, or complains they "can't find a session". Trigger phrases include "find the session where I talked about X", "find that session again", "which session discussed X", "I can't find a session anymore", "did I ever chat about X", "continue the one where we discussed X", "where did I leave off" (referring to another session). Even if the user doesn't say the word "session", use this whenever the intent is locating a past conversation rather than the current one. It works around the `claude -r` picker list, which is a black box that hides sessions that are in-use, queue-operation, or non-interactive types — giving a complete view the picker can't, plus exact resume commands. Proactively use this skill whenever the user repeatedly needs to locate sessions; don't make them dig through the `-r` list manually.
version: 2.0.0
---

# Session Find

Help the user find and locate past Claude Code sessions.

**Why this exists**: the `claude -r` (or `claude --resume`) picker list hides some sessions — those held by a live process (`status=busy`), programmatic calls (`queue-operation` first-line type), and other non-interactive entry types (`attachment` / `system` / `mode`). Users routinely hit "the session isn't in the list but I can resume by ID". This skill scans the jsonl files directly for a complete view.

## When to use

**Use it** when the user wants to locate a past session. Signals:
- Explicit: "find the session where I chatted about X", "bring back that session", "which session covered X", "I can't find a session"
- Implicit: "continue the one where we discussed X", "did I ever talk about X", "where did I leave off" (about another session, not the current one)
- Location intent: the user remembers a topic / a file they read / a task they did, and wants the session it happened in

**Don't use** when:
- The user asks "did we say X" inside the **current** session — that's current context, not a historical session.
- The user already has a full session ID and just wants to resume — give them `claude --resume <id> "continue"` directly, no query needed.

## The tool

`cc_sessions.py` is bundled at `scripts/cc_sessions.py` inside this skill. Invoke it with `python3` (don't rely on the `ccl` alias — a fresh Bash shell may not load aliases):

```bash
python3 ~/.claude/skills/session-find/scripts/cc_sessions.py [opts]
```

It works across all projects — it scans `~/.claude/projects/` wholesale.

## Core flow

### 1. Extract query dimensions

Pull these from the user's message (ask if missing — don't drag it out over multiple turns):
- **Keyword** — topic / tech term / project name (e.g. "channel", "CardPager", "auth")
- **Time window** — roughly how long ago (default: last 30 days)
- **Anchor document** — the user remembers the session opened by reading a specific file (a handoff doc, a spec). This is the **strongest** signal — use the anchor method below.

### 2. Run the query

```bash
# Keyword + time window (most common)
python3 ~/.claude/skills/session-find/scripts/cc_sessions.py -k <keyword> -d <days>

# Details + exact resume command for a candidate
python3 ~/.claude/skills/session-find/scripts/cc_sessions.py <ID-prefix-or-full>

# Scan all projects
python3 ~/.claude/skills/session-find/scripts/cc_sessions.py -a -k <keyword>
```

### 3. Read the output, narrow for the user

Each row is one session:
```
M   ID(full)                              Time        type            Name         B   First prompt
✅/⚠️  <uuid>                              06-30 12:00 last-prompt     卡片阅读 05      <first user message>
```

- **✅** likely visible in the `-r` list; **⚠️** likely hidden (in-use / queue-op / non-interactive) — these are exactly the sessions the user can't find via `-r`
- **B=`*`**: a live process is holding the session (the user may already have it open in another terminal)
- **First prompt**: the session's first user message — the strongest identification signal
- **Name**: custom title (user-chosen) > AI-generated title > agent name

Rank candidates by relevance and give a one-line summary each (based on first prompt + name). **List up to 5; for more, show top 5 and say "N more — narrow down if you want".**

### 4. Give the resume command

Once the user picks one, give the exact command (a prompt is required):

```bash
cd "<project cwd>" && claude --resume <full-ID> "continue"
```

**Why a prompt is required**: on 2.1.170, `claude --resume <id>` without a prompt fails with `No deferred tool marker found` — it tries to restore an interrupted tool call from the tail of the session, and old sessions don't have that marker. A prompt bypasses that path. Let the user rewrite `"continue"` into their own phrasing (e.g. `"keep working on the channel feature"`).

Use `cc_sessions.py <ID>` detail mode to get this command pre-built with the correct cwd.

## Anchor document method (strong localization)

When the user says "the session that started by reading `channel-handoff.md`", that's far more precise than a keyword. Grep every session's jsonl for that filename and rank by first-occurrence line number:

```python
import json, glob, os
KEY = "channel-handoff"   # fragment of the filename
rows = []
for f in glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl")):
    for i, line in enumerate(open(f, encoding="utf-8")):
        if KEY in line:
            rows.append((i + 1, os.path.basename(f)[:8]))
            break
rows.sort(key=lambda x: x[0])
for first, sid in rows:
    print(first, sid)
```

**How to read the result**: first occurrences at line 1–3 are almost always the SessionStart hook injecting the INDEX (a false positive — nearly every session has it). **First occurrence at line tens-to-hundreds is the real reference** — that's the entry session you're looking for.

## Key constraints

- **Always query via `cc_sessions.py` — never tell the user to rely on the `claude -r` list.** The list drops sessions, which is the whole reason this skill exists.
- **The resume command always needs a prompt**: `claude --resume <id> "continue"`. Without one, it errors out on 2.1.170.
- **Don't touch sessions the user is currently using**: if a candidate shows in-use (`B=*`), tell the user they may already have it open elsewhere — **don't kill the process** without asking first.
- **Prefer fewer, better candidates**: when there are too many, narrow first (add a keyword, shrink the time window) instead of dumping a wall of sessions on the user.

## Background

For the full mechanism — session storage layout (`projects/` / `sessions/` / `session-env/`), why the picker list filters, the cwd→projdir encoding rule, and the three `-r` gotchas — see the user's knowledge base note at `~/all_wendang/my-knowledge-base/wiki/cc-session-recovery.md`.
