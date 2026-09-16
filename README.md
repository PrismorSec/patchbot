<div align="center">

# patchbot

**Vulnerability scanning with your scanners, your threat feeds, and a coding agent that opens the fix PR.**

[![PyPI](https://img.shields.io/pypi/v/patchbot?color=blue)](https://pypi.org/project/patchbot/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://pypi.org/project/patchbot/)
[![CI](https://github.com/PrismorSec/patchbot/actions/workflows/ci.yml/badge.svg)](https://github.com/PrismorSec/patchbot/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![GitHub Action](https://img.shields.io/badge/GitHub-Action-2088FF?logo=githubactions&logoColor=white)](#github-actions)

<img src="docs/img/patchbot-demo.gif" alt="patchbot finds 5 advisories, fixes them, and re-scans clean" width="800">

</div>

---

patchbot inventories the packages in your repository, matches them against any threat feed, accepts findings from any scanner, and fixes what it finds. When a version bump is enough, it bumps. When the bump breaks the build, it hands the failure to a coding agent. It re-scans before opening each pull request.

Run it as a CLI, as a GitHub Action, or as a scheduled [Claude Managed Agents](https://platform.claude.com/docs/en/managed-agents/overview) deployment with no CI involved.

## Why patchbot

| | Dependabot / Renovate | Trivy / Grype alone | **patchbot** |
|---|---|---|---|
| Bring your own threat feed (private advisories, OSV format) | no | no | yes |
| Bring your own scanner (any tool that emits SARIF / Trivy / Grype JSON) | no | n/a | yes |
| Version bump + lockfile regeneration with no model call | yes | no | yes |
| Fixes that need **code changes** (breaking major bump, failing tests) | no | no | yes, agent tier |
| Re-scan before every PR | no | no | yes |
| Agent runs **off** the CI runner; secrets stay out of the sandbox | no | no | yes, Managed Agents |
| Works without CI (scheduled, any git host) | no | no | yes |

## Installation

```bash
pip install patchbot            # scan + bump-only fixes
pip install "patchbot[api]"     # + Anthropic-backed agent tiers (api, managed)
pip install "patchbot[openai]"  # + OpenAI Agents API tier (openai)
```

Requires Python 3.11 or newer. No other runtime dependencies.

## Quick start

```bash
patchbot scan                    # inventory -> OSV.dev -> table report
patchbot fix --dry-run           # preview the fix plan, change nothing
patchbot fix --pr                # bump or fix, verify, open one PR per package
```

<img src="docs/img/fix-dry-run.png" alt="patchbot fix --dry-run" width="800">

## How it works

```mermaid
flowchart LR
    inv["Inventory<br/>lockfiles · CycloneDX SBOM"]
    feeds["Feeds<br/>OSV.dev · your OSV file / URL"]
    scanners["Scanners<br/>trivy · grype · osv-scanner · any cmd"]
    findings["Findings<br/>(deduplicated)"]
    report["Report<br/>table · json · SARIF"]
    fix["Fix<br/>bump → verify → agent → verify → PR"]

    inv --> feeds --> findings
    inv --> scanners --> findings
    findings --> report
    findings --> fix
```

**Inventory.** Parsers for npm, pnpm, and yarn lockfiles, `requirements*.txt`, `pyproject.toml`, `go.mod`, and `Cargo.toml`. For other ecosystems, point patchbot at a CycloneDX SBOM from `syft`, `cdxgen`, or your own tooling.

**Feeds.** OSV.dev is on by default. To add a private feed, serve OSV-schema JSON from a file or URL. You keep one format.

**Scanners.** Wrappers for `trivy`, `grype`, and `osv-scanner`. The `command` scanner runs any tool that writes SARIF, Trivy, Grype, or osv-scanner JSON to stdout.

**Fix.** One branch per vulnerable package, in four steps:

1. **Bump.** patchbot rewrites the pin to the lowest version that clears every advisory and regenerates the lockfile with the ecosystem's own tool. No model call.
2. **Verify.** patchbot re-scans, runs `test_cmd`, and rejects any diff that reaches outside the dependency surface (CI config, dotfiles).
3. **Escalate.** If step 2 fails, patchbot briefs the agent with the failure itself: "bumped `lodash` to 4.18.0; tests fail with ...". The agent fixes the code.
4. **Verify again.** Then commit, push, and open the PR with the advisory table in the body.

`--agent none` skips step 3 and gives you bump-only mode.

## Commands

| Command | What it does |
|---|---|
| `patchbot scan [paths...]` | Run the pipeline and print a report. Exits 1 when any finding meets `--fail-on` (default `high`). |
| `patchbot fix [paths...]` | Run the fix loop. `--dry-run` previews; `--pr` pushes and opens pull requests through `gh`. |
| `patchbot plugins` | List each registered feed, scanner, and agent, built in and third party. |
| `patchbot managed ...` | Set up (`init`) and schedule (`deploy`, `list`, `pause`, `unpause`) the Managed Agents backend. |

<details>
<summary><code>patchbot scan</code></summary>
<br>
<img src="docs/img/scan.png" alt="patchbot scan" width="800">
</details>

<details>
<summary><code>patchbot scan --format json</code></summary>
<br>
<img src="docs/img/scan-json.png" alt="patchbot scan --format json" width="800">
</details>

<details>
<summary><code>patchbot plugins</code></summary>
<br>
<img src="docs/img/plugins.png" alt="patchbot plugins" width="800">
</details>

## Configuration

Put `patchbot.toml` in the repository root. CLI flags override the file.

```toml
[inventory]
paths = ["."]
# sbom = "sbom.cdx.json"

[feeds.osv]
enabled = true

[feeds.internal]                # your own threat feed
type = "url"                    # or "file" with path = "..."
url  = "https://intel.example.com/advisories.json"

[scanners.trivy]
enabled = true

[scanners.custom]               # your own scanner
type   = "command"
cmd    = "./scan.sh"
format = "sarif"                # sarif | trivy | grype | osv-scanner

[report]
fail_on = "high"                # critical | high | medium | low | none
ignore  = ["GHSA-xxxx-xxxx-xxxx"]

[fix]
agent    = "claude"             # claude | codex | api | openai | command | managed | none
model    = "claude-opus-5"      # optional; forwarded to the agent
max_prs  = 5
test_cmd = "npm test"
# cmd = "aider --yes --message {prompt}"     # agent = "command" only

[fix.managed]                   # agent = "managed" only; printed by `patchbot managed init`
agent_id       = "agent_..."
environment_id = "env_..."
vault_id       = "vlt_..."
```

## Choosing an agent backend

| Backend | Runs where | Needs | Use it for |
|---|---|---|---|
| `claude` / `codex` | Your machine or runner, through the CLI on `PATH` | The CLI, logged in | Local development |
| `api` | Your runner, in process | `pip install patchbot[api]`, `ANTHROPIC_API_KEY` | CI without Node |
| `openai` | Your runner, in process | `pip install patchbot[openai]`, `OPENAI_API_KEY` | CI without Node, on OpenAI models |
| `command` | Wherever your tool runs | Any agent that accepts a prompt (`aider`, `opencode`, ...) | Non-Anthropic models |
| `managed` | **Anthropic's sandbox**, off your runner | `patchbot managed init` once, three IDs as secrets | CI where the agent must not see repo secrets |

### Managed Agents, the recommended CI backend

An agent with a shell on your CI runner sits next to your repository secrets. The `managed` backend moves the agent into a [Claude Managed Agents](https://platform.claude.com/docs/en/managed-agents/overview) sandbox. Anthropic's git proxy authenticates `git push`; a vaulted GitHub MCP credential creates the pull request. Your GitHub token stays outside the sandbox. patchbot then re-scans the pushed branch on your side before it treats the fix as done.

```bash
pip install "patchbot[api]"
patchbot managed init --github-mcp-token "$GITHUB_MCP_TOKEN"
# prints agent_id, environment_id, vault_id; store them as repo secrets
patchbot fix --agent managed --pr
```

## GitHub Actions

**Scan and publish to the Security tab**

```yaml
permissions:
  security-events: write
steps:
  - uses: actions/checkout@v4
  - uses: PrismorSec/patchbot@v0
    with:
      fail-on: high
```

<img src="docs/img/code-scanning.jpg" alt="Code scanning alerts detected by patchbot" width="800">

**Auto-fix with Managed Agents** (no Node, no agent on the runner)

```yaml
permissions:
  contents: write
  pull-requests: write
steps:
  - uses: actions/checkout@v4
  - uses: PrismorSec/patchbot@v0
    with:
      fix: "true"
      agent: managed
      managed-agent-id: ${{ secrets.PATCHBOT_AGENT_ID }}
      managed-environment-id: ${{ secrets.PATCHBOT_ENVIRONMENT_ID }}
      managed-vault-id: ${{ secrets.PATCHBOT_VAULT_ID }}
    env:
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**Auto-fix with the in-runner `api` backend**

```yaml
permissions:
  contents: write
  pull-requests: write
  security-events: write
steps:
  - uses: actions/checkout@v4
  - uses: PrismorSec/patchbot@v0
    with:
      fix: "true"
      agent: api
    env:
      ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
```

**Weekly, against a private feed**

```yaml
on:
  schedule:
    - cron: "0 6 * * 1"
steps:
  - uses: actions/checkout@v4
  - uses: PrismorSec/patchbot@v0
    with:
      config: patchbot.toml    # [feeds.internal] url = ...
```

[`action.yml`](./action.yml) documents each input. [`.github/workflows/patchbot-fix-example.yml`](.github/workflows/patchbot-fix-example.yml) is a complete workflow you can copy.

A pull request opened by `patchbot fix --pr`:

<img src="docs/img/fix-pr.jpg" alt="A pull request opened by patchbot" width="800">

## Scheduled deployments (no CI)

`patchbot managed deploy` creates a cron-scheduled Managed Agents session that clones your repositories, scans, fixes, and opens pull requests. Nothing in it depends on GitHub Actions, so it works with GitLab and Bitbucket too.

```bash
patchbot managed deploy \
  --repos owner/api,owner/web \
  --cron "0 6 * * *" --tz UTC \
  --agent-id agent_... --environment-id env_... --vault-id vlt_... \
  --run-now                       # fire one session now to test
```

Manage it with `patchbot managed list | pause | unpause`. Anthropic jitters scheduled runs by up to nine minutes, and 1 to 3 AM local wall-clock times can skip or double-fire across DST changes. Schedule outside that window, or use UTC.

## Extending patchbot

Register a scanner, feed, or agent from your own package through entry points. No fork needed.

```toml
# your_package/pyproject.toml
[project.entry-points."patchbot.scanners"]
mytool = "your_package.scanner:run"      # run(cwd: str, config: dict) -> list[Finding]

[project.entry-points."patchbot.feeds"]
myfeed = "your_package.feed"             # match(packages, config) -> list[Finding]

[project.entry-points."patchbot.agents"]
myagent = "your_package.agent"           # run(prompt, cwd, model=None, timeout=600, config=None) -> int
```

If you would rather not write Python, `[scanners.*] type = "command"` and `[feeds.*] type = "url" | "file"` cover most cases. `cmd` values run through your shell, so point them at tools you trust.

## FAQ

**Why did a fix report `failed`?** patchbot prints the reason: the advisory still reproduces after the bump or the agent run, `test_cmd` failed (with the log tail), or the change touched files outside the dependency surface. patchbot discards the branch and commits nothing.

**What sets the exit code?** `scan` exits 1 when any finding meets `--fail-on` or worse; `none` exits 0. `fix` exits 1 if it could not fix any package.

**How do I suppress one advisory?** `[report] ignore = ["GHSA-..."]`.

**Do I need Node in CI?** Only for `--agent claude` or `codex`. The `api`, `openai` and `managed` backends need Python alone.

**Which ecosystems include transitive dependencies?** npm, pnpm, and yarn, through their lockfiles. For Python, Go, and Rust, set `[inventory] sbom` to a CycloneDX file to scan the full resolved tree.

## Development

```bash
git clone https://github.com/PrismorSec/patchbot && cd patchbot
python -m venv .venv && .venv/bin/pip install -e ".[dev,yaml,api]"
.venv/bin/pytest
docs/screenshots.sh              # regenerate docs/img (needs charmbracelet/freeze)
```

`examples/demo-npm` ships with a vulnerable `lodash` on purpose. The repository's own CI scans it, so the Security tab always shows live findings.

## License

MIT
