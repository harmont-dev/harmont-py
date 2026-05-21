"""Zig toolchain abstraction.

Chain: scratch -> apt-base (curl, xz-utils, ca-certificates) -> zig-install
(download tarball from ziglang.org, extract to /usr/local/zig) -> action
leaves.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ._toolchain import make_install_chain
from .cache import CacheForever

if TYPE_CHECKING:
    from ._step import Step

APT_PACKAGES = ("curl", "ca-certificates", "xz-utils")

_ACTION_KWARGS = frozenset(("cache", "env", "timeout_seconds", "label", "key"))

_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


def _zig_install_cmd(version: str) -> str:
    tarball = f"zig-linux-x86_64-{version}.tar.xz"
    url = f"https://ziglang.org/download/{version}/{tarball}"
    return (
        f"curl -fsSL {url} -o /tmp/zig.tar.xz && "
        "rm -rf /usr/local/zig && mkdir -p /usr/local/zig && "
        "tar -xJf /tmp/zig.tar.xz -C /usr/local/zig --strip-components=1 && "
        "ln -sf /usr/local/zig/zig /usr/local/bin/zig && zig version"
    )


@dataclass(frozen=True)
class ZigProject:
    path: str
    installed: Step

    def _emit(self, cmd: str, default_label: str, **kw: Any) -> Step:
        if kw.get("label") is None:
            kw["label"] = default_label
        return self.installed.sh(cmd, **kw)

    def build(self, **kw: Any) -> Step:
        return self._emit(f"cd {self.path} && zig build", ":zig: build", **kw)

    def test(self, **kw: Any) -> Step:
        return self._emit(f"cd {self.path} && zig build test", ":zig: test", **kw)

    def fmt(self, **kw: Any) -> Step:
        return self._emit(f"cd {self.path} && zig fmt --check .", ":zig: fmt", **kw)


def _make_zig(
    *,
    path: str = ".",
    version: str = "0.13.0",
    image: str | None = None,
    base: Step | None = None,
) -> ZigProject:
    if not _VERSION_RE.match(version):
        msg = (
            f"hm.zig: invalid version {version!r}\n"
            '  → use a Zig version like "0.13.0"'
        )
        raise ValueError(msg)
    installed = make_install_chain(
        apt_packages=APT_PACKAGES,
        install_cmd=_zig_install_cmd(version),
        install_cache=CacheForever(env_keys=()),
        lang_tag="zig",
        install_tag="install",
        image=image,
        base=base,
    )
    return ZigProject(path=path, installed=installed)


class _ZigEntry:
    def __call__(
        self,
        *,
        path: str = ".",
        version: str = "0.13.0",
        image: str | None = None,
        base: Step | None = None,
    ) -> ZigProject:
        return _make_zig(path=path, version=version, image=image, base=base)

    def build(self, **kw: Any) -> Step:
        action_kw = {k: kw.pop(k) for k in list(kw) if k in _ACTION_KWARGS}
        return self(**kw).build(**action_kw)

    def test(self, **kw: Any) -> Step:
        action_kw = {k: kw.pop(k) for k in list(kw) if k in _ACTION_KWARGS}
        return self(**kw).test(**action_kw)

    def fmt(self, **kw: Any) -> Step:
        action_kw = {k: kw.pop(k) for k in list(kw) if k in _ACTION_KWARGS}
        return self(**kw).fmt(**action_kw)


zig = _ZigEntry()
