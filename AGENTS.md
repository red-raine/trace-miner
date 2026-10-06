---
type: agents
title: "trace-miner — family observability spine"
---

# trace-miner AGENTS.md

Mines every coding agent's sessions (Windows + WSL2) into Langfuse v4, scores
good/bad thinking, feeds the distill flywheel. Start with README.md.

## Layout

| Path | Purpose |
|------|---------|
| `adapters/` | one reader per agent store (claude/opencode/zcode/wayward/mecha/codex/freebuff) |
| `canon.py` | task-lifecycle event schema + deterministic ids (trace/span) |
| `ship.py` | OTLP transport to Langfuse :3002 (port of wayward.trace_shipper) |
| `score.py` | good/bad detector bridge (TraceFoundry simCoT/contrastive/judge) |
| `run_miner.py` | CLI: mine / ship / gold / list |
| `wsl.py` | WSL2 read-only bridge |
| `test_smoke.py` | stdlib smoke tests (6, all green) |
| `traces/gold/` | gold distill copies (per-agent JSONL) |

## Rules

- **Never write agent stores.** All adapters open read-only (SQLite uses
  `mode=ro`; JSONL read-only). Gold output goes to `traces/gold/`.
- **Structured fields only** for mining; freebuff/ads carry the EXP-029
  caveat — never assume ad-free text.
- **Register-before-use**: `run_miner.py --list`; adding an adapter requires
  a smoke test in `test_smoke.py`.
- Langfuse url/pk/sk come from `~/.langfuse-otlp.env` (never inline keys).
- Honest failure: mine errors print to stderr, never swallowed.

## Family hooks

- NanoResearch: `mcp_server` gains `tf_*` miner tools.
- wayward: `trace_shipper.py` is the upstream transport; mirror changes here.
- TraceFoundry: `mcp-server.mjs` langfuseHost = `:3002` (not :3000).
- Mecha-Sharness: `ml.tracer` → workspace `trace.jsonl` adapter (built).

## Next (Tier 1)

- thinking-cap distiller on nyx consumes `traces/gold/*.jsonl`.
- Docker container (WSL2-built) wrapping adapters + shipper.
- codex + freebuff adapters after those CLIs are installed/registered.
- Branch merge: freebuff / pseudag / wayward three-way flywheel integration.