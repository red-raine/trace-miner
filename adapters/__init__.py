"""Adapter registry for trace-miner."""

ADAPTERS = {
    "claude": ("claude", "iter_sessions"),
    "opencode": ("opencode", "iter_sessions"),
    "zcode": ("zcode", "iter_sessions"),
    "wayward": ("wayward", "iter_sessions"),
    "mecha": ("mecha", "iter_sessions"),
    "pseudag": ("pseudag", "iter_sessions"),
    "tracefoundry": ("tracefoundry", "iter_sessions"),
}