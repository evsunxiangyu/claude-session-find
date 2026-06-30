#!/usr/bin/env python3
"""cc_sessions — list and query Claude Code sessions.

Bypasses the `claude --resume` picker list, which is a TUI black box that hides
some sessions (those in-use, or of queue-operation / non-interactive types).
Scans the on-disk jsonl files plus the sessions/ registry directly, giving a
complete view the picker can't.

Usage:
  cc_sessions                       # current project, recent 30
  cc_sessions -k yiweiy             # filter by first-prompt / name keyword
  cc_sessions -d 7                  # last 7 days
  cc_sessions -n 50                 # show 50
  cc_sessions -a                    # all projects
  cc_sessions --id 4987b3c4         # details + exact resume command
  cc_sessions 4987b3c4              # positional, equivalent to --id

Suggested alias (add to ~/.zshrc):
  alias ccl='python3 ~/.claude/skills/session-find/scripts/cc_sessions.py'
"""
import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime

CLAUDE_DIR = os.path.expanduser("~/.claude")
PROJECTS = os.path.join(CLAUDE_DIR, "projects")
SESSIONS = os.path.join(CLAUDE_DIR, "sessions")


def cwd_to_projdir(cwd):
    # Claude Code encodes cwd into a projects/ dir name by replacing every
    # non-alphanumeric character with '-'. Verified against 2.1.170.
    # e.g. /Users/x/all_wendang/my-kb -> -Users-x-all-wendang-my-kb
    # (Note: underscores become '-' too, not just slashes.)
    return re.sub(r'[^a-zA-Z0-9]', '-', cwd)


def parse_session(jsonl_path):
    """Extract lightweight metadata from a session jsonl without loading it all."""
    sid = os.path.basename(jsonl_path).replace(".jsonl", "")
    info = {
        "id": sid,
        "path": jsonl_path,
        "mtime": os.path.getmtime(jsonl_path),
        "lines": 0,
        "first_type": "?",
        "first_user": "(empty)",
        "name": None,        # custom title (user-chosen)
        "ai_name": None,     # AI-generated title
        "agent_name": None,  # agent identifier
        "cwd": None,
        "has_queue": False,
    }
    try:
        with open(jsonl_path, encoding="utf-8") as f:
            first = True
            got_user = False
            for line in f:
                info["lines"] += 1
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                t = o.get("type", "?")
                if first:
                    info["first_type"] = t
                    first = False
                if t == "queue-operation":
                    info["has_queue"] = True
                if t == "custom-title" and o.get("customTitle"):
                    info["name"] = o["customTitle"]
                elif t == "ai-title" and o.get("aiTitle") and not info["ai_name"]:
                    info["ai_name"] = o["aiTitle"]
                elif t == "agent-name" and o.get("agentName") and not info["agent_name"]:
                    info["agent_name"] = o["agentName"]
                if not info["cwd"] and o.get("cwd"):
                    info["cwd"] = o["cwd"]
                if not got_user:
                    msg = o.get("message") or {}
                    if msg.get("role") == "user":
                        c = msg.get("content")
                        txt = ""
                        if isinstance(c, str):
                            txt = c
                        elif isinstance(c, list):
                            for b in c:
                                if isinstance(b, dict) and b.get("type") == "text":
                                    txt = b.get("text", "")
                                    break
                        if txt and not txt.startswith("<") and "tool_result" not in txt and txt.strip():
                            info["first_user"] = txt.strip().replace("\n", " ")
                            got_user = True
    except Exception as e:
        info["first_user"] = f"(read error: {e})"
    return info


def load_active():
    """Read sessions/*.json -> {sessionId: {pid, status, name, kind, cwd}}.

    These files are keyed by PID and track currently-live Claude processes,
    which lets us tell which sessions are "in use" and therefore hidden from
    the resume picker.
    """
    active = {}
    for f in glob.glob(os.path.join(SESSIONS, "*.json")):
        try:
            o = json.load(open(f))
            sid = o.get("sessionId")
            if sid:
                active[sid] = {
                    "pid": o.get("pid"),
                    "status": o.get("status"),
                    "name": o.get("name"),
                    "kind": o.get("kind"),
                    "cwd": o.get("cwd"),
                }
        except Exception:
            pass
    return active


def assess(info, active):
    """Estimate whether the -r picker list would show this session.

    Returns (flag, reason). Black-box inference, not authoritative — the real
    filter logic is inside the Claude Code TUI and isn't documented.
    """
    sid = info["id"]
    if sid in active and active[sid].get("status") == "busy":
        return "⚠️", "in-use"
    ft = info["first_type"]
    if ft == "queue-operation":
        return "⚠️", "queue-op"
    if ft in ("attachment", "system", "mode", "permission-mode"):
        return "⚠️", ft
    if ft == "last-prompt":
        return "✅", ""
    return "?", ft


def main():
    ap = argparse.ArgumentParser(
        description="List/query Claude Code sessions (bypasses -r picker black box)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("-k", "--keyword", help="filter by first-prompt / name keyword")
    ap.add_argument("-d", "--days", type=int, help="only sessions within the last N days")
    ap.add_argument("-n", "--limit", type=int, default=30, help="number to show (default 30)")
    ap.add_argument("-a", "--all-projects", action="store_true", help="scan every project")
    ap.add_argument("-p", "--project", help="specific project path (default: current cwd)")
    ap.add_argument("--id", help="show details + resume command for a session (or use positional)")
    ap.add_argument("query", nargs="?", help="session ID (full or prefix), equivalent to --id")
    args = ap.parse_args()
    if args.query:
        args.id = args.query

    active = load_active()

    # --- detail mode: find one session anywhere and print its resume command ---
    if args.id:
        target = None
        for pd in glob.glob(os.path.join(PROJECTS, "*")):
            for f in glob.glob(os.path.join(pd, "*.jsonl")):
                if os.path.basename(f).startswith(args.id):
                    target = parse_session(f)
                    break
            if target:
                break
        if not target:
            print(f"Session not found: {args.id}")
            sys.exit(1)
        sid = target["id"]
        cwd = target["cwd"] or active.get(sid, {}).get("cwd") or "(unknown)"
        flag, reason = assess(target, active)
        busy = sid in active and active[sid].get("status") == "busy"
        print(f"Session ID    : {sid}")
        print(f"Project cwd   : {cwd}")
        print(f"First-line    : {target['first_type']}")
        print(f"Custom name   : {target['name'] or '(none)'}")
        print(f"AI name       : {target['ai_name'] or '(none)'}")
        print(f"Agent name    : {target['agent_name'] or '(none)'}")
        print(f"List-visible  : {flag} {reason}")
        print(f"In-use        : {'yes (busy - a live process holds it)' if busy else 'no'}")
        print(f"Lines         : {target['lines']}")
        print(f"mtime         : {datetime.fromtimestamp(target['mtime']).strftime('%Y-%m-%d %H:%M')}")
        print(f"First prompt  : {target['first_user'][:120]}")
        print()
        print("Resume command:")
        if cwd and cwd != "(unknown)":
            print(f'  cd "{cwd}" && claude --resume {sid} "continue"')
        else:
            print(f'  claude --resume {sid} "continue"   # run inside the matching project dir')
        print('  ^ A prompt is REQUIRED on 2.1.170, else "No deferred tool marker found"')
        return

    # --- list mode: pick project dir(s) ---
    if args.project:
        projdirs = [os.path.join(PROJECTS, cwd_to_projdir(os.path.expanduser(args.project)))]
    elif args.all_projects:
        projdirs = [d for d in glob.glob(os.path.join(PROJECTS, "*")) if os.path.isdir(d)]
    else:
        projdirs = [os.path.join(PROJECTS, cwd_to_projdir(os.getcwd()))]

    sessions = []
    for pd in projdirs:
        if not os.path.isdir(pd):
            continue
        proj_short = os.path.basename(pd)
        for f in glob.glob(os.path.join(pd, "*.jsonl")):
            info = parse_session(f)
            info["proj"] = proj_short
            sessions.append(info)

    if args.keyword:
        kw = args.keyword.lower()
        sessions = [s for s in sessions
                    if kw in s["first_user"].lower()
                    or kw in (s["name"] or "").lower()
                    or kw in (s["ai_name"] or "").lower()]
    if args.days:
        cutoff = datetime.now().timestamp() - args.days * 86400
        sessions = [s for s in sessions if s["mtime"] >= cutoff]

    sessions.sort(key=lambda s: s["mtime"], reverse=True)
    total = len(sessions)
    sessions = sessions[:args.limit]

    if not sessions:
        print("No matching sessions.")
        return

    multi = args.all_projects or args.project
    print(f"{'M':<3} {'ID(full)':<37} {'Time':<12} {'type':<15} {'Name':<13} {'B':<2} First prompt")
    print("─" * 118)
    for s in sessions:
        flag, _ = assess(s, active)
        ts = datetime.fromtimestamp(s["mtime"]).strftime("%m-%d %H:%M")
        nm = (s["name"] or s["ai_name"] or "")[:11]
        busy = "*" if (s["id"] in active and active[s["id"]].get("status") == "busy") else ""
        proj = f"[{s['proj'].split('-')[-1][:12]}] " if multi else ""
        fu = s["first_user"][:40]
        print(f"{flag:<3} {s['id']:<37} {ts:<12} {s['first_type']:<15} {nm:<13} {busy:<2} {proj}{fu}")
    print("─" * 118)
    print(f"{total} sessions (showing {len(sessions)}) | "
          "✅ likely list-visible  "
          "⚠️ likely hidden (in-use/queue-op/non-interactive)  "
          "? unknown")
    print('Resume: claude --resume <full-ID> "continue"  (a prompt is required)')


if __name__ == "__main__":
    main()
