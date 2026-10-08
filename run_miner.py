"""run_miner — CLI: mine agent sessions -> Langfuse (OTLP) + gold filter.

Usage:
    python run_miner.py --agent claude            # mine + ship one agent
    python run_miner.py --all                     # all local agents
    python run_miner.py --agent wayward --ship    # include Langfuse ship
    python run_miner.py --gold --min-score 0.7    # distill gold output
    python run_miner.py --list                    # list available adapters

Langfuse env auto-reads from ~/.langfuse-otlp.env (OTLP URL :3002).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from canon import Session
from score import gold_filter

ADAPTER_REGISTRY: dict[str, tuple[str, str]] = {
    "claude": ("adapters.claude", "iter_sessions"),
    "opencode": ("adapters.opencode", "iter_sessions"),
    "zcode": ("adapters.zcode", "iter_sessions"),
    "wayward": ("adapters.wayward", "iter_sessions"),
    "mecha": ("adapters.mecha", "iter_sessions"),
    "pseudag": ("adapters.pseudag", "iter_sessions"),
    "tracefoundry": ("adapters.tracefoundry", "iter_sessions"),
}


def _load_adapter(agent: str):
    import importlib

    mod_name, fn_name = ADAPTER_REGISTRY[agent]
    mod = importlib.import_module(mod_name)
    return getattr(mod, fn_name)


def mine(agent: str, **kwargs) -> list[Session]:
    fn = _load_adapter(agent)
    return list(fn(**kwargs))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="run_miner", description="trace-miner")
    ap.add_argument("--agent", choices=sorted(ADAPTER_REGISTRY), help="adapter to run")
    ap.add_argument("--all", action="store_true", help="all local adapters")
    ap.add_argument("--list", action="store_true", help="list adapters")
    ap.add_argument("--ship", action="store_true", help="ship to Langfuse")
    ap.add_argument("--gold", action="store_true", help="emit gold (distill-friendly) JSONL")
    ap.add_argument("--no-resolve", action="store_true", help="skip alias->upstream model resolution")
    ap.add_argument("--min-score", type=float, default=0.7)
    ap.add_argument("--out", type=str, default="", help="output dir (default traces/)")
    args = ap.parse_args(argv)

    if args.list:
        for name, (mod, fn) in ADAPTER_REGISTRY.items():
            print(f"{name:10} {mod}.{fn}")
        return 0

    agents = [args.agent] if args.agent else list(ADAPTER_REGISTRY) if args.all else []
    if not agents:
        ap.error("pick --agent or --all")

    total = 0
    for agent in agents:
        try:
            sessions = mine(agent)
        except Exception as exc:  # honest failure reporting, never silent
            print(f"[{agent}] MINE ERROR: {exc}", file=sys.stderr)
            continue
        print(f"[{agent}] mined {len(sessions)} sessions / "
              f"{sum(len(s.spans) for s in sessions)} spans")
        total += len(sessions)

        # A-W3: resolve routing aliases → actual upstream model (best-effort)
        if not args.no_resolve:
            try:
                from resolve import resolve_session_model

                resolved_n = 0
                for sess in sessions:
                    sess.model, sess.metadata["resolved"] = resolve_session_model(sess)
                    if sess.metadata.get("resolved"):
                        resolved_n += 1
                if resolved_n:
                    print(f"[{agent}] resolved {resolved_n} aliases -> upstream models")
            except Exception as exc:
                print(f"[{agent}] resolve skipped: {exc}", file=sys.stderr)

        if args.gold:
            gold, stats = gold_filter(sessions, args.min_score)
            print(f"[{agent}] gold: {len(gold)} sessions, {stats}")
            if sessions and not args.ship:
                _write_gold(agent, gold, args.out)

        if args.ship:
            _ship(agent, sessions)

    print(f"done. total sessions: {total}")
    return 0


def _write_gold(agent: str, gold: list[Session], out_dir: str) -> None:
    out = Path(out_dir or ("traces" / Path("gold"))).resolve()
    if out_dir == "":
        out = Path(__file__).parent / "traces" / "gold"
    out.mkdir(parents=True, exist_ok=True)
    with (out / f"{agent}-gold.jsonl").open("w", encoding="utf-8") as fh:
        for sess in gold:
            fh.write(json.dumps({"agent": sess.agent, "session_id": sess.session_id,
                                 "spans": [sp.__dict__ for sp in sess.spans]}) + "\n")
    print(f"[{agent}] gold written -> {out / (agent + '-gold.jsonl')}")


def _ship(agent: str, sessions: list[Session]) -> None:
    from ship import load_env, ship_session

    url, pk, sk = load_env()
    shipped = 0
    for sess in sessions:
        try:
            shipped += ship_session(sess, url, (pk, sk))
        except OSError as exc:
            print(f"[{agent}] SHIP ERROR {sess.session_id}: {exc}", file=sys.stderr)
    print(f"[{agent}] shipped {shipped} spans to Langfuse")


if __name__ == "__main__":
    raise SystemExit(main())