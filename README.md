# selected-model-is-at-capacity-tmuxer

**Auto-continue the [Codex CLI](https://github.com/openai/codex) when it stops with
`Selected model is at capacity. Please try a different model.`**

If you run Codex agents inside **tmux** and keep hitting

> ⚠ Selected model is at capacity. Please try a different model.

…the agent just sits there, idle, until you notice and nudge it. This is a tiny
`bash` + `tmux` watchdog that notices for you: it watches a whitelist of tmux
sessions, detects the "Selected model is at capacity" stall, and resubmits
`continue` so the agent keeps going — same model, no babysitting.

No dependencies beyond `bash`, `tmux`, and `grep`/`sed`. It never touches Codex
itself; it only reads panes with `tmux capture-pane` and types with
`tmux send-keys`.

## Why tmux

Codex renders its TUI **inline** (not on the alternate screen), so its transcript
lives in your normal tmux scrollback. That means tmux can read the exact frame
Codex is showing and type into its composer — no API, no plugin. Run your Codex
agents in tmux panes and point this tool at their sessions.

## Requirements

- `tmux`
- `bash`
- Codex CLI running **inside** tmux panes

## Install

```sh
git clone https://github.com/dearlordylord/selected-model-is-at-capacity-tmuxer.git
cd selected-model-is-at-capacity-tmuxer
chmod +x bin/capacity-tmuxer
# optional: put it on PATH
ln -s "$PWD/bin/capacity-tmuxer" ~/.local/bin/capacity-tmuxer
```

## Usage

Whitelist the tmux sessions running Codex (session names are the arguments):

```sh
capacity-tmuxer 43 44 my-agent
```

Or via env, and run it detached so it keeps watching:

```sh
WATCH_SESSIONS="43 44" nohup capacity-tmuxer > ~/capacity-tmuxer.log 2>&1 &
tail -f ~/capacity-tmuxer.log
```

`--help` prints the full option list.

### Live status pane (optional)

Codex renders inline, so its own status bar isn't pinned. `--status-pane` gives
you a synthesized one: a live, refreshing readout of every watched pane's state
(`WORKING` / `IDLE` / `CAPACITY`). Run it in a small split you keep at the bottom:

```sh
# split off a short pane and run the readout in it
tmux split-window -v -l 8 'capacity-tmuxer --status-pane 43 44'
```

```
capacity-tmuxer  13:01:06   sessions: 43 44 40   (refresh 2s)

PANE                STATE      DETAIL
------              -----      ------
43:0.0              CAPACITY   at capacity — waiting to resubmit
44:0.0              WORKING    • Working (25s • esc to interrupt)
40:0.0              IDLE
```

This mode is read-only — it never sends keys. Run it alongside the watcher (they
are independent processes).

## How it decides to send (only when it's *fresh*)

The capacity string has no "freshness" token, so the tool never fires on the mere
presence of the text. It sends only when three scroll-independent facts agree —
so an old message you scrolled past, or one that's already being retried, is
ignored:

1. **Position** — only the bottom slice of the pane's live frame counts
   (`capture-pane` reads the live grid even while you're scrolled up in
   copy-mode — verified), so a message above the fold doesn't match.
2. **Idle** — Codex's busy indicator (`esc to interrupt`) must be **absent**,
   proving it actually stopped rather than still working.
3. **Edge, not level** — it fires once on entering the stalled state, then
   re-arms only after Codex is seen working again. Per-pane exponential backoff
   bounds retries if `continue` bounces straight back into capacity.

## Safety

- **Composer guard (on by default)** — sends only when the input box is the empty
  dim placeholder. If you have a half-typed prompt sitting in the composer, the
  tool detects it and skips, so your text is never clobbered. Fail-safe: if it
  can't confirm the box is empty, it skips.
- **Read-only detection** — the only writes are `send-keys "continue"` + `Enter`,
  and only into a pane that passed every check above.
- **Backoff** — a pane that keeps returning to capacity is retried on a
  `30s → ×2 → 900s` schedule, not hammered.

## Configuration

All tunables are environment variables:

| Var | Default | Meaning |
|---|---|---|
| `POLL` | `15` | seconds between scans (watch mode) |
| `STATUS_POLL` | `2` | seconds between refreshes (`--status-pane` mode) |
| `WINDOW` | `20` | bottom lines that count as "current/last" |
| `CAP_RE` | `Selected model is at capacity` | capacity message to match (`grep -i`) |
| `BUSY_RE` | `esc to interrupt` | present == Codex is working |
| `BACKOFF_START` | `30` | first wait after a send (s) |
| `BACKOFF_MAX` | `900` | backoff ceiling (s) |
| `SEND_TEXT` | `continue` | text submitted to resume the agent |
| `GUARD_COMPOSER` | `1` | require an empty composer before sending |
| `WATCH_SESSIONS` | — | fallback whitelist if no args are given |

## Caveats

- **Same model.** It resubmits to the *same* model (the one that was at
  capacity), matching the "just retry" workflow. If capacity persists, backoff
  spaces the retries out. Switching models is out of scope.
- **Codex wording.** `CAP_RE` matches the observed string
  `Selected model is at capacity`. If a future Codex build reworks that message,
  update `CAP_RE`.
- **Composer prompt glyph.** The composer guard keys off Codex's `›` prompt and
  its dim-placeholder styling. If that rendering changes, set `GUARD_COMPOSER=0`
  (you lose the half-typed-prompt protection) or adjust the script.

## License

[MIT](LICENSE)
