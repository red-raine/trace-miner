"""trace-miner — cross-agent session tracing into Langfuse (2026).

Mines session history from every coding agent (Windows + WSL2) into a
self-hosted Langfuse v4 instance, then scores good/bad thinking for the
distill flywheel (thinking-cap distiller on nyx, SFT/SDFT/SPIN lanes).

See README.md for architecture. Sources: bandr-ai/bandits,
davanstrien/agent-traces, Skill-DisCo (arxiv 2606.26669).
"""

__version__ = "0.1.0"