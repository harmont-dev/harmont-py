"""Driver-agnostic deployment registry, decorator, and Dep marker.

This module is intentionally driver-free. Concrete deployment types
(``LocalDeployment``, future ``AwsDeployment``, …) live in their own
driver subpackages (``harmont.dev``, future ``harmont.aws``).
The registry stores deployments polymorphically; CLI subcommands filter
by ``isinstance`` or by the ``driver`` discriminator.
"""
from __future__ import annotations

import dataclasses
import inspect
import re
import typing
from dataclasses import dataclass
from functools import wraps
from typing import TYPE_CHECKING, Any

from ._deps import call_with_deps
from ._typing import _TARGET_MARKER, _BaseImageMarker, _DepMarker

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


_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]{0,30}$")


def _validate_slug(slug: str) -> None:
    """Raise ValueError if slug does not satisfy Docker container-name rules."""
    if not _SLUG_RE.match(slug):
        msg = (
            f"hm: invalid deployment slug {slug!r}\n"
            "  → use lowercase letters, digits, and '-', "
            "start with a letter, max 31 chars (Docker container name rules)"
        )
        raise ValueError(msg)


def _validate_deploy_signature(fn: Callable[..., Any]) -> None:
    """Decoration-time validation for @hm.deploy functions.

    Raises ValueError (not TypeError) with a deploy-specific message so
    callers see a clean, deploy-oriented error distinct from the
    @hm.target TypeError surface.

    Rules:
      - No ``*args``, ``**kwargs``, or positional-only parameters.
      - Every parameter must carry an hm marker (``Target[T]``,
        ``BaseImage[...]``, ``Dep[T]``) or have a default value.
    """
    sig = inspect.signature(fn)
    hints: dict[str, Any]
    try:
        hints = typing.get_type_hints(fn, include_extras=True)
    except Exception:
        hints = dict(getattr(fn, "__annotations__", {}))

    for param in sig.parameters.values():
        kind = param.kind
        if kind == inspect.Parameter.VAR_POSITIONAL:
            msg = (
                "hm: @hm.deploy functions cannot take *args\n"
                "  → declare each dependency as an explicit named parameter"
            )
            raise ValueError(msg)
        if kind == inspect.Parameter.VAR_KEYWORD:
            msg = (
                "hm: @hm.deploy functions cannot take **kwargs\n"
                "  → declare each dependency as an explicit named parameter"
            )
            raise ValueError(msg)
        if kind == inspect.Parameter.POSITIONAL_ONLY:
            msg = (
                f"hm: @hm.deploy functions cannot have positional-only "
                f"parameters (got {param.name!r})\n"
                "  → remove the '/' marker; parameters must be name-resolvable"
            )
            raise ValueError(msg)

        annotation = hints.get(param.name)
        # Check for any recognized hm marker.
        marker = _marker_for(annotation)
        if marker is not None:
            continue
        if param.default is not inspect.Parameter.empty:
            continue
        msg = (
            f"hm: parameter {param.name!r} on {fn.__qualname__} must carry a marker\n"
            "  → annotate with Dep[T] (deployment dep), Target[T] (target dep), "
            'or BaseImage["..."] (scratch image), or give it a default'
        )
        raise ValueError(msg)


def _marker_for(annotation: Any) -> object | None:
    """Return the hm-specific marker from an Annotated annotation, or None."""
    if typing.get_origin(annotation) is None:
        return None
    metadata = typing.get_args(annotation)[1:]
    for meta in metadata:
        if meta is _TARGET_MARKER:
            return _TARGET_MARKER
        if isinstance(meta, _BaseImageMarker):
            return meta
        if isinstance(meta, _DepMarker):
            return meta
    return None


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
    references.

    Usage::

        @hm.deploy("db")
        def db():
            return hm.dev.deploy(image="postgres:16", port_mapping={5432: hm.dev.port()})

        @hm.deploy("api")
        def api(db: hm.Dep[hm.Deployment]):
            return hm.dev.deploy(
                image="myapp:latest",
                port_mapping={8000: hm.dev.port()},
                env={"DB_HOST": db.name},
            )

    Args:
        slug: Registry key for this deployment. Must match
              ``^[a-z][a-z0-9-]{0,30}$`` (Docker container-name rules).
              Defaults to the decorated function's ``__name__``.
        name: Reserved for future use as a human-readable display name.
              Has no effect in v1; the slug is the public identity.

    Raises:
        ValueError: On invalid slug, duplicate slug, or an unmarkered
                    parameter with no default.
        TypeError: If the wrapped function returns a non-:class:`Deployment`
                   value at call time.
    """

    def decorator(fn: "Callable[..., Any]") -> "Callable[[], Deployment]":
        _validate_deploy_signature(fn)
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
            # Stamp the resolved slug into the returned dataclass so callers
            # see name=<slug> regardless of what the factory left in `name`.
            return dataclasses.replace(value, name=resolved_slug)

        DEPLOYMENTS[resolved_slug] = wrapper
        return wrapper

    return decorator
