"""OpenAI Agents API backend: no CLI, no npm/node: just `pip install patchbot[openai]`.

Same shape as the `api` (Anthropic) backend: a session with `environment:
none` and two application-side function tools (bash + write_file, scoped to
cwd), so the fix lands in the local checkout that fix.py then verifies.
`OPENAI_API_KEY` is the only secret involved.

Docs: https://developers.openai.com/api/docs/guides/agents-api/quickstart
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Optional

DEFAULT_MODEL = "gpt-6-astra"

TOOLS = [
    {
        "type": "function",
        "name": "bash",
        "description": "Run a shell command in the repository and return its output.",
        "parameters": {
            "type": "object",
            "properties": {"command": {"type": "string", "description": "The shell command to run."}},
            "required": ["command"],
        },
    },
    {
        "type": "function",
        "name": "write_file",
        "description": "Write content to a file in the repository.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path relative to the repository root."},
                "content": {"type": "string", "description": "The full file content to write."},
            },
            "required": ["path", "content"],
        },
    },
]

FAILED_EVENTS = {"agent.session.turn.failed", "agent.session.turn.cancelled", "agent.session.failed"}


def _handlers(cwd: str) -> dict:
    root = Path(cwd).resolve()

    def bash(args: dict) -> str:
        result = subprocess.run(
            args["command"], shell=True, cwd=root, capture_output=True, text=True, timeout=120,
        )
        return f"exit={result.returncode}\n{result.stdout}\n{result.stderr}"[:8000]

    def write_file(args: dict) -> str:
        target = (root / args["path"]).resolve()
        if root not in target.parents and target != root:
            return "error: path escapes the repository root"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(args["content"], encoding="utf-8")
        return "ok"

    return {"bash": bash, "write_file": write_file}


def run(prompt: str, cwd: str, model: Optional[str] = None, timeout: int = 600,
        config: Optional[dict] = None) -> int:
    try:
        import openai
    except ImportError as exc:
        raise RuntimeError(
            "the 'openai' agent needs the openai package: pip install patchbot[openai]"
        ) from exc

    client = openai.OpenAI()
    session = client.beta.agents.sessions.create(
        environment={"type": "none"},
        agent={
            "model": model or DEFAULT_MODEL,
            "instructions": "Fix the reported vulnerability with the smallest change that works. "
                            "Use the bash and write_file tools; never edit outside the repository.",
            "tools": TOOLS,
        },
    )

    failed = False
    with client.beta.agents.sessions.stream(
        session.id, input=prompt, tool_handlers=_handlers(cwd), timeout=timeout,
    ) as stream:
        for event in stream:
            if event.type in FAILED_EVENTS:
                failed = True

    # As with `managed`, the session's own verdict is not the fix gate:
    # fix.py re-scans and runs test_cmd host-side after this returns.
    return 1 if failed else 0
