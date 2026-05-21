# Releasing harmont-py

This package lives upstream at <https://github.com/harmont-dev/harmont-py> and is mirrored into the private Harmont monorepo as `cidsl/py/`. The monorepo is the source of truth; the public repo receives a `git subtree push`.

## One-time setup

```sh
gh repo create harmont-dev/harmont-py --public \
  --description "Python DSL for Harmont CI pipelines" \
  --homepage https://harmont.dev

# Initial split from the monorepo (run from the monorepo root)
git subtree split --prefix=cidsl/py -b harmont-py-export
git push git@github.com:harmont-dev/harmont-py.git harmont-py-export:main
git branch -D harmont-py-export
```

## Ongoing sync (monorepo → public)

```sh
git subtree push --prefix=cidsl/py git@github.com:harmont-dev/harmont-py.git main
```

If subtree-push fails because the public repo has commits that aren't in the monorepo's history, fall back to a fresh split:

```sh
git subtree split --prefix=cidsl/py -b harmont-py-export
git push git@github.com:harmont-dev/harmont-py.git harmont-py-export:main
git branch -D harmont-py-export
```

## Pulling external contributions back (public → monorepo)

```sh
git subtree pull --prefix=cidsl/py git@github.com:harmont-dev/harmont-py.git main --squash
```

## Cutting a release

1. Bump `version` in `cidsl/py/pyproject.toml`.
2. Run the full check from `cidsl/py/`:

   ```sh
   pytest
   mypy --strict harmont
   ruff check .
   ```

3. Build the sdist and wheel:

   ```sh
   pip install --upgrade build twine
   python -m build
   ```

4. Inspect the artifacts under `dist/` — confirm `LICENSE` and `README.md` are bundled.
5. Commit the version bump in the monorepo.
6. Tag: `git tag harmont-py-v<version> && git push origin harmont-py-v<version>`.
7. Subtree-push to the public repo (see "Ongoing sync" above).
8. `twine upload dist/*` (requires `~/.pypirc` or `TWINE_USERNAME`/`TWINE_PASSWORD`).
9. Create a GitHub release on `harmont-dev/harmont-py` at tag `v<version>`, linking to PyPI.
