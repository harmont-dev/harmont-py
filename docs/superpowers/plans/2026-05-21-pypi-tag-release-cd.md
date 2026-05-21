# harmont-py PyPI Tag-Release CD — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Push a `v*` tag to `harmont-dev/harmont-py` → GitHub Actions builds the sdist and wheel, then publishes to PyPI via Trusted Publishing (OIDC; no API tokens stored in the repo).

**Architecture:** Mirror `harmont-cli/.github/workflows/release.yml` shape — tag-triggered, sed the version from the tag into `pyproject.toml` (which sits at `0.0.0-dev` in main), build via `python -m build`, publish via `pypa/gh-action-pypi-publish@release/v1` (OIDC-based). One repo, one workflow file, no third-party publishing secrets. The action runs inside a GitHub Environment called `release` so PyPI can scope the OIDC trust to that environment.

**Tech Stack:** GitHub Actions, `actions/checkout@v4`, `actions/setup-python@v5`, `python -m build` (PEP 517), `pypa/gh-action-pypi-publish@release/v1` (PyPI's official OIDC publisher), PyPI Trusted Publishing.

**Direct-to-main:** Per project convention, commits land on `main` in `/home/marko/harmont-py/`.

**One-time human prerequisites** (the workflow cannot work until these are done — they are spelled out in Task 4):

1. Configure a Trusted Publisher on PyPI for the `harmont` project: workflow filename `release.yml`, environment `release`, owner `harmont-dev`, repo `harmont-py`.
2. Create a GitHub Environment named `release` on `harmont-dev/harmont-py` with branch protection (optional but recommended): tags matching `v*` only.

---

## File Map

### `/home/marko/harmont-py/`

- **Create:** `.github/workflows/release.yml` — tag-triggered publish workflow.
- **Modify:** `pyproject.toml` — pin `version` to `"0.0.0-dev"` so non-tagged builds carry a clearly-not-released version; the workflow sed's the real version in from the tag at CI time. Mirrors `harmont-cli`'s pattern (every `Cargo.toml` has `0.0.0-dev`).
- **Modify:** `RELEASING.md` — replace the manual `twine upload` flow with the new tag-driven flow. Keep the monorepo subtree-push section unchanged.

No source code or test changes.

---

## Task 1: Pin pyproject.toml to a dev version

**Why first:** The workflow's `sed` substitution requires a stable marker to find. Pinning to `"0.0.0-dev"` upfront also keeps anyone who `pip install`s harmont-py from `main` from accidentally getting an artifact labeled with the last released version.

**Files:**
- Modify: `/home/marko/harmont-py/pyproject.toml`

- [ ] **Step 1: Edit pyproject.toml**

Locate the `[project]` block (currently around lines 5–14):

```toml
[project]
name = "harmont"
version = "0.1.0"
```

Change `version = "0.1.0"` to `version = "0.0.0-dev"`. Leave every other field as-is.

- [ ] **Step 2: Confirm the version string is grep-unique**

```bash
cd /home/marko/harmont-py
grep -n 'version = "0.0.0-dev"' pyproject.toml
```

Expected: one match in `pyproject.toml`. If two or more lines match, the sed in Task 2 will need a more specific anchor — fix the duplicate before continuing.

- [ ] **Step 3: Confirm imports + tests still work**

```bash
cd /home/marko/harmont-py
python3 -m pytest -x -q 2>&1 | tail -10
```

Expected: the suite passes (pre-existing failures unrelated to this work — gradle + haskell-CI-only paths — are documented; everything else green). Version is just a metadata string; no runtime code reads it.

- [ ] **Step 4: Commit**

```bash
cd /home/marko/harmont-py
git add pyproject.toml
git commit -m "$(cat <<'EOF'
chore: pin pyproject version to 0.0.0-dev

main-branch builds now carry a clearly-unreleased version marker.
The release.yml workflow (next commit) sed's the real version in
from the v* git tag at publish time, mirroring harmont-cli's
crates.io flow.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Write the release workflow

**Why next:** This is the load-bearing artifact. Two distinct jobs as in `harmont-cli/.github/workflows/release.yml`: nothing else, single file.

**Files:**
- Create: `/home/marko/harmont-py/.github/workflows/release.yml`

- [ ] **Step 1: Create the workflow directory**

```bash
mkdir -p /home/marko/harmont-py/.github/workflows
```

- [ ] **Step 2: Write the workflow file**

Create `/home/marko/harmont-py/.github/workflows/release.yml`:

```yaml
name: Release

on:
  push:
    tags:
      - "v*"

permissions:
  contents: read

jobs:
  pypi-publish:
    name: Publish to PyPI
    runs-on: ubuntu-latest
    environment:
      # PyPI Trusted Publisher is scoped to this environment. Configure
      # the matching publisher on https://pypi.org/manage/account/publishing/
      # before the first tag push (see RELEASING.md).
      name: release
      url: https://pypi.org/project/harmont/
    permissions:
      # `id-token: write` is the OIDC switch that pypa/gh-action-pypi-publish
      # uses to mint a short-lived token PyPI accepts in lieu of an API token.
      id-token: write
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Set version from tag
        run: |
          VERSION="${GITHUB_REF_NAME#v}"
          echo "VERSION=$VERSION" >> "$GITHUB_ENV"
          # Sed only the first match so this is a no-op if pyproject is
          # already at the tagged version (a re-run with a corrected tag,
          # for instance, shouldn't double-edit).
          sed -i '0,/version = "0.0.0-dev"/s//version = "'"$VERSION"'"/' pyproject.toml
          grep -n "^version" pyproject.toml

      - name: Install build
        run: python -m pip install --upgrade build

      - name: Build sdist and wheel
        run: python -m build

      - name: Inspect dist
        run: |
          ls -la dist/
          # Fail fast if either artifact is missing.
          test -f dist/harmont-${VERSION}.tar.gz
          test -f dist/harmont-${VERSION}-py3-none-any.whl

      - name: Publish to PyPI via Trusted Publishing
        uses: pypa/gh-action-pypi-publish@release/v1
        # No `with:` block needed — the action defaults to using OIDC
        # against the project's configured Trusted Publisher when
        # `id-token: write` is granted (above). It picks up dist/* by
        # default.
```

Key design choices, all matching `harmont-cli/release.yml`:

- **Trigger:** `push.tags: ["v*"]`. Tag-driven, no manual workflow_dispatch path.
- **Permissions:** `contents: read` at the workflow level; `id-token: write` only on the publish job. Minimum surface.
- **Environment `release`:** PyPI's Trusted Publisher binds to this exact environment name. Required.
- **Version-from-tag sed:** `GITHUB_REF_NAME` strips `v`. The `0,/.../s//.../` form replaces only the first match — same idiom as `harmont-cli/release.yml:27-29`.
- **Inspect dist:** Asserts both artifacts exist with the expected name shape before the publish step, so a build regression fails the job with a clear message instead of a confusing "no files to upload."
- **No `with:` on the publish action:** PyPI's recommended config; the action introspects `dist/` and uses OIDC by default.

- [ ] **Step 3: Lint the workflow yaml**

```bash
python3 -c "import yaml; yaml.safe_load(open('/home/marko/harmont-py/.github/workflows/release.yml'))" && echo yaml-ok
```

Expected: `yaml-ok`. If you have `actionlint` installed, also run it: `actionlint .github/workflows/release.yml`. Don't add actionlint as a new dependency just for this.

- [ ] **Step 4: Confirm `python -m build` succeeds locally**

```bash
cd /home/marko/harmont-py
python3 -m pip install --upgrade build 2>&1 | tail -3
python3 -m build 2>&1 | tail -10
ls dist/
```

Expected: `dist/harmont-0.0.0.dev0.tar.gz` and `dist/harmont-0.0.0.dev0-py3-none-any.whl` (setuptools normalizes `0.0.0-dev` to `0.0.0.dev0`; the dev-version name shape proves the build path works end-to-end). The CI job will see `0.0.0-dev` replaced with the real tag version, so the produced files will be named `harmont-<version>.tar.gz` etc. — that's what the `test -f` checks in the workflow validate.

After confirming, clean up:

```bash
rm -rf /home/marko/harmont-py/dist /home/marko/harmont-py/build /home/marko/harmont-py/harmont.egg-info
```

- [ ] **Step 5: Commit**

```bash
cd /home/marko/harmont-py
git add .github/workflows/release.yml
git commit -m "$(cat <<'EOF'
ci: add release.yml — tag-triggered PyPI publish via OIDC

Mirrors harmont-cli/.github/workflows/release.yml: push a tag
matching v* → GH Actions builds the sdist + wheel, sed's the
version from the tag into pyproject.toml, and publishes to PyPI
using pypa/gh-action-pypi-publish@release/v1 with Trusted
Publishing (OIDC, no API tokens in the repo).

Runs inside a GH Environment named `release` so PyPI's Trusted
Publisher can scope the OIDC trust. The Publisher must be
configured on PyPI before the first tag push (see RELEASING.md).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Update RELEASING.md to describe the new flow

**Files:**
- Modify: `/home/marko/harmont-py/RELEASING.md`

- [ ] **Step 1: Open RELEASING.md and locate the "Cutting a release" section**

The section currently runs `pytest`/`mypy`/`ruff`, then `python -m build`, then `twine upload dist/*` manually. Replace it wholesale with the tag-driven shape. Keep the "How the mirror is synced" and "Ongoing sync (monorepo → public)" sections — those describe the subtree mirror which is unchanged.

- [ ] **Step 2: Rewrite the "Cutting a release" section**

Replace lines starting at `## Cutting a release` through the end of the file with:

```markdown
## Cutting a release

Versioning is **driven by git tags on the public mirror**. The release
workflow in `.github/workflows/release.yml` triggers on any tag matching
`v*`, seds the version from the tag into `pyproject.toml`, builds the
sdist and wheel, and publishes to PyPI via Trusted Publishing (OIDC —
no API tokens stored in the repo).

### Prerequisites (one-time)

1. **Configure the PyPI Trusted Publisher** on
   <https://pypi.org/manage/project/harmont/settings/publishing/> with:
   - Owner: `harmont-dev`
   - Repository: `harmont-py`
   - Workflow filename: `release.yml`
   - Environment: `release`

   If the `harmont` project does not yet exist on PyPI, create it via a
   one-off manual `twine upload` first (or use the "Add a pending
   publisher" flow at <https://pypi.org/manage/account/publishing/>),
   then add the Trusted Publisher.

2. **Create the `release` GitHub Environment** on
   <https://github.com/harmont-dev/harmont-py/settings/environments>.
   Recommended protection rules:
   - Deployment branches and tags → "Selected branches and tags" →
     add tag rule `v*`.
   - (Optional) required reviewers on the environment so a human has
     to click "approve" before publish runs.

### Releasing

1. Update `CHANGELOG.md` or release notes locally if you keep them.
2. Tag from the monorepo (source of truth):

   ```sh
   git tag v<version>
   git subtree push --prefix=cidsl/py git@github.com:harmont-dev/harmont-py.git main
   git push git@github.com:harmont-dev/harmont-py.git v<version>
   ```

   The tag has to land on the **public** repo for the workflow to fire.
   The subtree-push lands the corresponding `main` commit there first
   so the tag points at the right SHA.

3. Watch the run:

   ```sh
   gh run watch \
     "$(gh run list --repo harmont-dev/harmont-py --workflow release.yml \
        --limit 1 --json databaseId --jq '.[0].databaseId')" \
     --repo harmont-dev/harmont-py --exit-status
   ```

4. Confirm the release on <https://pypi.org/project/harmont/>.
5. (Optional) Create a GitHub Release on the same tag with notes:

   ```sh
   gh release create v<version> --repo harmont-dev/harmont-py \
     --title "harmont v<version>" --generate-notes
   ```

### Troubleshooting

- **`Trusted publishing exchange failed`:** the GH Environment name in
  the workflow does not match the one configured on PyPI. Both must be
  exactly `release`.
- **`File already exists`:** the version was already published to PyPI.
  PyPI is append-only — bump the version, re-tag, re-push.
- **`No files to upload`:** the build step did not produce
  `dist/*.tar.gz` and `dist/*.whl`. Inspect the `Build sdist and wheel`
  step output. Most common cause: `setuptools` couldn't find a package
  to build because `pyproject.toml` was mid-edit.
```

- [ ] **Step 3: Quick markdown sanity check**

```bash
cd /home/marko/harmont-py
head -100 RELEASING.md  # eyeball the structure
```

Confirm: the "How the mirror is synced", "Forcing a manual sync", and "Pulling external contributions back" sections are preserved; "Cutting a release" now describes the tag-driven flow; no stray references to `twine upload` remain.

- [ ] **Step 4: Commit**

```bash
cd /home/marko/harmont-py
git add RELEASING.md
git commit -m "$(cat <<'EOF'
docs(releasing): document tag-driven PyPI CD via OIDC

Replaces the manual `python -m build` + `twine upload` flow with
the new release.yml workflow. Lists the one-time PyPI Trusted
Publisher + GH Environment setup steps and the per-release
`git tag` + `subtree push` sequence.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: One-time PyPI + GitHub Environment setup (HUMAN, not the agent)

**Why:** The agent cannot click into PyPI's or GitHub's UI. These steps are spelled out so the user runs them once. The workflow will fail until both are in place.

This is a **manual** task — the agent reports it as DONE without doing anything programmatic. The instructions are repeated here so the executor flags them to the human at the end of the implementation pass.

- [ ] **Step 1: Verify the project exists on PyPI (or create a pending publisher)**

Visit <https://pypi.org/project/harmont/>. If a "Page not found" appears, the project name is unclaimed. Two paths:

- **Pending publisher** (preferred — no manual `twine upload` needed):
  Go to <https://pypi.org/manage/account/publishing/> → "Add a pending
  publisher" → fill `harmont`, `harmont-dev`, `harmont-py`,
  `release.yml`, `release`. The first successful tag-push will claim
  the name and run the publish.

- **Manual claim:** `python -m build && twine upload dist/*` once with
  a personal API token. Then configure the Trusted Publisher (Step 2).

- [ ] **Step 2: Configure the Trusted Publisher on PyPI**

If the project already exists, visit
<https://pypi.org/manage/project/harmont/settings/publishing/>.

Click "Add a new publisher" → GitHub. Fill exactly:

- Owner: `harmont-dev`
- Repository name: `harmont-py`
- Workflow name: `release.yml`
- Environment name: `release`

Save.

- [ ] **Step 3: Create the `release` GitHub Environment**

Visit <https://github.com/harmont-dev/harmont-py/settings/environments>.
Click "New environment" → name it `release` → "Configure environment".

Set the following protection rules:

- **Deployment branches and tags:** "Selected branches and tags". Click
  "Add deployment branch or tag rule" → choose "Tag" → pattern `v*`.
  This prevents anyone from running the publish workflow against a
  non-tag ref.
- (Optional) **Required reviewers:** add yourself or a small list. With
  reviewers set, every release pauses for human approval before the
  publish step runs. Useful for catching accidental tag pushes.

Save.

- [ ] **Step 4: Smoke test**

Don't tag a real release yet. The smoke test goes in Task 5.

---

## Task 5: Push the workflow + version-bump commits to main

**Why:** After this push, the workflow file is in place on the public repo and the user can tag whenever they're ready. Tagging and watching the publish are explicitly out-of-scope per user direction; they'll handle those steps themselves.

**Files:** none.

- [ ] **Step 1: Confirm the staged commits**

```bash
cd /home/marko/harmont-py
git log --oneline origin/main..HEAD
```

Expected: three commits — pyproject pin to 0.0.0-dev, the new release.yml, and the RELEASING.md rewrite.

- [ ] **Step 2: Push to main**

```bash
cd /home/marko/harmont-py
git push origin main
```

Expected: three commits land on origin/main. After this, the workflow is dormant until a `v*` tag is pushed.

- [ ] **Step 3: Hand off**

Report back to the user:
- The three SHAs that landed.
- A reminder of the one-time PyPI Trusted Publisher + GH `release` environment setup (Task 4) that has to happen before the first tag-push.
- The tag-push command the user will run themselves (`git tag v<version> && git push origin v<version>`), so they have it handy.

---

## Out of scope

- **CI** (running tests on every push/PR). This plan is **CD only**. A
  `test.yml` workflow that runs `pytest` on push is a separate concern
  — the existing local `pytest` workflow is enough until contributors
  arrive. Don't bundle it here.
- **Publishing to TestPyPI as a staging step.** The rc-tag smoke test
  in Task 5 is sufficient — it exercises the full real path with a
  pre-release version label, which is closer to production than a
  separate TestPyPI environment would be.
- **Bumping the harmont-cli CI workflow's `pip install /tmp/harmont-py`
  to point at the tagged PyPI release.** Currently CI clones harmont-py
  main and pip-installs from source; that path is fine and keeps the
  cross-repo feedback loop fast. Switching to PyPI is a follow-up if
  someone wants reproducible CI against pinned versions.
- **A custom `build` system other than setuptools.** The existing
  `pyproject.toml` uses `setuptools.build_meta`; `python -m build`
  honors that. No reason to change.

---

## Self-review

- **Spec coverage:** Workflow ✓ (Task 2); pyproject pin ✓ (Task 1); docs
  ✓ (Task 3); manual prereqs called out ✓ (Task 4); push to main ✓
  (Task 5). Tagging + publishing intentionally out of scope (user
  handles).
- **Placeholder scan:** no "TBD", "implement later", "as needed". Every
  command has an expected output or a clear next step on failure.
- **Type/name consistency:** environment name `release` is used
  identically in (a) the workflow YAML, (b) the PyPI Trusted Publisher
  setup, (c) the GitHub Environment creation, (d) the RELEASING.md
  prose. Workflow filename `release.yml` is consistent everywhere.
  Project name on PyPI is `harmont` (matches `pyproject.toml`
  `name = "harmont"` — verified during plan-writing).
- **No `id-token: write` outside the publish job.** Confirmed.
