"""OCaml toolchain abstraction.

Chain: scratch -> apt-base (opam + build deps) -> opam-init (opam switch
create <compiler>; installs project deps via ``opam install . --deps-only``
when the project has an .opam file) -> action leaves driven by dune.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ._toolchain import make_install_chain
from .cache import CacheForever

if TYPE_CHECKING:
    from ._step import Step

APT_PACKAGES = (
    "opam",
    "build-essential",
    "git",
    "m4",
    "unzip",
    "bubblewrap",
)

_ACTION_KWARGS = frozenset(("cache", "env", "timeout_seconds", "label", "key"))

_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


def _opam_init_cmd(compiler: str) -> str:
    return (
        "opam init -y --disable-sandboxing --bare && "
        f"opam switch create {compiler} {compiler} && "
        "eval $(opam env) && opam install -y dune ocamlformat"
    )


@dataclass(frozen=True)
class OCamlProject:
    path: str
    installed: Step

    def _emit(self, cmd: str, default_label: str, **kw: Any) -> Step:
        if kw.get("label") is None:
            kw["label"] = default_label
        return self.installed.sh(cmd, **kw)

    def build(self, **kw: Any) -> Step:
        return self._emit(
            f"cd {self.path} && opam exec -- dune build",
            ":ocaml: build",
            **kw,
        )

    def test(self, **kw: Any) -> Step:
        return self._emit(
            f"cd {self.path} && opam exec -- dune runtest",
            ":ocaml: test",
            **kw,
        )

    def fmt(self, **kw: Any) -> Step:
        return self._emit(
            f"cd {self.path} && opam exec -- dune build @fmt",
            ":ocaml: fmt",
            **kw,
        )


def _make_ocaml(
    *,
    path: str = ".",
    compiler: str = "5.1.1",
    image: str | None = None,
    base: Step | None = None,
) -> OCamlProject:
    if not _VERSION_RE.match(compiler):
        msg = (
            f"hm.ocaml: invalid compiler {compiler!r}\n"
            '  → use a compiler version like "5.1.1"'
        )
        raise ValueError(msg)
    installed = make_install_chain(
        apt_packages=APT_PACKAGES,
        install_cmd=_opam_init_cmd(compiler),
        install_cache=CacheForever(env_keys=()),
        lang_tag="ocaml",
        install_tag="opam",
        image=image,
        base=base,
    )
    return OCamlProject(path=path, installed=installed)


class _OCamlEntry:
    def __call__(
        self,
        *,
        path: str = ".",
        compiler: str = "5.1.1",
        image: str | None = None,
        base: Step | None = None,
    ) -> OCamlProject:
        return _make_ocaml(path=path, compiler=compiler, image=image, base=base)

    def build(self, **kw: Any) -> Step:
        action_kw = {k: kw.pop(k) for k in list(kw) if k in _ACTION_KWARGS}
        return self(**kw).build(**action_kw)

    def test(self, **kw: Any) -> Step:
        action_kw = {k: kw.pop(k) for k in list(kw) if k in _ACTION_KWARGS}
        return self(**kw).test(**action_kw)

    def fmt(self, **kw: Any) -> Step:
        action_kw = {k: kw.pop(k) for k in list(kw) if k in _ACTION_KWARGS}
        return self(**kw).fmt(**action_kw)


ocaml = _OCamlEntry()
