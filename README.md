# trace-miner

Cross-agent session tracing into a self-hosted Langfuse v4, plus a good/bad
thinking scorer for the distill flywheel (thinking-cap distiller on nyx;
SFT/SDFT/SPIN lanes). Mines session history from every coding agent on this
machine (Windows + WSL2) — the family's observability spine.

## Architecture

```
ALL CODING AGENTS (Windows + WSL2)          THE SPINE          CONSUMERS
claude  opencode  zcode  freebuff  codex ─► trace-miner ─► Langfuse v4 (:3002)
wayward mecha pseudag jitral                  adapters     ClickHouse spans/
NanoResearch TraceFoundry                     canon→OTLP   sessions/tasks
        │                                             ▲
        └── good/bad detector (TraceFoundry           │
            simCoT + contrastive-cot + judgeAnswer) ──┘ gold/weak
                                   │ gold
                                   ▼
        thinking-cap distiller (nyx GPU) → SFT/SDFT/SPIN → back to family
```

## Quick start

```bash
python run_miner.py --list                # adapters
python run_miner.py --agent wayward       # mine wayward trace log
python run_miner.py --all                 # all local agents
python run_miner.py --agent claude --ship # mine + ship to Langfuse
python run_miner.py --gold --min-score 0.7  # distill gold copies
python test_smoke.py                      # smoke tests (stdlib only)
```

Langfuse env auto-reads `~/.langfuse-otlp.env` (LANGFUSE_OTLP_URL /
LANGFUSE_PK / LANGFUSE_SK). The OTLP transport is the proven
wayward.trace_shipper (EXP-026 verified: 78,509 events in 24s, idempotent
byte-offset resume, Langfuse dedupes by trace_id+span_id).

## Gitea on lyre — remotes + setup

Canonical backup remote (models NEVER go to GitHub): `http://192.168.8.217:3005/zcode/trace-miner`
(web UI: `http://lyre:3005/zcode/trace-miner`). ⚠️ The old `gitea` remote
(`opencode/trace-miner`) and GitHub `origin` (`red-raine/trace-miner`) point at repos
that do not exist — kept only as historical references; do not push to them.

Create a new repository on gitea, then from the empty repo's quick-start (this repo's path):

```bash
git remote add origin http://192.168.8.217:3005/zcode/trace-miner.git
git push -u origin master        # our default branch is master (repo template says main)
git push -u origin trace-miner-upgrade-wave1   # upgrade lane branch (plan-23)
```

Auth note: push auth needs the token in the URL or a credential helper
(`GIT_ASKPASS` alone is declined by this server). Token lives in
`build models/scripts/.env` as `GITEA_TOKEN` — never commit it.

## Adapters (2026-verified sources)

| Agent | Store | Adapter |
|-------|-------|---------|
| claude | `~/.claude/projects/*/*.jsonl` (HF-native) | adapters/claude.py |
| opencode | `~/.local/share/opencode/opencode.db` (SQLite, 3.5 GB) | adapters/opencode.py |
| zcode | `~/.zcode/v2/*.json` | adapters/zcode.py |
| wayward | `logs/wayward-trace.log` (always-on JSONL) | adapters/wayward.py |
| mecha | workspace `trace.jsonl` (ml.tracer) | adapters/mecha.py |
| codex | `~/.codex/sessions/*.jsonl` (stub — install) | adapters/codex.py |
| freebuff | local session JSONL (ad-caveat, EXP-029) | adapters/freebuff.py |

WSL2 agents (Linux-side stores) run read-only via `wsl.py`.

## 2026 research backing

- **TRACE** — Trajectory-Aware Comprehensive Evaluation (arXiv 2602.21230):
  trajectory-level metrics, RL (DAPO/GHPO) post-training.
- **bandr-ai/bandits** — trace mining for post-training; judge-turns by
  reaction, propose-verifier, filter→export SFT/RL.
- **davanstrien/agent-traces** — Claude/Codex/Pi → Polars/Parquet, 3-table
  layout (sessions/events/content).
- **Skill-DisCo** (arXiv 2606.26669) — distill PFSM procedural skills from
  successful traces.
- **SemiAnalysis cc-traces** — real Claude Code traces for KV-cache/replay.
- LiteLLM OTEL v2 (`LITELLM_OTEL_V2=true`) — native GenAI semantic-convention
  spans with Langfuse preset.

## Chain of custody / honest failure

- Structured fields are the mining contract; freebuff/ads caveat per wayward
  EXP-029 — ads are not reliably separable from agent chatter, so mining
  uses structured fields (exit codes, gates, timings, verdicts) only.
- Source of truth stays with each agent's raw logs; Langfuse is the view.
- Every span carries agent/session/task attrs for deterministic dedupe.