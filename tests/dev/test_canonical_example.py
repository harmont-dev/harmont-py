"""End-to-end test mirroring the spec's canonical db+api+web example."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

import harmont as hm

if TYPE_CHECKING:
    from pathlib import Path


def test_canonical_db_api_web_dumps_expected_shape(tmp_path: Path):
    @hm.target()
    def api_image() -> hm.Step:
        return hm.sh("docker build -t myapi .", image="docker:24")

    @hm.deploy("db")
    def db() -> hm.Deployment:
        return hm.dev.deploy(
            image="postgres:16",
            cmd=["postgres", "-c", "shared_buffers=128MB"],
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
            volumes={".": "/workspace"},
            workdir="/workspace",
        )

    @hm.deploy("web")
    def web(api: hm.Dep[hm.Deployment]) -> hm.Deployment:
        return hm.dev.deploy(
            image="node:20",
            port_mapping={3000: hm.dev.port()},
            env={"API_URL": f"http://{api.name}:8000"},
        )

    raw = hm.dev.dump_registry_json(worktree_root=tmp_path)
    out = json.loads(raw)
    assert out["schema_version"] == "0"
    assert list(out["deployments"].keys()) == ["db", "api", "web"]  # topo order
    assert out["deployments"]["api"]["deps"] == ["db"]
    assert out["deployments"]["web"]["deps"] == ["api"]
    assert out["deployments"]["api"]["env"]["DATABASE_URL"] == "postgres://db:5432/app"
    assert out["deployments"]["web"]["env"]["API_URL"] == "http://api:8000"
    # Step-chain `from_=` lowered through the existing v0 IR machinery
    api_from = out["deployments"]["api"]["from"]
    assert api_from["type"] == "step_chain"
    assert api_from["pipeline_v0"]["version"] == "0"
    assert any(s.get("cmd", "").startswith("docker build")
               for s in api_from["pipeline_v0"]["steps"])
