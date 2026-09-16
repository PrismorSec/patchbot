from __future__ import annotations

import argparse
import sys
from pathlib import Path

from patchbot import inventory, feeds, scanners, report, fix
from patchbot.config import Config
from patchbot.registry import load_plugins


def _collect_findings(cfg: Config, cwd: str):
    packages = inventory.collect(cfg.paths, cfg.sbom)
    findings = feeds.match_all(packages, cfg.feeds)
    findings.extend(scanners.run_all(cwd, cfg.scanners))
    from patchbot.models import dedupe
    findings = dedupe(findings)
    return [f for f in findings if f.id not in cfg.ignore]


def cmd_scan(args) -> int:
    cfg = Config.load(args.config)
    if args.paths:
        cfg.paths = args.paths
    fail_on = args.fail_on or cfg.fail_on

    findings = _collect_findings(cfg, args.paths[0] if args.paths else ".")

    writer = report.FORMATS[args.format]
    output = writer(findings)
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
    else:
        print(output)

    return report.exit_code(findings, fail_on)


def cmd_fix(args) -> int:
    cfg = Config.load(args.config)
    if args.paths:
        cfg.paths = args.paths
    cwd = args.paths[0] if args.paths else "."

    findings = _collect_findings(cfg, cwd)
    if not findings:
        print("No vulnerabilities found; nothing to fix.")
        return 0

    agent_config = dict(cfg.agent_config)
    if args.cmd:
        agent_config["cmd"] = args.cmd

    results = fix.run(
        findings, cwd,
        agent_name=args.agent or cfg.agent,
        max_prs=args.max if args.max is not None else cfg.max_prs,
        open_pr=args.pr,
        test_cmd=args.test_cmd or cfg.test_cmd,
        dry_run=args.dry_run,
        model=args.model or cfg.model,
        agent_config=agent_config,
    )
    for r in results:
        print(f"[{r['status']}] {r['package']}: {r['detail']}")
    return 0 if all(r["status"] != "failed" for r in results) else 1


def cmd_plugins(args) -> int:
    from patchbot.feeds import BUILTIN as feed_builtins
    from patchbot.scanners import BUILTIN as scanner_builtins
    from patchbot.agents import BUILTIN as agent_builtins
    print("feeds:   ", sorted(load_plugins("patchbot.feeds", feed_builtins)))
    print("scanners:", sorted(load_plugins("patchbot.scanners", scanner_builtins)))
    print("agents:  ", sorted(load_plugins("patchbot.agents", agent_builtins)))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="patchbot")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="scan for vulnerable packages")
    scan.add_argument("paths", nargs="*", default=["."])
    scan.add_argument("--config", help="path to patchbot.toml")
    scan.add_argument("--format", choices=sorted(report.FORMATS), default="table")
    scan.add_argument("-o", "--output", help="write report to a file instead of stdout")
    scan.add_argument("--fail-on", choices=["critical", "high", "medium", "low", "none"])
    scan.set_defaults(func=cmd_scan)

    fix_p = sub.add_parser("fix", help="open fix PRs for vulnerable packages via a coding agent")
    fix_p.add_argument("paths", nargs="*", default=["."])
    fix_p.add_argument("--config", help="path to patchbot.toml")
    fix_p.add_argument("--agent", help="claude | codex | api | openai | command | managed | none, or a registered plugin")
    fix_p.add_argument("--model", help="model ID to pass to the agent (claude/codex/api/openai/managed)")
    fix_p.add_argument("--cmd", help="shell command template for --agent command, e.g. 'aider --message {prompt}'")
    fix_p.add_argument("--max", type=int, help="max packages to fix in this run")
    fix_p.add_argument("--pr", action="store_true", help="push the branch and open a PR (needs gh)")
    fix_p.add_argument("--test-cmd", help="command to verify a fix before committing")
    fix_p.add_argument("--dry-run", action="store_true", help="print the agent prompt, make no changes")
    fix_p.set_defaults(func=cmd_fix)

    plugins = sub.add_parser("plugins", help="list registered feeds, scanners, and agents")
    plugins.set_defaults(func=cmd_plugins)

    from patchbot import managed_setup
    managed_setup.add_subparser(sub)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
