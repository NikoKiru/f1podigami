# Workflow Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dataset validation gate to `deploy.yml`, add an `actionlint` CI job to `ci.yml`, and SHA-pin all remaining `@vN` action references across five workflow files.

**Architecture:** Pure CI config changes — no Python source touched. Three independent commits, then one PR. The actionlint job uses `rhysd/actionlint` pinned to a SHA, consistent with the project's existing SHA-pin style for third-party actions.

**Tech Stack:** GitHub Actions YAML, `rhysd/actionlint` v1.7.12

**Resolved SHAs (as of 2026-06-29):**
| Action | SHA | Tag |
|--------|-----|-----|
| `actions/checkout` | `9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0` | v7 |
| `actions/setup-python` | `ece7cb06caefa5fff74198d8649806c4678c61a1` | v6 |
| `actions/upload-artifact` | `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a` | v7 |
| `actions/upload-pages-artifact` | `fc324d3547104276b827a68afc52ff2a11cc49c9` | v5 |
| `actions/deploy-pages` | `cd2ce8fcbc39b97be8ca5fce6e763baed58fa128` | v5 |
| `github/codeql-action/{init,analyze}` | `411bbbe57033eedfc1a82d68c01345aa96c737d7` | v4 |
| `rhysd/actionlint` | `914e7df21a07ef503a81201c76d2b11c789d3fca` | v1.7.12 |

---

## Task 0: Create feature branch

- [ ] **Step 1: Branch off main**

```bash
git checkout -b feat/workflow-hardening
```

---

## Task 1: Add validate gate to `deploy.yml`

**Files:**
- Modify: `.github/workflows/deploy.yml`

- [ ] **Step 1: Insert validate step before `Build site`**

In `.github/workflows/deploy.yml`, replace:

```yaml
      - name: Run tests (deploy is blocked if these fail)
        run: pytest -q
      - name: Build site
```

with:

```yaml
      - name: Run tests (deploy is blocked if these fail)
        run: pytest -q
      - name: Validate datasets
        run: PYTHONPATH=src python -m datalib.validate
      - name: Build site
```

- [ ] **Step 2: Verify the file looks right**

Run: `grep -n "Validate\|Build site\|pytest" .github/workflows/deploy.yml`

Expected output shows three lines in order: pytest, Validate datasets, Build site.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/deploy.yml
git commit -m "ci: add datalib.validate gate to deploy.yml"
```

---

## Task 2: Add `actionlint` job to `ci.yml`

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Append the `actionlint` job at the end of `ci.yml`**

At the end of `.github/workflows/ci.yml` (after the `build` job), add:

```yaml

  actionlint:
    name: Lint workflows
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7
      - name: Run actionlint
        uses: rhysd/actionlint@914e7df21a07ef503a81201c76d2b11c789d3fca # v1.7.12
```

Note: this `checkout` reference will be replaced in Task 3's SHA-pinning pass. The value used here is already the pinned SHA, so Task 3's replacement will be a no-op for this line.

- [ ] **Step 2: Verify structure**

Run: `grep -n "actionlint\|Lint workflows" .github/workflows/ci.yml`

Expected: two matching lines near the end of the file.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add actionlint job to ci.yml"
```

---

## Task 3: SHA-pin `actions/checkout` across all five files

**Files:**
- Modify: `.github/workflows/ci.yml`, `deploy.yml`, `update.yml`, `codeql.yml`, `security.yml`

Replace every occurrence of `actions/checkout@v7` with `actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7` in all five files.

- [ ] **Step 1: Replace in `ci.yml`**

Use `replace_all: true`. Replace:
```
actions/checkout@v7
```
with:
```
actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7
```

- [ ] **Step 2: Replace in `deploy.yml`**

Same replacement (single occurrence).

- [ ] **Step 3: Replace in `update.yml`**

Same replacement (single occurrence).

- [ ] **Step 4: Replace in `codeql.yml`**

Same replacement (single occurrence).

- [ ] **Step 5: Replace in `security.yml`**

Same replacement (single occurrence).

- [ ] **Step 6: Verify**

Run: `grep -rn "checkout@v7" .github/workflows/`

Expected: no output (all replaced).

---

## Task 4: SHA-pin `actions/setup-python` across three files

**Files:**
- Modify: `.github/workflows/ci.yml`, `deploy.yml`, `update.yml`

Replace every occurrence of `actions/setup-python@v6` with `actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6`.

- [ ] **Step 1: Replace in `ci.yml`** (appears 4 times — use `replace_all: true`)

Replace:
```
actions/setup-python@v6
```
with:
```
actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6
```

- [ ] **Step 2: Replace in `deploy.yml`** (single occurrence)

Same replacement.

- [ ] **Step 3: Replace in `update.yml`** (single occurrence)

Same replacement.

- [ ] **Step 4: Verify**

Run: `grep -rn "setup-python@v6" .github/workflows/`

Expected: no output.

---

## Task 5: SHA-pin remaining `@vN` refs

**Files:**
- Modify: `.github/workflows/ci.yml`, `deploy.yml`, `codeql.yml`

- [ ] **Step 1: Pin `actions/upload-artifact@v7` in `ci.yml`**

Replace:
```
actions/upload-artifact@v7
```
with:
```
actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7
```

- [ ] **Step 2: Pin `actions/upload-pages-artifact@v5` in `deploy.yml`**

Replace:
```
actions/upload-pages-artifact@v5
```
with:
```
actions/upload-pages-artifact@fc324d3547104276b827a68afc52ff2a11cc49c9 # v5
```

- [ ] **Step 3: Pin `actions/deploy-pages@v5` in `deploy.yml`**

Replace:
```
actions/deploy-pages@v5
```
with:
```
actions/deploy-pages@cd2ce8fcbc39b97be8ca5fce6e763baed58fa128 # v5
```

- [ ] **Step 4: Pin `github/codeql-action/init@v4` in `codeql.yml`**

Replace:
```
github/codeql-action/init@v4
```
with:
```
github/codeql-action/init@411bbbe57033eedfc1a82d68c01345aa96c737d7 # v4
```

- [ ] **Step 5: Pin `github/codeql-action/analyze@v4` in `codeql.yml`**

Replace:
```
github/codeql-action/analyze@v4
```
with:
```
github/codeql-action/analyze@411bbbe57033eedfc1a82d68c01345aa96c737d7 # v4
```

- [ ] **Step 6: Final verification — no unpinned @vN refs remain**

Run: `grep -rn "@v[0-9]" .github/workflows/`

Expected: no output.

- [ ] **Step 7: Commit**

```bash
git add .github/workflows/
git commit -m "ci: SHA-pin all remaining @vN action refs"
```

---

## Task 6: Update RELEASE_NOTES.md

**Files:**
- Modify: `RELEASE_NOTES.md`

- [ ] **Step 1: Add entry under today's date heading**

Add under `## 2026-06-29` (create if absent):

```markdown
### Improvements
- Harden CI: add `datalib.validate` gate to `deploy.yml`, `actionlint` workflow linter, and SHA-pin all action refs (#114)
```

- [ ] **Step 2: Commit**

```bash
git add RELEASE_NOTES.md
git commit -m "docs: add release note for workflow hardening (#114)"
```

---

## Task 7: Open PR, merge, and deploy

- [ ] **Step 1: Push branch and open PR**

```bash
git push -u origin feat/workflow-hardening
```

```bash
gh pr create \
  --title "ci: lint & harden GitHub Actions workflows (#114)" \
  --body "$(cat <<'EOF'
## Summary
Closes #114. Three hardening changes to the CI/CD workflows:
- Added `datalib.validate` gate to `deploy.yml` (defence-in-depth: catches schema violations on manual workflow_dispatch deploys)
- Added `actionlint` job to `ci.yml` (static-checks shell scripts and expression syntax in all workflow files)
- SHA-pinned all remaining `@vN` action references (supply-chain hardening; Dependabot already configured to update these)

## Changes
- `.github/workflows/deploy.yml`: add `Validate datasets` step before `Build site`
- `.github/workflows/ci.yml`: add `actionlint` job using `rhysd/actionlint@v1.7.12` (SHA-pinned)
- All five workflow files: replace `@vN` tags with commit-SHA pins + inline version comments

## Testing
- `actionlint` job will self-validate all workflows on the PR CI run
- `deploy.yml` validate step verified by inspection (mirrors identical step in `ci.yml` and `update.yml`)
- SHA values resolved from GitHub API on 2026-06-29

## Checklist
- [x] Lint: no Python changes; workflow YAML validated by actionlint in CI
- [x] Format: N/A
- [x] Tests: N/A (no Python changes)
- [x] No secrets introduced
- [x] RELEASE_NOTES.md updated
EOF
)"
```

- [ ] **Step 2: Open PR**

```bash
gh pr create \
  --title "ci: lint & harden GitHub Actions workflows (#114)" \
  --body "$(cat <<'EOF'
## Summary
Closes #114. Three hardening changes to the CI/CD workflows:
- Added `datalib.validate` gate to `deploy.yml` (defence-in-depth: catches schema violations on manual workflow_dispatch deploys)
- Added `actionlint` job to `ci.yml` (static-checks shell scripts and expression syntax in all workflow files)
- SHA-pinned all remaining `@vN` action references (supply-chain hardening; Dependabot already configured to update these)

## Changes
- `.github/workflows/deploy.yml`: add `Validate datasets` step before `Build site`
- `.github/workflows/ci.yml`: add `actionlint` job using `rhysd/actionlint@v1.7.12` (SHA-pinned)
- All five workflow files: replace `@vN` tags with commit-SHA pins + inline version comments

## Testing
- `actionlint` job will self-validate all workflows on the PR CI run
- `deploy.yml` validate step verified by inspection (mirrors identical step in `ci.yml` and `update.yml`)
- SHA values resolved from GitHub API on 2026-06-29

## Checklist
- [x] Lint: no Python changes; workflow YAML validated by actionlint in CI
- [x] Format: N/A
- [x] Tests: N/A (no Python changes)
- [x] No secrets introduced
- [x] RELEASE_NOTES.md updated
EOF
)"
```

- [ ] **Step 3: Enable auto-merge**

```bash
gh pr merge --auto --squash "$(gh pr list --head "$(git branch --show-current)" --json number --jq '.[0].number')"
```

- [ ] **Step 4: Monitor CI**

```bash
gh pr checks "$(gh pr list --head "$(git branch --show-current)" --json number --jq '.[0].number')" --watch
```

Wait for all checks to pass. The `actionlint` job will run on this PR and validate the very workflow files being changed.

- [ ] **Step 5: Confirm deploy**

After merge, confirm the deploy workflow triggered:

```bash
gh run list --workflow=deploy.yml --limit=3
```

Expected: a new run in `queued` or `in_progress` state triggered by the merge to `main`.
