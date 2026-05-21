# harmont-py

[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Python DSL for defining [Harmont](https://harmont.dev) CI pipelines. Pipelines are chains of shell commands, branched with `.fork()`, synchronized with `hm.wait()`, registered with a decorator, and rendered to a JSON IR consumed by the Harmont runner.

Pipelines defined with this package are run by the companion [`harmont-cli`](https://github.com/harmont-dev/harmont-cli) (`hm run`).

The package installs as `harmont` and you import it as `harmont`:

```python
import harmont as hm
```

## Install

`harmont` is not yet published to PyPI. Install from source:

```sh
git clone https://github.com/harmont-dev/harmont-py
cd harmont-py
pip install -e .
```

For development (tests, mypy, ruff):

```sh
pip install -e '.[dev]'
```

Requires Python 3.11+.

## Quickstart

A pipeline file lives at `.harmont/<slug>.py` in your repo. The simplest one:

```python
import harmont as hm


@hm.pipeline("hello")
def hello() -> hm.Step:
    return (
        hm.sh("echo 'hello from harmont'", label="hello")
            .sh("uname -a", label="env")
    )
```

The DSL primitives:

| Primitive                        | Returns | What it does                                                                 |
| -------------------------------- | ------- | ---------------------------------------------------------------------------- |
| `hm.sh(cmd, cwd=..., label=...)` | `Step`  | Start a chain in one call (= `hm.scratch().sh(cmd, ...)`).                   |
| `hm.scratch()`                   | `Step`  | Empty root; chain with `.sh(...)` for an explicit start.                     |
| `Step.sh(cmd, cwd=..., ...)`     | `Step`  | Run a shell command. Chained `.sh` calls share container state.              |
| `Step.fork(label=...)`           | `Step`  | Branch from a shared base into parallel work.                                |
| `hm.wait()`                      | `Step`  | Explicit synchronization barrier.                                            |
| `@hm.target()`                   | decorator | Reusable, memoized building block (composed into one or more pipelines).     |
| `@hm.pipeline("slug")`           | decorator | Register a pipeline. Multiple per file are fine.                             |
| `hm.pipeline(*leaves, env=...)`  | `dict`  | Factory form — build the v0 IR dict directly (used in tests).                |

Cache policies (`hm.ttl`, `hm.on_change`, `hm.forever`, `hm.compose`), triggers (`hm.push`, `hm.pull_request`, `hm.schedule`), and matrix axes are documented in the module docstrings; see `harmont/__init__.py`.

A two-branch example:

```python
@hm.pipeline("ci")
def ci() -> hm.Step:
    setup = hm.sh(
        "apt-get update && apt-get install -y curl",
        label="apt",
    )
    fetch = setup.fork(label="branch-a").sh(
        "curl -fsSL https://example.com",
        label="fetch",
    )
    work = setup.fork(label="branch-b").sh(
        "echo independent work",
        label="other",
    )
    return hm.pipeline(fetch, work, default_image="ubuntu:24.04")
```

### Typed fixture-style target deps

Declare dependencies with `Target[T]` annotations (resolved by parameter
name from the global `@hm.target` registry) and base images with
`Annotated[Step, BaseImage("...")]`:

```python
from typing import Annotated

@hm.target()
def apt_base(base: Annotated[hm.Step, hm.BaseImage("ubuntu-24.04")]) -> hm.Step:
    return base.sh("apt-get update").sh("apt-get install -y curl")

@hm.target()
def api(apt_base: hm.Target[hm.Step]) -> hm.Step:
    return apt_base.sh("cabal build", cwd="api")

@hm.pipeline("ci")
def ci(api: hm.Target[hm.Step]) -> hm.Step:
    return api
```

Markers are required for every fixture parameter — unmarked params
raise at decoration time. Both `Target[T]` and `BaseImage(...)` use
standard PEP 593 `Annotated`; mypy and pyright unwrap them to their
concrete types (`assert_type(apt_base, Step)` passes under
`mypy --strict`).

Once the file is in place, run the pipeline with the [Harmont CLI](https://github.com/harmont-dev/harmont-cli):

```sh
hm run hello --local
```

## How it works

`hm.sh(...).sh(...)` builds a chain of frozen `Step` dataclasses. Each `.sh()` returns a new `Step` carrying the parent reference. The `hm.pipeline()` factory walks back from each leaf, topo-sorts, and emits a `version: "0"` IR dict matching the schema in `harmont-pipeline` (Haskell side).

When used as a decorator, `@hm.pipeline("slug")` registers the wrapped function with a module-level registry. `hm.dump_registry_json()` walks every `.harmont/*.py`, imports each (which triggers the decorators), and returns the full envelope.

The JSON wire format and cache-key algorithm are stable; see the module docstrings under `harmont/` for the contract.

## Build & test

```sh
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'

pytest                                  # all tests
pytest -v --tb=short
mypy --strict harmont
ruff check .
```

`pytest` is configured to treat warnings as errors (`filterwarnings = ["error"]`).

## See also

- [`harmont-cli`](https://github.com/harmont-dev/harmont-cli) — the CLI that consumes the JSON this package emits and runs pipelines locally with Docker (`hm run --local`).

## License

MIT. See [`LICENSE`](LICENSE).
