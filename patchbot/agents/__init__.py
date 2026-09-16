from __future__ import annotations

from patchbot.registry import load_plugins
from patchbot.agents import claude, codex, api, command, managed, openai

BUILTIN = {"claude": claude, "codex": codex, "api": api, "command": command,
           "managed": managed, "openai": openai}


def get(name: str):
    plugins = load_plugins("patchbot.agents", BUILTIN)
    module = plugins.get(name)
    if module is None:
        raise ValueError(f"unknown agent: {name!r} (available: {sorted(plugins)})")
    return module
