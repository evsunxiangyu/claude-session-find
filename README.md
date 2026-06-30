# claude-session-find

A [Claude Code](https://claude.com/claude-code) skill that finds and locates past sessions — bypassing the `claude --resume` picker list, which is a black box that hides some sessions.

## Why

On Claude Code 2.1.170+, the `claude -r` (resume) picker list filters out:

- **Sessions held by a live process** (`status=busy`) — to prevent double-opening
- **Programmatic calls** (first-line type `queue-operation`, from `-p` / hooks / loops / subagents)
- **Other non-interactive entries** (`attachment` / `system` / `mode`)

Those sessions are invisible in the picker but still recoverable by ID. This skill scans the on-disk jsonl files directly, giving a complete view the picker can't.

It also documents two other `-r` gotchas:

- `claude --resume <id>` **requires a prompt** on 2.1.170 (`No deferred tool marker found` otherwise)
- The picker is scoped to the **current cwd** only

## Install

Clone into your Claude skills directory:

```bash
git clone git@github.com:evsunxiangyu/claude-session-find.git ~/.claude/skills/session-find
```

Then either invoke it through the model ("find the session where I talked about X") or run the bundled tool directly:

```bash
python3 ~/.claude/skills/session-find/scripts/cc_sessions.py -k <keyword> -d <days>
```

Optional alias for your `~/.zshrc`:

```bash
alias ccl='python3 ~/.claude/skills/session-find/scripts/cc_sessions.py'
```

## Usage

```
cc_sessions                       # current project, recent 30
cc_sessions -k yiweiy             # filter by first-prompt / name keyword
cc_sessions -d 7                  # last 7 days
cc_sessions -n 50                 # show 50
cc_sessions -a                    # all projects
cc_sessions <ID>                  # details + exact resume command (full or prefix)
```

Sample output:

```
M   ID(full)                              Time        type            Name          B  First prompt
✅  4987b3c4-8551-4668-95b7-58ad23bcecf7  06-30 12:00 last-prompt     卡片阅读 05       Run this task as a loop...
⚠️  c958ce00-...                          06-30 12:10 last-prompt     ...            *  ...
```

- `✅` likely visible in the `-r` picker
- `⚠️` likely hidden (in-use / queue-op / non-interactive)
- `*` in the `B` column = a live process holds this session

## How it works

Claude Code stores sessions as:

- `~/.claude/projects/<encoded-cwd>/<sessionId>.jsonl` — full session content
- `~/.claude/sessions/<pid>.json` — live process registry (keyed by PID, tells us what's in-use)

The cwd→dir encoding rule: `re.sub(r'[^a-zA-Z0-9]', '-', cwd)` — every non-alphanumeric character (including `_`) becomes `-`. So `/Users/x/all_wendang/my-kb` becomes `-Users-x-all-wendang-my-kb`.

## Requirements

- Python 3.7+ (stdlib only — no dependencies)
- Claude Code 2.1.x (other versions not tested)

## License

MIT
