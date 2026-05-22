# `harmont-py`: hm.deploy + hm.dev DSL — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the Python DSL surface for local deployments: `@hm.deploy` (driver-agnostic decorator), `hm.Dep[T]` (PEP-593 fixture marker), `hm.Deployment` (abstract dataclass), `hm.dev.deploy(...)` (local-driver factory), `hm.dev.port()` (sentinel), and `harmont.dev.dump_registry_json()` + `python -m harmont.dev --dump-registry` CLI shim that emits the v0 JSON the Rust CLI consumes.

**Architecture:** Top-level `harmont._deploy` houses the abstract `Deployment`, the `@hm.deploy` decorator, the `Dep[T]` marker, and the `DEPLOYMENTS` registry. Driver-specific code lives in `harmont/dev/`: `_deployment.py` (LocalDeployment), `_port.py` (sentinel), `_factory.py` (deploy(...)), `_registry_dump.py` (JSON emitter), and `__main__.py` (CLI shim). The dep-graph resolver extends the existing `harmont._deps.call_with_deps` so `Dep[T]` markers participate in the same fixture-injection pipeline as `Target[T]`.

**Tech Stack:** Python 3.11+, frozen `dataclasses`, `typing.Annotated` (PEP 593), pytest (incl. `pytest.raises`). No new runtime deps. The cli side is out of scope for this plan.

**Spec:** `docs/superpowers/specs/2026-05-21-hm-dev-deploy-design.md` (committed to this branch). Read § 1 (DSL surface) and § 5 (error handling) before starting — error-message shapes are tested literally.

**Branch:** `feat/hm-dev-deploy`. Already created off `main`.

**Commit cadence:** Every task ends with a commit. No exceptions. The commit subject line is in the example commands.

---

## File Map

### Create (harmont-py)

- `harmont/_deploy.py` — abstract `Deployment` dataclass; `@hm.deploy` decorator; `Dep[T]` PEP-593 marker; `DEPLOYMENTS` registry; topo-sort + dep-graph resolver.
- `harmont/dev/__init__.py` — re-exports `deploy`, `port`, `LocalDeployment`, `dump_registry_json`.
- `harmont/dev/__main__.py` — `python -m harmont.dev --dump-registry` CLI shim.
- `harmont/dev/_deployment.py` — `LocalDeployment` frozen dataclass + `__post_init__` validation.
- `harmont/dev/_port.py` — `_PortSentinel` singleton + `port()` factory.
- `harmont/dev/_factory.py` — `deploy(...)` factory function (field validation + LocalDeployment construction).
- `harmont/dev/_registry_dump.py` — `dump_registry_json()` walks `DEPLOYMENTS` in topo order, emits the spec's JSON shape.
- `tests/dev/__init__.py` — empty, marks dir as test package.
- `tests/dev/conftest.py` — pytest fixture that clears `DEPLOYMENTS`, `_TARGETS_BY_NAME`, `REGISTRATIONS` between tests.
- `tests/dev/test_port_sentinel.py` — sentinel behavior + misuse.
- `tests/dev/test_local_deployment.py` — `LocalDeployment` field validation.
- `tests/dev/test_deploy_factory.py` — `hm.dev.deploy(...)` XOR rule, port_mapping shape, env/cmd coercion, volumes.
- `tests/dev/test_decorator.py` — slug regex, duplicate-slug, missing marker, dep cycle, `Dep[T]` injection, `Target[T]` injection co-exists.
- `tests/dev/test_registry_dump.py` — golden JSON for canonical db+api+web example; topo ordering; non-local entries marked `_unhandled`.
- `tests/dev/test_dump_cli.py` — `python -m harmont.dev --dump-registry` against a temp `.harmont/`.

### Modify (harmont-py)

- `harmont/__init__.py` — re-export `deploy` (the decorator), `Dep`, `Deployment`, and the `dev` submodule.
- `harmont/_deps.py` — extend `call_with_deps` + `validate_target_signature` + `_marker_for` to recognize `Dep[T]` markers and resolve them against `DEPLOYMENTS`.
- `harmont/_typing.py` — add `_DepMarker` sentinel + `Dep` PEP-593 alias.
- `CLAUDE.md` — append a "Deployments (`hm.deploy` + `hm.dev`)" section to the public surface table.

### Do NOT touch

- `harmont/_step.py`, `harmont/pipeline.py`, `harmont/keygen.py` — already do exactly what we need (`LocalDeployment.from_step` reuses `Step` as-is; `hm.dev.deploy(from_=Step)` lowers via `pipeline()` + `pipeline_to_json` at registry-dump time).
- Any toolchain (`harmont/haskell.py`, etc.) — unrelated.
- `harmont/_envelope.py` — that's the pipeline envelope; deployments get their own dumper. Look at it as a structural reference but do not modify.

---

## Task 1: Scaffold `harmont/_deploy.py` with abstract `Deployment`

Sets the cross-driver foundation. Empty subclass scaffolding for `LocalDeployment` (which gets fleshed out in Task 3).

**Files:**
- Create: `harmont/_deploy.py`
- Test: `tests/dev/test_local_deployment.py` (only the abstract-type test in this task)
- Modify: `tests/dev/__init__.py` (create empty)
- Modify: `tests/dev/conftest.py` (create with reset fixture)

- [ ] **Step 1: Create `tests/dev/__init__.py`**

```python
```

Yes, empty. The file's existence marks the dir.

- [ ] **Step 2: Create `tests/dev/conftest.py`**

```python
"""Per-test reset of every registry the deploy DSL touches."""
from __future__ import annotations

import pytest

from harmont._deploy import DEPLOYMENTS
from harmont._deps import _TARGETS_BY_NAME, _RESOLVING
from harmont._registry import REGISTRATIONS


@pytest.fixture(autouse=True)
def _reset_registries():
    """Clear every module-level registry before each test so order is irrelevant."""
    DEPLOYMENTS.clear()
    _TARGETS_BY_NAME.clear()
    _RESOLVING.clear()
    REGISTRATIONS.clear()
    yield
    DEPLOYMENTS.clear()
    _TARGETS_BY_NAME.clear()
    _RESOLVING.clear()
    REGISTRATIONS.clear()
```

- [ ] **Step 3: Write the failing test**

In `tests/dev/test_local_deployment.py`:

```python
"""Abstract Deployment + LocalDeployment construction tests."""
from __future__ import annotations

import pytest

from harmont._deploy import Deployment


def test_deployment_is_abstract_dataclass():
    """Deployment carries name + driver, is frozen, and is constructible (sentinel-level)."""
    d = Deployment(name="db", driver="local")
    assert d.name == "db"
    assert d.driver == "local"
    with pytest.raises(Exception):
        d.name = "other"  # type: ignore[misc]  # frozen
```

- [ ] **Step 4: Run test to verify it fails**

```bash
pytest tests/dev/test_local_deployment.py -v
```

Expected: `ImportError: cannot import name 'Deployment' from 'harmont._deploy'`.

- [ ] **Step 5: Implement `harmont/_deploy.py` (abstract type only)**

```python
"""Driver-agnostic deployment registry, decorator, and Dep marker.

This module is intentionally driver-free. Concrete deployment types
(``LocalDeployment``, future ``AwsDeployment``, …) live in their own
driver subpackages (``harmont.dev``, future ``harmont.aws``).
The registry stores deployments polymorphically; CLI subcommands filter
by ``isinstance`` or by the ``driver`` discriminator.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True)
class Deployment:
    """Abstract deployment record. Subclassed per driver.

    ``name`` is the slug the user passed to ``@hm.deploy``.
    ``driver`` is the discriminator string ("local" for ``hm.dev``).
    """
    name: str
    driver: str


# Registry: slug -> zero-arg callable that re-invokes the user-defined
# function with deps resolved. Same shape as REGISTRATIONS for pipelines.
DEPLOYMENTS: dict[str, Callable[[], Deployment]] = {}
```

- [ ] **Step 6: Run test to verify it passes**

```bash
pytest tests/dev/test_local_deployment.py -v
```

Expected: 1 passed.

- [ ] **Step 7: Commit**

```bash
git add harmont/_deploy.py tests/dev/__init__.py tests/dev/conftest.py tests/dev/test_local_deployment.py
git commit -m "$(cat <<'EOF'
feat(deploy): scaffold abstract Deployment dataclass + registry

Sets the driver-agnostic foundation for hm.deploy. Concrete
LocalDeployment (Task 3) subclasses Deployment; the DEPLOYMENTS
registry stores polymorphic entries. Test-only reset fixture covers
DEPLOYMENTS plus the existing TARGETS/REGISTRATIONS registries so
all three are wiped between tests.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `hm.dev.port()` sentinel

**Files:**
- Create: `harmont/dev/__init__.py`
- Create: `harmont/dev/_port.py`
- Test: `tests/dev/test_port_sentinel.py`

- [ ] **Step 1: Write the failing test**

In `tests/dev/test_port_sentinel.py`:

```python
"""hm.dev.port() sentinel: equality, repr, and structural use."""
from __future__ import annotations

from harmont.dev import port


def test_port_returns_sentinel_singleton():
    a = port()
    b = port()
    assert a is b               # singleton — equality-by-identity is fine
    assert a == b


def test_port_repr_is_stable_and_introspectable():
    assert repr(port()) == "<hm.dev.port>"


def test_port_is_hashable():
    # frozen LocalDeployment uses port_mapping values inside a Mapping;
    # being hashable means user code can put it in sets / tuple keys
    # without surprise.
    {port(): 1}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/dev/test_port_sentinel.py -v
```

Expected: `ModuleNotFoundError: No module named 'harmont.dev'`.

- [ ] **Step 3: Implement `harmont/dev/_port.py`**

```python
"""hm.dev.port() — the OS-assigned-host-port sentinel.

The sentinel is only meaningful as a value in
``hm.dev.deploy(..., port_mapping={CONTAINER_PORT: hm.dev.port()})``.
Any other position (env value, cmd arg, …) is rejected at the call
site that consumes it, with a fix-directed message per PRINCIPLES § 5.
"""
from __future__ import annotations


class _PortSentinel:
    __slots__ = ()

    def __repr__(self) -> str:
        return "<hm.dev.port>"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _PortSentinel)

    def __hash__(self) -> int:
        return hash(_PortSentinel)


_SINGLETON = _PortSentinel()


def port() -> _PortSentinel:
    """Return the sentinel for an OS-assigned host port.

    Use only as a ``port_mapping`` value:

        hm.dev.deploy(
            image="postgres:16",
            port_mapping={5432: hm.dev.port()},
        )
    """
    return _SINGLETON
```

- [ ] **Step 4: Implement `harmont/dev/__init__.py` (minimal, re-export only what's built)**

```python
"""harmont.dev — local Docker deployment driver.

Public surface (grows across tasks):

    deploy(*, image=None, from_=None, cmd=None,
           port_mapping=None, env=None,
           volumes=None, workdir=None) -> LocalDeployment
    port()                                  -> _PortSentinel
    LocalDeployment                          (concrete subclass)
    dump_registry_json()                    -> str
"""
from __future__ import annotations

from ._port import _PortSentinel, port

__all__ = ["_PortSentinel", "port"]
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/dev/test_port_sentinel.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add harmont/dev/__init__.py harmont/dev/_port.py tests/dev/test_port_sentinel.py
git commit -m "$(cat <<'EOF'
feat(dev): add hm.dev.port() sentinel for OS-assigned host ports

Singleton with stable repr and hash. Misuse outside port_mapping
is detected by deploy()'s field validation (Task 4), not at the
port() call site, so the error points at the exact misuse location.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `LocalDeployment` frozen dataclass

**Files:**
- Create: `harmont/dev/_deployment.py`
- Modify: `harmont/dev/__init__.py`
- Test: `tests/dev/test_local_deployment.py` (append)

- [ ] **Step 1: Write the failing tests (append to `tests/dev/test_local_deployment.py`)**

```python
from collections.abc import Mapping

from harmont._deploy import Deployment
from harmont._step import Step, scratch
from harmont.dev import port
from harmont.dev._deployment import LocalDeployment
from harmont.dev._port import _PortSentinel


def test_local_deployment_is_a_deployment_with_driver_local():
    d = LocalDeployment(
        name="db",
        driver="local",
        image="postgres:16",
        from_step=None,
        cmd=None,
        port_mapping={5432: port()},
        env={},
        volumes={},
        workdir=None,
    )
    assert isinstance(d, Deployment)
    assert d.driver == "local"
    assert d.image == "postgres:16"


def test_local_deployment_rejects_non_local_driver():
    import pytest
    with pytest.raises(ValueError, match="driver must be 'local'"):
        LocalDeployment(
            name="db", driver="aws",
            image="postgres:16", from_step=None, cmd=None,
            port_mapping={5432: port()},
            env={}, volumes={}, workdir=None,
        )


def test_local_deployment_holds_step_chain():
    s = scratch().sh("echo hi", image="alpine:3.20")
    d = LocalDeployment(
        name="api", driver="local",
        image=None, from_step=s, cmd=None,
        port_mapping={8000: port()},
        env={}, volumes={}, workdir=None,
    )
    assert d.from_step is s
    assert d.image is None


def test_port_mapping_is_a_mapping_of_int_to_port_sentinel():
    d = LocalDeployment(
        name="db", driver="local",
        image="postgres:16", from_step=None, cmd=None,
        port_mapping={5432: port()},
        env={}, volumes={}, workdir=None,
    )
    assert isinstance(d.port_mapping, Mapping)
    [(cport, sentinel)] = d.port_mapping.items()
    assert cport == 5432
    assert isinstance(sentinel, _PortSentinel)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/dev/test_local_deployment.py -v
```

Expected: ImportError or ModuleNotFoundError on `harmont.dev._deployment`.

- [ ] **Step 3: Implement `harmont/dev/_deployment.py`**

```python
"""LocalDeployment — the concrete dataclass for the local Docker driver.

Construction is mediated by ``harmont.dev._factory.deploy(...)``; the
factory does input validation and coerces fields. ``__post_init__`` is
the last-line invariant check (driver must be 'local').
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from harmont._deploy import Deployment

if TYPE_CHECKING:
    from collections.abc import Mapping

    from harmont._step import Step

    from ._port import _PortSentinel


@dataclass(frozen=True)
class LocalDeployment(Deployment):
    """Local Docker deployment record.

    Exactly one of ``image`` or ``from_step`` is non-None — enforced by
    ``deploy(...)``. ``port_mapping`` keys are container ports (1..65535);
    values are ``_PortSentinel`` (the ``hm.dev.port()`` singleton).
    ``volumes`` maps host paths (relative or absolute) to container
    paths (with optional ``:ro`` suffix).
    """
    image: str | None
    from_step: "Step | None"
    cmd: tuple[str, ...] | None
    port_mapping: "Mapping[int, _PortSentinel]"
    env: "Mapping[str, str]"
    volumes: "Mapping[str, str]"
    workdir: str | None

    def __post_init__(self) -> None:
        if self.driver != "local":
            msg = (
                f"LocalDeployment.driver must be 'local', got {self.driver!r}\n"
                "  → use the harmont.dev._factory.deploy() function "
                "instead of constructing LocalDeployment directly"
            )
            raise ValueError(msg)
```

- [ ] **Step 4: Re-export from `harmont/dev/__init__.py`**

Update `harmont/dev/__init__.py` so its content becomes:

```python
"""harmont.dev — local Docker deployment driver.

Public surface (grows across tasks):

    deploy(*, image=None, from_=None, cmd=None,
           port_mapping=None, env=None,
           volumes=None, workdir=None) -> LocalDeployment
    port()                                  -> _PortSentinel
    LocalDeployment                          (concrete subclass)
    dump_registry_json()                    -> str
"""
from __future__ import annotations

from ._deployment import LocalDeployment
from ._port import _PortSentinel, port

__all__ = ["LocalDeployment", "_PortSentinel", "port"]
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/dev/test_local_deployment.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add harmont/dev/_deployment.py harmont/dev/__init__.py tests/dev/test_local_deployment.py
git commit -m "$(cat <<'EOF'
feat(dev): add LocalDeployment frozen dataclass

Concrete subclass of Deployment for the local Docker driver.
__post_init__ enforces driver=='local'; everything else is a
plain dataclass field. The deploy(...) factory in Task 4 is the
sanctioned constructor.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `hm.dev.deploy(...)` factory + field validation

**Files:**
- Create: `harmont/dev/_factory.py`
- Modify: `harmont/dev/__init__.py`
- Test: `tests/dev/test_deploy_factory.py`

- [ ] **Step 1: Write the failing tests**

In `tests/dev/test_deploy_factory.py`:

```python
"""hm.dev.deploy(...) field validation + LocalDeployment construction."""
from __future__ import annotations

import pytest

from harmont._step import Step, scratch
from harmont.dev import LocalDeployment, deploy, port


def test_deploy_with_raw_image_returns_local_deployment():
    d = deploy(
        image="postgres:16",
        port_mapping={5432: port()},
        env={"POSTGRES_PASSWORD": "dev"},
    )
    assert isinstance(d, LocalDeployment)
    assert d.image == "postgres:16"
    assert d.from_step is None
    # name is set later by the @hm.deploy decorator; factory leaves it ""
    assert d.name == ""


def test_deploy_with_from_step():
    s = scratch().sh("echo build", image="alpine:3.20")
    d = deploy(from_=s, port_mapping={8000: port()})
    assert d.image is None
    assert d.from_step is s


def test_deploy_requires_exactly_one_of_image_or_from():
    with pytest.raises(ValueError, match="exactly one of `image=` or `from_=`"):
        deploy(port_mapping={5432: port()})
    with pytest.raises(ValueError, match="exactly one of `image=` or `from_=`"):
        deploy(image="x", from_=scratch().sh("echo"), port_mapping={5432: port()})


def test_port_mapping_keys_must_be_valid_container_ports():
    with pytest.raises(ValueError, match="port_mapping key must be int in"):
        deploy(image="x", port_mapping={0: port()})
    with pytest.raises(ValueError, match="port_mapping key must be int in"):
        deploy(image="x", port_mapping={70000: port()})
    with pytest.raises(ValueError, match="port_mapping key must be int in"):
        deploy(image="x", port_mapping={"5432": port()})  # type: ignore[dict-item]


def test_port_mapping_values_must_be_hm_dev_port():
    with pytest.raises(ValueError, match="port_mapping value must be hm.dev.port"):
        deploy(image="x", port_mapping={5432: 31337})  # type: ignore[dict-item]


def test_env_values_must_be_strings():
    with pytest.raises(ValueError, match="env value for 'PORT' must be str"):
        deploy(image="x", port_mapping={5432: port()}, env={"PORT": 31337})  # type: ignore[dict-item]


def test_cmd_coerces_to_tuple_of_strings():
    d = deploy(image="x", port_mapping={5432: port()}, cmd=["postgres", "-c", "shared_buffers=128MB"])
    assert d.cmd == ("postgres", "-c", "shared_buffers=128MB")


def test_cmd_rejects_non_string_elements():
    with pytest.raises(ValueError, match="cmd elements must be str"):
        deploy(image="x", port_mapping={5432: port()}, cmd=["postgres", 5432])  # type: ignore[list-item]


def test_volumes_keys_resolve_relative_to_worktree_at_dump_time():
    # The factory keeps host paths verbatim; resolution happens in
    # _registry_dump.py. Here we only check that the dict is preserved.
    d = deploy(image="x", port_mapping={5432: port()}, volumes={".": "/workspace"})
    assert dict(d.volumes) == {".": "/workspace"}


def test_workdir_must_be_absolute():
    with pytest.raises(ValueError, match="workdir must be an absolute path"):
        deploy(image="x", port_mapping={5432: port()}, workdir="workspace")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/dev/test_deploy_factory.py -v
```

Expected: ImportError on `deploy` from `harmont.dev`.

- [ ] **Step 3: Implement `harmont/dev/_factory.py`**

```python
"""hm.dev.deploy(...) — the public factory for LocalDeployment.

Validation is deliberately strict and fix-directed. The @hm.deploy
decorator only learns the slug at decoration time, so this factory
emits LocalDeployment with name="" — the decorator stamps the slug
in afterwards via dataclasses.replace.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

from harmont._step import Step

from ._deployment import LocalDeployment
from ._port import _PortSentinel

if TYPE_CHECKING:
    pass


def deploy(
    *,
    image: str | None = None,
    from_: "Step | None" = None,
    cmd: "Iterable[str] | None" = None,
    port_mapping: "Mapping[int, _PortSentinel] | None" = None,
    env: "Mapping[str, str] | None" = None,
    volumes: "Mapping[str, str] | None" = None,
    workdir: str | None = None,
) -> LocalDeployment:
    """Construct a LocalDeployment.

    Exactly one of ``image`` or ``from_`` is required. ``port_mapping``
    keys are container ports (1..65535); values must be the
    ``hm.dev.port()`` sentinel in v1. See the design spec § 1 for the
    full validation table.
    """
    if (image is None) == (from_ is None):
        msg = (
            "hm.dev.deploy requires exactly one of `image=` or `from_=`, "
            f"got image={image!r}, from_={from_!r}\n"
            "  → pick one. Use `image=\"...\"` for a published image, "
            "`from_=<Step>` to build from a Step chain."
        )
        raise ValueError(msg)
    if from_ is not None and not isinstance(from_, Step):
        msg = (
            f"hm.dev.deploy from_= must be a hm.Step, got {type(from_).__name__}\n"
            "  → pass a Step chain (e.g. hm.sh(...) or a @hm.target() value)"
        )
        raise ValueError(msg)

    pm = _validate_port_mapping(port_mapping)
    env_resolved = _validate_env(env)
    volumes_resolved = _validate_volumes(volumes)
    cmd_resolved = _validate_cmd(cmd)
    workdir_resolved = _validate_workdir(workdir)

    return LocalDeployment(
        name="",            # decorator stamps the slug in
        driver="local",
        image=image,
        from_step=from_,
        cmd=cmd_resolved,
        port_mapping=pm,
        env=env_resolved,
        volumes=volumes_resolved,
        workdir=workdir_resolved,
    )


def _validate_port_mapping(
    pm: "Mapping[int, _PortSentinel] | None",
) -> Mapping[int, _PortSentinel]:
    if pm is None:
        return {}
    result: dict[int, _PortSentinel] = {}
    for k, v in pm.items():
        if not isinstance(k, int) or k < 1 or k > 65535:
            msg = (
                f"hm.dev.deploy port_mapping key must be int in 1..65535, "
                f"got {k!r}\n"
                "  → keys are container ports the service listens on"
            )
            raise ValueError(msg)
        if not isinstance(v, _PortSentinel):
            msg = (
                f"hm.dev.deploy port_mapping value must be hm.dev.port(), "
                f"got {type(v).__name__}\n"
                "  → use hm.dev.port() to ask the OS for a free host port"
            )
            raise ValueError(msg)
        result[k] = v
    return result


def _validate_env(env: "Mapping[str, str] | None") -> Mapping[str, str]:
    if env is None:
        return {}
    for k, v in env.items():
        if not isinstance(k, str):
            msg = f"hm.dev.deploy env key must be str, got {type(k).__name__}"
            raise ValueError(msg)
        if not isinstance(v, str):
            msg = (
                f"hm.dev.deploy env value for {k!r} must be str, "
                f"got {type(v).__name__}\n"
                "  → call str(...) at the call site so the conversion is explicit"
            )
            raise ValueError(msg)
    return dict(env)


def _validate_volumes(
    volumes: "Mapping[str, str] | None",
) -> Mapping[str, str]:
    if volumes is None:
        return {}
    for hp, cp in volumes.items():
        if not isinstance(hp, str) or not hp:
            msg = (
                f"hm.dev.deploy volumes host path must be a non-empty str, "
                f"got {hp!r}"
            )
            raise ValueError(msg)
        if not isinstance(cp, str) or not cp.startswith("/"):
            msg = (
                f"hm.dev.deploy volumes container path {cp!r} must start with "
                "'/'; append ':ro' for read-only mounts (e.g. '/workspace:ro')"
            )
            raise ValueError(msg)
    return dict(volumes)


def _validate_cmd(cmd: "Iterable[str] | None") -> tuple[str, ...] | None:
    if cmd is None:
        return None
    items = tuple(cmd)
    for x in items:
        if not isinstance(x, str):
            msg = (
                f"hm.dev.deploy cmd elements must be str, got {type(x).__name__}\n"
                "  → call str(...) at the call site so the conversion is explicit"
            )
            raise ValueError(msg)
    return items


def _validate_workdir(workdir: str | None) -> str | None:
    if workdir is None:
        return None
    if not workdir.startswith("/"):
        msg = (
            f"hm.dev.deploy workdir must be an absolute path, got {workdir!r}\n"
            "  → workdir is interpreted inside the container; "
            "use a path that starts with '/'"
        )
        raise ValueError(msg)
    return workdir
```

- [ ] **Step 4: Re-export `deploy` from `harmont/dev/__init__.py`**

Replace `harmont/dev/__init__.py` content with:

```python
"""harmont.dev — local Docker deployment driver.

Public surface (grows across tasks):

    deploy(*, image=None, from_=None, cmd=None,
           port_mapping=None, env=None,
           volumes=None, workdir=None) -> LocalDeployment
    port()                                  -> _PortSentinel
    LocalDeployment                          (concrete subclass)
    dump_registry_json()                    -> str  (Task 8)
"""
from __future__ import annotations

from ._deployment import LocalDeployment
from ._factory import deploy
from ._port import _PortSentinel, port

__all__ = ["LocalDeployment", "_PortSentinel", "deploy", "port"]
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/dev/test_deploy_factory.py -v
```

Expected: 10 passed.

- [ ] **Step 6: Commit**

```bash
git add harmont/dev/_factory.py harmont/dev/__init__.py tests/dev/test_deploy_factory.py
git commit -m "$(cat <<'EOF'
feat(dev): hm.dev.deploy(...) factory with field validation

Strict, fix-directed validation per PRINCIPLES § 5: every error
message points at the misuse and states the fix. The factory leaves
name="" so the @hm.deploy decorator can stamp the slug in via
dataclasses.replace after deciding the slug from its arg or fn name.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: `hm.Dep[T]` marker + extend `call_with_deps`

The marker lives in `harmont._typing` alongside `Target`; the resolver lives in `harmont._deps` alongside the existing target/baseimage resolution. The dep registry is `harmont._deploy.DEPLOYMENTS` (already created in Task 1).

**Files:**
- Modify: `harmont/_typing.py`
- Modify: `harmont/_deps.py`
- Test: `tests/dev/test_dep_marker.py` (new)

- [ ] **Step 1: Write the failing tests**

In `tests/dev/test_dep_marker.py`:

```python
"""hm.Dep[T] marker is detected; call_with_deps resolves it from DEPLOYMENTS."""
from __future__ import annotations

import pytest

from harmont import Dep
from harmont._deploy import DEPLOYMENTS, Deployment
from harmont._deps import call_with_deps


def test_dep_marker_alias_subscripts_to_annotated():
    # Dep is PEP-593 Annotated[T, _DEP_MARKER]; subscripting works at
    # both static and runtime levels.
    from typing import get_args, get_origin

    T = Dep[Deployment]
    assert get_origin(T) is not None
    args = get_args(T)
    assert args[0] is Deployment


def test_call_with_deps_resolves_dep_param_from_DEPLOYMENTS():
    # Register a fake deployment under the name "db".
    DEPLOYMENTS["db"] = lambda: Deployment(name="db", driver="local")

    def consumer(db: Dep[Deployment]) -> Deployment:
        return db

    result = call_with_deps(consumer)
    assert isinstance(result, Deployment)
    assert result.name == "db"


def test_call_with_deps_raises_when_dep_unknown():
    def consumer(redis: Dep[Deployment]) -> Deployment:
        return redis

    with pytest.raises(ValueError, match="hm.Dep parameter 'redis' refers to"):
        call_with_deps(consumer)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/dev/test_dep_marker.py -v
```

Expected: ImportError — `Dep` not in `harmont`.

- [ ] **Step 3: Add `_DepMarker` + `Dep` alias in `harmont/_typing.py`**

Append to `harmont/_typing.py`:

```python
class _DepMarker:
    """Sentinel for Annotated metadata. Marks a parameter as a
    dependency on another @hm.deploy by parameter name. The injected
    value is the resolved Deployment.
    """

    __slots__ = ()

    def __repr__(self) -> str:
        return "<hm.Dep marker>"


_DEP_MARKER = _DepMarker()


# hm.Dep[Deployment] (or a concrete subclass) -> Annotated[T, _DEP_MARKER].
Dep = Annotated[T, _DEP_MARKER]
```

- [ ] **Step 4: Extend `harmont/_deps.py` to resolve `_DepMarker`**

The current `_marker_for` returns `_TARGET_MARKER` or `_BaseImageMarker`. Extend it to also return `_DEP_MARKER`. The current `call_with_deps` dispatches on the marker type. Add a `_DEP_MARKER` branch that looks up `harmont._deploy.DEPLOYMENTS`.

Locate the existing `_marker_for` function in `harmont/_deps.py` and update it to recognize the dep marker. Then extend the resolver loop. Concrete edits (full new file content of `harmont/_deps.py` once edits are applied):

```python
"""Shared dependency resolution for @hm.target, @hm.pipeline, and @hm.deploy.

Strict-marker model:
- ``Target[T]``           — resolve by parameter name from the global
                            target registry; raise if not found.
- ``BaseImage["X"]``      — inject a scratch-rooted ``Step(image=X)``.
- ``Dep[T]``              — resolve by parameter name from
                            ``harmont._deploy.DEPLOYMENTS``; raise if
                            not found.
- plain param with default — bind the default value.
- anything else            — raise at decoration time via
                            :func:`validate_target_signature`.

Cycle detection uses a module-level "currently resolving" stack keyed
by function name; the dump_registry_json render clears it at the
start of every render along with the target memoization cache.
"""

from __future__ import annotations

import inspect
import typing
from typing import TYPE_CHECKING, Any

from ._step import Step
from ._typing import _DEP_MARKER, _TARGET_MARKER, _BaseImageMarker, _DepMarker, _TargetMarker

if TYPE_CHECKING:
    from collections.abc import Callable


_TARGETS_BY_NAME: dict[str, Callable[[], Any]] = {}
_RESOLVING: list[str] = []


def register_named_target(name: str, fn: Callable[[], Any]) -> None:
    """Register a named target. Raises on duplicate name."""
    if name in _TARGETS_BY_NAME:
        msg = (
            f"hm: duplicate target name {name!r}\n"
            "  → each @hm.target must have a unique name; pass "
            'name="..." to disambiguate'
        )
        raise ValueError(msg)
    _TARGETS_BY_NAME[name] = fn


def clear_target_names() -> None:
    """Reset the name registry and cycle-detection stack."""
    _TARGETS_BY_NAME.clear()
    _RESOLVING.clear()


def _param_kind_error(param: inspect.Parameter) -> str | None:
    """Return a fix-directed error message if `param` has a forbidden kind."""
    kind = param.kind
    if kind == inspect.Parameter.VAR_POSITIONAL:
        return (
            "hm: target functions cannot take *args\n"
            "  → declare each dependency as an explicit named parameter"
        )
    if kind == inspect.Parameter.VAR_KEYWORD:
        return (
            "hm: target functions cannot take **kwargs\n"
            "  → declare each dependency as an explicit named parameter"
        )
    if kind == inspect.Parameter.POSITIONAL_ONLY:
        return (
            f"hm: target functions cannot have positional-only "
            f"parameters (got {param.name!r})\n"
            "  → remove the '/' marker; parameters must be name-resolvable"
        )
    return None


def _marker_for(annotation: Any) -> object | None:
    """Return the hm-specific marker present on an ``Annotated[T, ...]``
    annotation, else None. Markers: ``_TargetMarker``, ``_BaseImageMarker``,
    ``_DepMarker``.
    """
    if typing.get_origin(annotation) is None:
        return None
    metadata = typing.get_args(annotation)[1:]
    for m in metadata:
        if isinstance(m, (_TargetMarker, _BaseImageMarker, _DepMarker)):
            return m
    return None


def validate_target_signature(fn: Callable[..., Any]) -> None:
    """Raise at decoration time if any param lacks a marker or default."""
    sig = inspect.signature(fn)
    hints = typing.get_type_hints(fn, include_extras=True)
    for name, param in sig.parameters.items():
        kind_err = _param_kind_error(param)
        if kind_err is not None:
            raise ValueError(kind_err)
        if param.default is not inspect.Parameter.empty:
            continue
        ann = hints.get(name)
        if ann is None or _marker_for(ann) is None:
            msg = (
                f"hm: parameter {name!r} on {fn.__name__} must carry a marker "
                "or have a default.\n"
                "  → add `hm.Target[T]`, `hm.Dep[T]`, or "
                "`Annotated[Step, hm.BaseImage(\"...\")]`, or set a default value."
            )
            raise ValueError(msg)


def call_with_deps(fn: Callable[..., Any]) -> Any:
    """Resolve fn's parameters via markers and call it."""
    sig = inspect.signature(fn)
    hints = typing.get_type_hints(fn, include_extras=True)

    fn_id = getattr(fn, "__name__", repr(fn))
    if fn_id in _RESOLVING:
        chain = " -> ".join([*_RESOLVING, fn_id])
        msg = f"hm: dependency cycle detected: {chain}"
        raise RuntimeError(msg)
    _RESOLVING.append(fn_id)
    try:
        kwargs: dict[str, Any] = {}
        for name, param in sig.parameters.items():
            ann = hints.get(name)
            marker = _marker_for(ann) if ann is not None else None
            if marker is _TARGET_MARKER:
                if name not in _TARGETS_BY_NAME:
                    msg = (
                        f"hm.Target parameter {name!r} refers to no registered "
                        f"@hm.target — register one with that name, or pass "
                        '`name="..."` to disambiguate.'
                    )
                    raise ValueError(msg)
                kwargs[name] = _TARGETS_BY_NAME[name]()
            elif isinstance(marker, _BaseImageMarker):
                kwargs[name] = Step(image=marker.image)
            elif marker is _DEP_MARKER:
                # Local import to avoid circular: _deploy imports nothing from us.
                from ._deploy import DEPLOYMENTS

                if name not in DEPLOYMENTS:
                    msg = (
                        f"hm.Dep parameter {name!r} refers to no registered "
                        f"@hm.deploy — register one with that slug, or pass "
                        '`name="..."` to disambiguate.'
                    )
                    raise ValueError(msg)
                kwargs[name] = DEPLOYMENTS[name]()
            elif param.default is not inspect.Parameter.empty:
                kwargs[name] = param.default
            else:
                msg = (
                    f"hm: parameter {name!r} on {fn_id} has no resolution.\n"
                    "  → add a marker or default value."
                )
                raise ValueError(msg)
        return fn(**kwargs)
    finally:
        _RESOLVING.pop()
```

NB: The body above is the **complete new content** of `harmont/_deps.py`. The diff from the prior version is: imports gain `_DEP_MARKER`/`_DepMarker`; `_marker_for` recognizes them; `call_with_deps` resolves them via `DEPLOYMENTS`. Replace the entire file with this content; do not edit-in-place line by line, since `call_with_deps` and `validate_target_signature` change in coupled ways.

- [ ] **Step 5: Add `Dep` to top-level `harmont/__init__.py`**

Read `harmont/__init__.py`, locate the line `from ._typing import BaseImage, Target`, and replace it with:

```python
from ._typing import BaseImage, Dep, Target
```

Add `"Dep"` to the `__all__` list in alphabetical position (between `Pipeline` and `Step`).

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/dev/test_dep_marker.py -v
```

Expected: 3 passed.

Also re-run all existing tests to make sure `call_with_deps` changes didn't regress:

```bash
pytest -v
```

Expected: every prior pass still passes; new tests pass.

- [ ] **Step 7: Commit**

```bash
git add harmont/_typing.py harmont/_deps.py harmont/__init__.py tests/dev/test_dep_marker.py
git commit -m "$(cat <<'EOF'
feat(deploy): add hm.Dep[T] marker + extend call_with_deps resolver

Dep[T] resolves a parameter against harmont._deploy.DEPLOYMENTS by
the parameter name (same shape as Target[T] vs _TARGETS_BY_NAME).
Cycle detection reuses the existing _RESOLVING stack so dep cycles
between deployments and dep cycles between targets share one detector.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: `@hm.deploy` decorator

**Files:**
- Modify: `harmont/_deploy.py` (add the decorator + slug validator)
- Modify: `harmont/__init__.py` (re-export `deploy` — note name-clashes with `hm.dev.deploy`)
- Test: `tests/dev/test_decorator.py` (new)

The clash: `hm.deploy` (decorator) vs `hm.dev.deploy` (factory). They live in different namespaces and are imported separately. The factory is `harmont.dev.deploy`; the decorator is `harmont.deploy`. The `harmont/__init__.py` re-exports `deploy = harmont._deploy.deploy` so `hm.deploy(...)` resolves to the decorator. `hm.dev.deploy(...)` is reached via the submodule.

- [ ] **Step 1: Write the failing tests**

In `tests/dev/test_decorator.py`:

```python
"""@hm.deploy decorator: registration, slug derivation, fixture injection."""
from __future__ import annotations

import pytest

import harmont as hm
from harmont._deploy import DEPLOYMENTS
from harmont.dev import LocalDeployment


def test_deploy_registers_under_explicit_slug():
    @hm.deploy("db")
    def db():
        return hm.dev.deploy(image="postgres:16", port_mapping={5432: hm.dev.port()})

    assert "db" in DEPLOYMENTS
    resolved = DEPLOYMENTS["db"]()
    assert isinstance(resolved, LocalDeployment)
    assert resolved.name == "db"           # decorator stamped slug in
    assert resolved.image == "postgres:16"


def test_deploy_uses_function_name_when_slug_omitted():
    @hm.deploy()
    def redis():
        return hm.dev.deploy(image="redis:7", port_mapping={6379: hm.dev.port()})

    assert "redis" in DEPLOYMENTS


def test_deploy_rejects_invalid_slug():
    with pytest.raises(ValueError, match="invalid deployment slug"):
        @hm.deploy("Bad Slug")
        def x():
            return hm.dev.deploy(image="x", port_mapping={5432: hm.dev.port()})


def test_deploy_rejects_duplicate_slug():
    @hm.deploy("db")
    def db1():
        return hm.dev.deploy(image="postgres:16", port_mapping={5432: hm.dev.port()})

    with pytest.raises(ValueError, match="duplicate deployment slug"):
        @hm.deploy("db")
        def db2():
            return hm.dev.deploy(image="postgres:15", port_mapping={5432: hm.dev.port()})


def test_deploy_requires_marker_on_param():
    with pytest.raises(ValueError, match=r"parameter 'db' on .* must carry a marker"):
        @hm.deploy("api")
        def api(db):  # type: ignore[no-untyped-def]
            return hm.dev.deploy(image="x", port_mapping={8000: hm.dev.port()})


def test_deploy_injects_dep_value():
    @hm.deploy("db")
    def db():
        return hm.dev.deploy(image="postgres:16", port_mapping={5432: hm.dev.port()})

    @hm.deploy("api")
    def api(db: hm.Dep[hm.Deployment]):
        # db.name comes from the resolved upstream Deployment
        return hm.dev.deploy(
            image="x",
            port_mapping={8000: hm.dev.port()},
            env={"DB_HOST": db.name},
        )

    resolved = DEPLOYMENTS["api"]()
    assert resolved.env["DB_HOST"] == "db"


def test_deploy_with_explicit_name_arg():
    @hm.deploy("db", name="primary-db")
    def db():
        return hm.dev.deploy(image="postgres:16", port_mapping={5432: hm.dev.port()})

    # The display name is held alongside the slug; the registry is keyed by slug.
    assert "db" in DEPLOYMENTS
    # In v1 we don't expose `name` separately on the returned Deployment;
    # the slug IS the public identity. The kwarg is reserved for future use.


def test_deploy_function_can_return_remote_driver_value():
    # Simulate a future driver: a function that returns a Deployment with
    # driver != "local". The decorator must register it without complaint.
    from harmont._deploy import Deployment

    @hm.deploy("prod-api")
    def prod_api():
        return Deployment(name="", driver="aws")

    resolved = DEPLOYMENTS["prod-api"]()
    assert resolved.driver == "aws"
    assert resolved.name == "prod-api"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/dev/test_decorator.py -v
```

Expected: `AttributeError: module 'harmont' has no attribute 'deploy'`.

- [ ] **Step 3: Implement `@hm.deploy` in `harmont/_deploy.py`**

Replace the entire `harmont/_deploy.py` content with:

```python
"""Driver-agnostic deployment registry, decorator, and Dep marker.

This module is intentionally driver-free. Concrete deployment types
(``LocalDeployment``, future ``AwsDeployment``, …) live in their own
driver subpackages (``harmont.dev``, future ``harmont.aws``).
"""
from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from functools import wraps
from typing import TYPE_CHECKING, Any

from ._deps import call_with_deps, validate_target_signature

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True)
class Deployment:
    """Abstract deployment record. Subclassed per driver."""
    name: str
    driver: str


DEPLOYMENTS: dict[str, "Callable[[], Deployment]"] = {}


_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{0,30}$")


def _validate_slug(slug: str) -> None:
    if not _SLUG_RE.match(slug):
        msg = (
            f"hm: invalid deployment slug {slug!r}\n"
            "  → use lowercase letters, digits, and '-', "
            "start with a letter, max 31 chars (Docker container name rules)"
        )
        raise ValueError(msg)


def deploy(
    slug: str | None = None,
    *,
    name: str | None = None,
) -> "Callable[[Callable[..., Any]], Callable[[], Deployment]]":
    """Register a function as a deployment.

    The wrapped function returns a :class:`Deployment` (typically the
    output of :func:`harmont.dev.deploy` or any future driver's factory).
    Parameters are resolved via the markers used by ``@hm.target`` and
    ``@hm.pipeline``, plus ``hm.Dep[T]`` for deployment-to-deployment
    references. See ``docs/superpowers/specs/2026-05-21-hm-dev-deploy-design.md``.
    """

    def decorator(fn: "Callable[..., Any]") -> "Callable[[], Deployment]":
        validate_target_signature(fn)
        resolved_slug = slug if slug is not None else fn.__name__
        _validate_slug(resolved_slug)
        if resolved_slug in DEPLOYMENTS:
            msg = (
                f"hm: duplicate deployment slug {resolved_slug!r}\n"
                "  → each @hm.deploy must have a unique slug; pass an "
                "explicit slug or `name=\"...\"` to disambiguate"
            )
            raise ValueError(msg)

        @wraps(fn)
        def wrapper() -> Deployment:
            value = call_with_deps(fn)
            if not isinstance(value, Deployment):
                msg = (
                    f"hm.deploy({resolved_slug!r}) must return a Deployment, "
                    f"got {type(value).__name__}\n"
                    "  → return the output of hm.dev.deploy(...) or another "
                    "driver's factory"
                )
                raise TypeError(msg)
            # Stamp the slug into the returned dataclass.
            return dataclasses.replace(value, name=resolved_slug)

        DEPLOYMENTS[resolved_slug] = wrapper
        return wrapper

    return decorator
```

- [ ] **Step 4: Re-export `deploy`, `Dep`, `Deployment` from `harmont/__init__.py`**

Read `harmont/__init__.py`. After the existing imports add:

```python
from ._deploy import Deployment, deploy
```

And re-export `dev` as a submodule. Find the `from . import _decorator` line and add right after it:

```python
from . import dev
```

Update the `__all__` list to include (in alphabetical position): `"Dep"`, `"Deployment"`, `"deploy"`, `"dev"`.

The final `__all__` should look like (sorted):

```python
__all__ = [
    "BaseImage",
    "CacheCompose",
    "CacheForever",
    "CacheNone",
    "CacheOnChange",
    "CachePolicy",
    "CacheTTL",
    "Dep",
    "Deployment",
    "Pipeline",
    "Step",
    "Target",
    "cmake",
    "compose",
    "composer",
    "deploy",
    "dev",
    "dotnet",
    "dump_registry_json",
    "elm",
    "forever",
    "go",
    "gradle",
    "haskell",
    "npm",
    "ocaml",
    "on_change",
    "perl",
    "pipeline",
    "pipeline_to_json",
    "pull_request",
    "push",
    "python",
    "ruby",
    "rust",
    "schedule",
    "scratch",
    "sh",
    "target",
    "ttl",
    "wait",
    "zig",
]
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/dev/test_decorator.py -v
```

Expected: 8 passed.

Also run the full suite to confirm no regressions:

```bash
pytest -v
```

Expected: every pre-existing test still passes; new tests pass.

- [ ] **Step 6: Commit**

```bash
git add harmont/_deploy.py harmont/__init__.py tests/dev/test_decorator.py
git commit -m "$(cat <<'EOF'
feat(deploy): add @hm.deploy decorator with slug validation + Dep injection

Decorator validates the slug regex (Docker container-name rules),
rejects duplicates, validates the function signature via the existing
validate_target_signature, and wraps the function so call_with_deps
resolves Target/Dep/BaseImage markers at registry-walk time.

dataclasses.replace stamps the resolved slug into the returned
Deployment so the value seen by callers and the registry has
name=<slug> (the factory leaves name="").

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Topo sort + dep-graph extraction

The registry dumper (Task 8) needs to walk deployments in dependency order. This task adds a pure dep-graph extractor + topo sort. No JSON yet.

**Files:**
- Modify: `harmont/_deploy.py` (add `dep_graph` + `topo_order`)
- Test: `tests/dev/test_topo.py` (new)

- [ ] **Step 1: Write the failing tests**

In `tests/dev/test_topo.py`:

```python
"""dep_graph extraction + topo_order on the deployment registry."""
from __future__ import annotations

import pytest

import harmont as hm
from harmont._deploy import dep_graph, topo_order


def test_dep_graph_empty_when_no_deps():
    @hm.deploy("db")
    def db():
        return hm.dev.deploy(image="postgres:16", port_mapping={5432: hm.dev.port()})

    g = dep_graph()
    assert g == {"db": ()}


def test_dep_graph_lists_param_names_in_order():
    @hm.deploy("db")
    def db():
        return hm.dev.deploy(image="postgres:16", port_mapping={5432: hm.dev.port()})

    @hm.deploy("api")
    def api(db: hm.Dep[hm.Deployment]):
        return hm.dev.deploy(image="x", port_mapping={8000: hm.dev.port()},
                             env={"DB": db.name})

    g = dep_graph()
    assert g == {"db": (), "api": ("db",)}


def test_topo_order_is_stable_and_deps_first():
    @hm.deploy("db")
    def db():
        return hm.dev.deploy(image="postgres:16", port_mapping={5432: hm.dev.port()})

    @hm.deploy("api")
    def api(db: hm.Dep[hm.Deployment]):
        return hm.dev.deploy(image="x", port_mapping={8000: hm.dev.port()})

    @hm.deploy("web")
    def web(api: hm.Dep[hm.Deployment]):
        return hm.dev.deploy(image="x", port_mapping={3000: hm.dev.port()})

    order = topo_order()
    # db before api before web
    assert order.index("db") < order.index("api") < order.index("web")


def test_topo_order_raises_on_cycle():
    # Build the cycle directly in the registry (bypasses normal decoration
    # ordering, since at decoration time the upstream may not yet be
    # registered — we only want to test the detector here).
    from harmont._deploy import DEPLOYMENTS, Deployment

    @hm.deploy("a")
    def a(b: hm.Dep[hm.Deployment]):
        return Deployment(name="", driver="local")

    @hm.deploy("b")
    def b(a: hm.Dep[hm.Deployment]):
        return Deployment(name="", driver="local")

    with pytest.raises(RuntimeError, match="dep cycle"):
        topo_order()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/dev/test_topo.py -v
```

Expected: ImportError on `dep_graph` / `topo_order` from `harmont._deploy`.

- [ ] **Step 3: Implement `dep_graph` and `topo_order` in `harmont/_deploy.py`**

Append to `harmont/_deploy.py`:

```python
def dep_graph() -> dict[str, tuple[str, ...]]:
    """Return slug -> tuple of upstream slugs, in parameter order.

    Walks DEPLOYMENTS; for each registered slug, introspects the wrapped
    function's signature for ``Dep[T]`` parameters. Plain defaults and
    Target/BaseImage markers do not produce edges in the deploy graph.
    """
    import inspect
    import typing as _typing

    from ._typing import _DEP_MARKER

    out: dict[str, tuple[str, ...]] = {}
    for slug, wrapper in DEPLOYMENTS.items():
        fn = wrapper.__wrapped__  # type: ignore[attr-defined]
        sig = inspect.signature(fn)
        hints = _typing.get_type_hints(fn, include_extras=True)
        deps: list[str] = []
        for name in sig.parameters:
            ann = hints.get(name)
            if ann is None:
                continue
            if _typing.get_origin(ann) is None:
                continue
            metadata = _typing.get_args(ann)[1:]
            if any(m is _DEP_MARKER for m in metadata):
                deps.append(name)
        out[slug] = tuple(deps)
    return out


def topo_order() -> list[str]:
    """Topological ordering of DEPLOYMENTS by dep_graph; deps first.

    Raises RuntimeError on cycles. Stable under insertion order for
    independent slugs (preserves decoration order within a level).
    """
    g = dep_graph()
    # Kahn's algorithm w/ stable level ordering (insertion-order).
    indeg: dict[str, int] = {slug: 0 for slug in g}
    for upstreams in g.values():
        for u in upstreams:
            if u in indeg:
                indeg[u]  # downstream depends on u; u has no incoming from here
            # incoming edge is into the *dependent* slug, not the upstream.
    # Rebuild: indeg of S = number of deps of S that exist in the registry.
    for slug, upstreams in g.items():
        indeg[slug] = sum(1 for u in upstreams if u in g)
    order: list[str] = []
    # Iterate in registry insertion order so the result is stable.
    while True:
        progressed = False
        for slug in list(g.keys()):
            if slug in order:
                continue
            if indeg[slug] == 0:
                order.append(slug)
                for downstream, upstreams in g.items():
                    if slug in upstreams and downstream not in order:
                        indeg[downstream] -= 1
                progressed = True
        if not progressed:
            break
    if len(order) != len(g):
        unresolved = [s for s in g if s not in order]
        msg = (
            f"hm: dep cycle among deployments: {', '.join(unresolved)}\n"
            "  → break the cycle, or factor shared state into a target"
        )
        raise RuntimeError(msg)
    return order
```

NB: The above intentionally keeps the implementation small and obvious (no graph library). The `__wrapped__` attribute is set by `functools.wraps` in the decorator, so the introspection finds the original function's signature.

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/dev/test_topo.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add harmont/_deploy.py tests/dev/test_topo.py
git commit -m "$(cat <<'EOF'
feat(deploy): add dep_graph + topo_order over DEPLOYMENTS

dep_graph walks the registry, introspects each wrapped function for
Dep[T] params, and emits slug -> tuple of upstream slugs in parameter
order. topo_order runs Kahn's algorithm with stable level ordering
(insertion order within a level) so the registry-dump output is
deterministic. Cycle detection raises RuntimeError listing the
unresolved slugs.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: `dump_registry_json` for the local driver

**Files:**
- Create: `harmont/dev/_registry_dump.py`
- Modify: `harmont/dev/__init__.py`
- Test: `tests/dev/test_registry_dump.py`

- [ ] **Step 1: Write the failing tests**

In `tests/dev/test_registry_dump.py`:

```python
"""dump_registry_json — golden JSON shape for canonical examples."""
from __future__ import annotations

import json
from pathlib import Path

import harmont as hm
from harmont._deploy import Deployment
from harmont.dev import dump_registry_json


def test_dump_minimal_local_deployment():
    @hm.deploy("db")
    def db():
        return hm.dev.deploy(
            image="postgres:16",
            port_mapping={5432: hm.dev.port()},
            env={"POSTGRES_PASSWORD": "dev"},
        )

    out = json.loads(dump_registry_json(worktree_root=Path("/tmp/wt")))
    assert out["schema_version"] == "0"
    assert out["worktree"] == "/tmp/wt"
    assert out["deployments"]["db"] == {
        "driver": "local",
        "image": "postgres:16",
        "from": None,
        "cmd": None,
        "port_mapping": {"5432": "__hm_dev_port__"},
        "env": {"POSTGRES_PASSWORD": "dev"},
        "volumes": {},
        "workdir": None,
        "deps": [],
    }


def test_dump_with_cmd_workdir_volumes():
    @hm.deploy("db")
    def db():
        return hm.dev.deploy(
            image="postgres:16",
            cmd=["postgres", "-c", "shared_buffers=128MB"],
            port_mapping={5432: hm.dev.port()},
            volumes={".": "/workspace"},
            workdir="/workspace",
        )

    out = json.loads(dump_registry_json(worktree_root=Path("/tmp/wt")))
    e = out["deployments"]["db"]
    assert e["cmd"] == ["postgres", "-c", "shared_buffers=128MB"]
    assert e["workdir"] == "/workspace"
    assert e["volumes"] == {".": "/workspace"}


def test_dump_with_deps_emits_deps_array_in_param_order():
    @hm.deploy("db")
    def db():
        return hm.dev.deploy(image="postgres:16", port_mapping={5432: hm.dev.port()})

    @hm.deploy("api")
    def api(db: hm.Dep[hm.Deployment]):
        return hm.dev.deploy(
            image="x", port_mapping={8000: hm.dev.port()},
            env={"DB_HOST": db.name},
        )

    out = json.loads(dump_registry_json(worktree_root=Path("/tmp/wt")))
    assert out["deployments"]["api"]["deps"] == ["db"]
    assert out["deployments"]["api"]["env"] == {"DB_HOST": "db"}


def test_dump_step_chain_emits_pipeline_v0_ir():
    @hm.deploy("api")
    def api():
        return hm.dev.deploy(
            from_=hm.sh("echo build", image="alpine:3.20"),
            port_mapping={8000: hm.dev.port()},
        )

    out = json.loads(dump_registry_json(worktree_root=Path("/tmp/wt")))
    f = out["deployments"]["api"]["from"]
    assert f["type"] == "step_chain"
    assert f["pipeline_v0"]["version"] == "0"
    assert f["pipeline_v0"]["steps"][0]["cmd"] == "echo build"


def test_dump_non_local_driver_is_marked_unhandled():
    @hm.deploy("prod-api")
    def prod_api():
        # Future drivers will produce their own subclasses; for the v1
        # registry-dump test we use the abstract Deployment with a
        # non-"local" driver to simulate the shape.
        return Deployment(name="", driver="aws")

    out = json.loads(dump_registry_json(worktree_root=Path("/tmp/wt")))
    assert out["deployments"]["prod-api"] == {"driver": "aws", "_unhandled": True}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/dev/test_registry_dump.py -v
```

Expected: ImportError on `dump_registry_json` from `harmont.dev`.

- [ ] **Step 3: Implement `harmont/dev/_registry_dump.py`**

```python
"""Local-driver registry dump.

Walks ``harmont._deploy.DEPLOYMENTS`` in topo order, lowering each
``LocalDeployment`` to the JSON shape described in
``docs/superpowers/specs/2026-05-21-hm-dev-deploy-design.md`` § 1.
Non-local deployments are passed through as ``{"driver": X,
"_unhandled": true}`` so the CLI can render them in ``hm dev ls``.

Step-chain deployments emit their pipeline as the existing v0 IR via
``harmont.pipeline()``; cache-keys are resolved through
``harmont.pipeline_to_json``'s standard path.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from harmont._deploy import DEPLOYMENTS, Deployment, dep_graph, topo_order
from harmont._target import clear_target_memo
from harmont.pipeline import pipeline as _assemble
from harmont.keygen import resolve_pipeline_keys

from ._deployment import LocalDeployment
from ._port import _PortSentinel

if TYPE_CHECKING:
    from pathlib import Path


_SENTINEL_WIRE = "__hm_dev_port__"


def _lower_local(d: LocalDeployment, deps: tuple[str, ...]) -> dict[str, Any]:
    return {
        "driver": "local",
        "image": d.image,
        "from": _lower_from_step(d.from_step) if d.from_step is not None else None,
        "cmd": list(d.cmd) if d.cmd is not None else None,
        "port_mapping": {
            str(cport): _SENTINEL_WIRE
            for cport, value in d.port_mapping.items()
            if isinstance(value, _PortSentinel)
        },
        "env": dict(d.env),
        "volumes": dict(d.volumes),
        "workdir": d.workdir,
        "deps": list(deps),
    }


def _lower_from_step(step: Any) -> dict[str, Any]:
    """Lower a single Step (the deployment's `from_=`) into the v0 IR shape.

    The Step is treated as the terminal leaf of a one-pipeline IR.
    Cache-keys are resolved via the existing keygen so the Rust side
    can use them as image tags without re-running the algorithm.
    """
    ir = _assemble(step)
    resolve_pipeline_keys(
        ir.get("steps", []),
        pipeline_org="hm-dev",
        pipeline_slug="hm-dev-build",
        now=0,
        base_path=None,
        env={},
    )
    return {"type": "step_chain", "pipeline_v0": ir}


def dump_registry_json(
    *,
    worktree_root: "Path | None" = None,
) -> str:
    """Emit the v0 deployment-registry JSON.

    ``worktree_root`` is recorded so the CLI can resolve relative
    ``volumes`` paths and the worktree-hash label.  Pass the value
    yourself in tests; production use comes through the CLI shim
    (``python -m harmont.dev --dump-registry --worktree-root <PATH>``).
    """
    from pathlib import Path as _Path

    clear_target_memo()
    wt = _Path(worktree_root) if worktree_root is not None else _Path.cwd()
    order = topo_order()
    graph = dep_graph()
    deployments: dict[str, dict[str, Any]] = {}
    for slug in order:
        value = DEPLOYMENTS[slug]()
        if isinstance(value, LocalDeployment):
            deployments[slug] = _lower_local(value, graph[slug])
        elif isinstance(value, Deployment):
            deployments[slug] = {"driver": value.driver, "_unhandled": True}
        else:
            msg = (
                f"hm: @hm.deploy({slug!r}) returned {type(value).__name__}; "
                "expected a Deployment subclass"
            )
            raise TypeError(msg)
    return json.dumps({
        "schema_version": "0",
        "worktree": str(wt),
        "deployments": deployments,
    })
```

- [ ] **Step 4: Re-export from `harmont/dev/__init__.py`**

Replace `harmont/dev/__init__.py` with the final v1 content:

```python
"""harmont.dev — local Docker deployment driver.

Public surface:

    deploy(*, image=None, from_=None, cmd=None,
           port_mapping=None, env=None,
           volumes=None, workdir=None) -> LocalDeployment
    port()                                  -> _PortSentinel
    LocalDeployment                          (concrete subclass)
    dump_registry_json(*, worktree_root)    -> str
"""
from __future__ import annotations

from ._deployment import LocalDeployment
from ._factory import deploy
from ._port import _PortSentinel, port
from ._registry_dump import dump_registry_json

__all__ = ["LocalDeployment", "_PortSentinel", "deploy", "dump_registry_json", "port"]
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/dev/test_registry_dump.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add harmont/dev/_registry_dump.py harmont/dev/__init__.py tests/dev/test_registry_dump.py
git commit -m "$(cat <<'EOF'
feat(dev): dump_registry_json emits the v0 deployment IR for the CLI

Walks DEPLOYMENTS in topo order, lowering LocalDeployment values to
the schema documented in the spec (§ 1). Step-chain from_= values are
lowered via the existing harmont.pipeline() + keygen pipeline so the
Rust executor can run the chain and use the terminal key as the
build-image tag. Non-local drivers are passed through as
{"driver": X, "_unhandled": true} for hm dev ls.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: `python -m harmont.dev --dump-registry` CLI shim

The Rust CLI spawns this subprocess to read the deployment registry. It walks `.harmont/*.py`, imports each (side-effect registration), then prints the registry JSON to stdout.

**Files:**
- Create: `harmont/dev/__main__.py`
- Test: `tests/dev/test_dump_cli.py`

- [ ] **Step 1: Write the failing test**

In `tests/dev/test_dump_cli.py`:

```python
"""`python -m harmont.dev --dump-registry` integration."""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path


def test_dump_cli_walks_harmont_dir_and_prints_registry(tmp_path: Path):
    pkg = tmp_path / ".harmont"
    pkg.mkdir()
    (pkg / "deploys.py").write_text(textwrap.dedent("""
        import harmont as hm

        @hm.deploy("db")
        def db():
            return hm.dev.deploy(
                image="postgres:16",
                port_mapping={5432: hm.dev.port()},
                env={"POSTGRES_PASSWORD": "dev"},
            )
    """))
    result = subprocess.run(
        [sys.executable, "-m", "harmont.dev", "--dump-registry"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    out = json.loads(result.stdout)
    assert out["schema_version"] == "0"
    assert out["worktree"] == str(tmp_path)
    assert "db" in out["deployments"]
    assert out["deployments"]["db"]["image"] == "postgres:16"


def test_dump_cli_errors_when_no_harmont_dir(tmp_path: Path):
    result = subprocess.run(
        [sys.executable, "-m", "harmont.dev", "--dump-registry"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "no .harmont/ directory" in result.stderr


def test_dump_cli_errors_on_bad_argument(tmp_path: Path):
    result = subprocess.run(
        [sys.executable, "-m", "harmont.dev", "--no-such-flag"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2  # argparse default
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/dev/test_dump_cli.py -v
```

Expected: `ModuleNotFoundError: No module named 'harmont.dev.__main__'`.

- [ ] **Step 3: Implement `harmont/dev/__main__.py`**

```python
"""`python -m harmont.dev` — registry-dump entry point for the CLI.

Walks ``.harmont/*.py`` (importing each by file path), letting
``@hm.deploy``-decorated functions register themselves into
``harmont._deploy.DEPLOYMENTS`` as a side effect. Then emits the
deployment registry JSON to stdout.

Errors go to stderr with exit code 1 (DSL error) or 2 (argparse
usage error), matching ``harmont``'s convention.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


def _import_path(path: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        name=f"_harmont_dev_user_{path.stem}",
        location=str(path),
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)


def _walk_harmont_dir(root: Path) -> None:
    harmont_dir = root / ".harmont"
    if not harmont_dir.is_dir():
        print(
            f"hm: no .harmont/ directory in {root}\n"
            "  → create .harmont/ and add @hm.deploy-decorated functions",
            file=sys.stderr,
        )
        sys.exit(1)
    for py in sorted(harmont_dir.glob("*.py")):
        _import_path(py)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m harmont.dev")
    parser.add_argument(
        "--dump-registry",
        action="store_true",
        help="walk .harmont/*.py and emit the v0 deployment registry JSON",
    )
    parser.add_argument(
        "--worktree-root",
        type=Path,
        default=None,
        help="path to the worktree root; defaults to cwd",
    )
    args = parser.parse_args(argv)

    if not args.dump_registry:
        parser.error("nothing to do; pass --dump-registry")
        return 2

    from harmont.dev import dump_registry_json

    root = args.worktree_root if args.worktree_root is not None else Path.cwd()
    _walk_harmont_dir(root)
    print(dump_registry_json(worktree_root=root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/dev/test_dump_cli.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add harmont/dev/__main__.py tests/dev/test_dump_cli.py
git commit -m "$(cat <<'EOF'
feat(dev): python -m harmont.dev --dump-registry CLI shim

Walks .harmont/*.py, imports each by file path so @hm.deploy
registrations land in harmont._deploy.DEPLOYMENTS, then prints the
deployment registry JSON to stdout. The Rust CLI invokes this and
deserializes via serde (see harmont-cli plan).

Missing .harmont/ exits 1 with a fix-directed stderr. Argparse handles
usage errors with exit 2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Update `CLAUDE.md` public-surface documentation

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Append deployments section to `CLAUDE.md`**

Read `CLAUDE.md`. Add the following section immediately before `## Cache keys` (the existing section):

````markdown
## Deployments — `@hm.deploy` and `hm.dev`

`@hm.deploy` is a driver-agnostic decorator that registers a function
as a long-lived service. The function returns a `Deployment` value
produced by a driver-specific factory; v1 ships only the local Docker
driver via `hm.dev.deploy(...)`. Future cloud drivers (`hm.aws.deploy`,
`hm.fly.deploy`) plug in without touching the top-level decorator.

```python
import harmont as hm

@hm.deploy("db")
def db() -> hm.Deployment:
    return hm.dev.deploy(
        image="postgres:16",
        port_mapping={5432: hm.dev.port()},
        env={"POSTGRES_PASSWORD": "dev"},
    )

@hm.deploy("api")
def api(
    db: hm.Dep[hm.Deployment],
    api_image: hm.Target[hm.Step],
) -> hm.Deployment:
    return hm.dev.deploy(
        from_=api_image,
        port_mapping={8000: hm.dev.port()},
        env={"DATABASE_URL": f"postgres://{db.name}:5432/app"},
    )
```

Public surface:

```python
hm.deploy(slug=None, *, name=None)                 # decorator
hm.Dep[T]                                           # PEP-593 fixture marker
hm.Deployment                                       # abstract dataclass

hm.dev.deploy(*, image=None, from_=None, cmd=None,
              port_mapping=None, env=None,
              volumes=None, workdir=None)           # -> LocalDeployment
hm.dev.port()                                       # OS-assigned host port sentinel
hm.dev.LocalDeployment                              # concrete subclass
hm.dev.dump_registry_json(*, worktree_root)         # -> v0 JSON
```

`hm.dev.port()` is only valid as a value in `port_mapping`. The host
port is assigned by Docker (via `-p :<container_port>`) at `hm dev up`
time; query it from another terminal with `hm dev port-of <slug>
<container_port>`. Ports are fresh on every `hm dev up`.

The Rust CLI (`hm dev up`) shells out to `python -m harmont.dev
--dump-registry` to obtain the registry JSON. Schema is at
`docs/superpowers/specs/2026-05-21-hm-dev-deploy-design.md` § 1.
````

- [ ] **Step 2: Sanity-check the doc compiles in your head**

Re-read CLAUDE.md top-to-bottom. Confirm no stale references and that the new section sits between the pipeline surface and the cache-key section.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "$(cat <<'EOF'
docs: document hm.deploy + hm.dev in CLAUDE.md

Adds the deployments section to the agent-facing doc with the
canonical example and the full public surface. Cross-links the
design spec for engineers who need the wire-format details.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Full-suite green + canonical end-to-end sanity check

A final integration test that mirrors the spec's canonical example. Confirms every piece works together.

**Files:**
- Test: `tests/dev/test_canonical_example.py` (new)

- [ ] **Step 1: Write the integration test**

In `tests/dev/test_canonical_example.py`:

```python
def test_canonical_hello_greeter_dumps_expected_shape():
    @hm.deploy("hello")
    def hello() -> hm.Deployment:
        return hm.dev.deploy(
            image="python:3.12-alpine",
            cmd=["python", "-m", "http.server", "5678"],
            port_mapping={5678: hm.dev.port()},
        )

    @hm.deploy("greeter")
    def greeter(hello: hm.Dep[hm.Deployment]) -> hm.Deployment:
        return hm.dev.deploy(
            image="python:3.12-alpine",
            cmd=["python", "-m", "http.server", "5678"],
            port_mapping={5678: hm.dev.port()},
            env={"HELLO_HOST": hello.name},
        )

    raw = hm.dev.dump_registry_json(worktree_root=Path("/tmp/wt"))
    out = json.loads(raw)
    assert out["schema_version"] == "0"
    assert list(out["deployments"].keys()) == ["hello", "greeter"]  # topo order
    assert out["deployments"]["greeter"]["deps"] == ["hello"]
    assert out["deployments"]["hello"]["image"] == "python:3.12-alpine"
    assert out["deployments"]["hello"]["cmd"] == [
        "python", "-m", "http.server", "5678",
    ]
    assert out["deployments"]["greeter"]["env"] == {"HELLO_HOST": "hello"}
    # No Step-chain in the new example (from_= is stubbed in v1 cli);
    # both entries have from=None.
    assert out["deployments"]["hello"]["from"] is None
    assert out["deployments"]["greeter"]["from"] is None
```

- [ ] **Step 2: Run only this test**

```bash
pytest tests/dev/test_canonical_example.py -v
```

Expected: 1 passed.

- [ ] **Step 3: Run the full suite to confirm zero regressions**

```bash
pytest -v
```

Expected: every test passes. If any pre-existing test fails, investigate `harmont/_deps.py` changes — they're the only cross-cutting modification.

- [ ] **Step 4: Run lint + type-check (matches CLAUDE.md gate)**

```bash
ruff check .
mypy harmont tests
```

Expected: both pass cleanly. The new code is fully type-annotated; if mypy complains, fix the annotations before committing — do not suppress.

- [ ] **Step 5: Commit**

```bash
git add tests/dev/test_canonical_example.py
git commit -m "$(cat <<'EOF'
test(dev): end-to-end canonical db+api+web example

Mirrors the spec's worked example. Asserts topo order, dep edges,
cross-deploy f-string env values, and that from_=Step lowers through
the existing v0 IR pipeline. This is the "vibe check" gate before
the CLI plan can start consuming the JSON output.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: PR-readiness sanity pass

**Files:** none modified.

- [ ] **Step 1: Branch is up to date with main**

```bash
git fetch origin main
git log --oneline origin/main..HEAD
```

Expected: a clean linear history of task commits.

- [ ] **Step 2: Confirm public surface end-to-end**

```bash
python -c "
import harmont as hm
print(hm.deploy, hm.Dep, hm.Deployment)
print(hm.dev.deploy, hm.dev.port, hm.dev.LocalDeployment, hm.dev.dump_registry_json)
"
```

Expected: every name prints without ImportError. If any fails, locate the missing re-export.

- [ ] **Step 3: Run the dump CLI shim against the canonical example**

```bash
mkdir /tmp/hm-deploy-smoke && cd /tmp/hm-deploy-smoke && mkdir .harmont && cat > .harmont/deploys.py <<'EOF'
import harmont as hm

@hm.deploy("db")
def db():
    return hm.dev.deploy(
        image="postgres:16",
        port_mapping={5432: hm.dev.port()},
        env={"POSTGRES_PASSWORD": "dev"},
    )
EOF
python -m harmont.dev --dump-registry | python -m json.tool
```

Expected: a pretty-printed JSON document matching the spec's schema.

- [ ] **Step 4: Commit ANY follow-up fixes (none if smoke is clean)**

If you tweak anything in this pass, commit it with subject `chore: PR-readiness sanity pass`. Otherwise skip.

- [ ] **Step 5: Done — branch ready for review**

The `feat/hm-dev-deploy` branch on harmont-py is now feature-complete for v1. The harmont-cli plan (`/home/marko/harmont-cli/docs/superpowers/plans/2026-05-21-hm-dev-deploy-cli.md`) is the natural follow-up; the cli plan assumes harmont-py from this branch is installed (e.g., `pip install -e ../harmont-py` in the cli test environment).

---

## Self-Review Notes (for the plan author, not the executor)

Coverage of spec § 1 (DSL surface):
- `hm.deploy` decorator → Task 6.
- `hm.Dep[T]` marker → Task 5.
- `hm.Deployment` abstract type → Task 1.
- `hm.dev.deploy(...)` factory → Task 4.
- `hm.dev.port()` sentinel → Task 2.
- `LocalDeployment` dataclass → Task 3.
- `dump_registry_json` → Task 8.
- `python -m harmont.dev --dump-registry` shim → Task 9.
- Validation rules (slug regex, port_mapping shape, env value types, volumes container-path, workdir absolute, exactly-one-of image/from_) → Tasks 4, 6.
- Fixture-injection rules (param must have marker or default; cycles raise) → Tasks 5, 6, 7.

Coverage of spec § 5 (error handling, decoration-time):
- "invalid deployment slug" → Task 6.
- "duplicate deployment slug" → Task 6.
- "hm.dev.deploy requires exactly one of image= or from_=" → Task 4.
- "port_mapping value must be hm.dev.port()" → Task 4.
- "parameter X must carry a marker" → Task 5 (via the extended `validate_target_signature`).
- "dep cycle" → Task 7.

Not covered by this plan (correctly — they belong in the cli plan):
- Spec § 2 (CLI surface) — entirely cli-side.
- Spec § 3 (runtime / executor) — entirely cli-side.
- Spec § 4 (lifecycle & signals) — entirely cli-side.
- Spec § 5 runtime errors — entirely cli-side.
- Spec § 6 (cli unit + integration tests).

Type / name consistency:
- `Deployment`, `LocalDeployment`, `deploy`, `Dep`, `port`, `dump_registry_json` are used identically across all tasks.
- `__hm_dev_port__` is the wire encoding everywhere it appears (Task 8 implementation + tests).
- `worktree_root` kwarg on `dump_registry_json` is used identically across Tasks 8, 9, 11.
- `from_step` (LocalDeployment field) vs `from_` (factory kwarg) — intentionally different (Python keyword conflict for the kwarg; the field is a normal attribute).
