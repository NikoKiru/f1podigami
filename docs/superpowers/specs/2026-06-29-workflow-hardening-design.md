# Workflow Hardening Design

**Date:** 2026-06-29
**Issue:** #114 — Lint & harden the GitHub Actions workflows

## Overview

Three targeted changes to the GitHub Actions workflows: add a dataset validation gate to `deploy.yml`, add an `actionlint` job to `ci.yml`, and SHA-pin all remaining `@vN` action references.

## 1. `deploy.yml` — validate gate

Insert a `Validate datasets` step before `Build site` in the `build` job:

```yaml
- name: Validate datasets
  run: PYTHONPATH=src python -m datalib.validate
```

This mirrors the identical step already present in `ci.yml`'s `build` job and in `update.yml`. No new dependencies — pydantic is already in `requirements.txt`.

**Why:** A `workflow_dispatch` deploy on a commit that passed CI but carries a bad dataset (e.g., a manual data edit that slipped schema validation) would otherwise ship silently. The validate gate is a cheap defence-in-depth check.

## 2. `ci.yml` — `actionlint` job

Add a new `actionlint` job alongside the existing `lint`, `test`, `e2e`, and `build` jobs:

```yaml
actionlint:
  name: Lint workflows
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@<SHA> # v7
    - name: Run actionlint
      run: |
        bash <(curl -s https://raw.githubusercontent.com/rhysd/actionlint/main/scripts/download-actionlint.bash)
        ./actionlint -color
```

`actionlint` statically checks: embedded shell scripts in `run:` blocks, expression syntax (`${{ ... }}`), event/trigger types, permissions, and context field names. CodeQL's `"actions"` language matrix handles some of this but misses shell-level checks inside `run:` steps — which is exactly where `update.yml`'s non-trivial PR/push logic lives.

The job is not added to any `needs:` chain; it runs independently and does not block other jobs.

## 3. SHA pinning

Pin all remaining `@vN` action references to their commit SHAs with an inline version comment. The seven refs across five files:

| File | Action | Tag |
|------|--------|-----|
| `ci.yml`, `deploy.yml`, `update.yml`, `codeql.yml`, `security.yml` | `actions/checkout` | v7 |
| `ci.yml`, `deploy.yml`, `update.yml` | `actions/setup-python` | v6 |
| `ci.yml` | `actions/upload-artifact` | v7 |
| `deploy.yml` | `actions/upload-pages-artifact` | v5 |
| `deploy.yml` | `actions/deploy-pages` | v5 |
| `codeql.yml` | `github/codeql-action/init` | v4 |
| `codeql.yml` | `github/codeql-action/analyze` | v4 |

SHAs are resolved from GitHub's API at implementation time. Format: `uses: actions/checkout@<sha> # v7.x.y`.

Dependabot's existing `github-actions` weekly group (`dependabot.yml`) already handles SHA-pinned actions — it will open PRs to bump the SHA whenever a new tag is released, so ongoing maintenance is automatic.

## Scope

No changes to `security.yml`, `codeql.yml` (beyond SHA pins), or `dependabot-automerge.yml` logic. No pre-commit hook added (CI gate is sufficient). No changes to Python source or tests.
