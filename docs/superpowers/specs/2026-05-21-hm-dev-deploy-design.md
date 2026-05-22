# `hm.deploy` + `hm dev` Local Deployments — Design Spec

**Status:** Draft. v1 = local Docker driver only.
**Repos touched:** `harmont-py` (DSL), `harmont-cli` (executor).
**Authors:** Claude + Marko.

---

## Goal

Let Harmont users declare long-lived, port-mapped local services (Postgres, Redis, an API container, a webapp dev server, …) from the same Python DSL they use for pipelines, and bring them up with one foreground command per worktree.

## Motivation

The agentic workflow has one developer (or one agent) per git worktree. Each worktree wants its own Postgres, its own API, its own dev server — running on **globally-unique host ports** so they coexist on one machine. Today this requires hand-curated `docker compose` files with manually-assigned ports, drifting from the canonical CI definition.

`hm.deploy` + `hm dev up` makes that ergonomic, type-checked, and consistent with the rest of Harmont:

- Same DSL idioms as `@hm.pipeline` and `@hm.target` (fixture injection, frozen dataclasses, decoration-time validation, fix-directed errors).
- One source of truth: deployments live alongside pipelines in `.harmont/*.py`.
- Each `hm dev up` invocation gets its own ephemeral docker network and a per-session container suffix so multiple sessions in the same worktree don't collide.
- Port assignment is delegated to the OS (`docker -p :CPORT`), so no global registry, no allocator, no lock files.

## Non-goals (v1)

- Non-local drivers (`hm.aws`, `hm.fly`, `hm.k8s`). The decorator + abstract type are designed to admit them later; no stubs ship now.
- Daemon-mode / background deployments.
- Healthchecks beyond `Running: true`.
- Cross-session shared state.
- Persistent named volumes (bind mounts only).
- Pipeline ↔ deployment auto-wiring (a test pipeline can't yet declare "needs db up"); deferred.
- Wire-format JSON IR for deployments. v1 hands a Python dict (serialized JSON) from a subprocess to the CLI. Formalized when a second driver lands.

---

## §1 DSL surface

### Decoupling test

If `harmont.dev` were deleted entirely, `harmont.deploy` + `harmont.Dep` + `harmont.Deployment` would still compile, the registry would still populate (with deployments nobody can materialize), and `hm dev up` would error cleanly: "no local driver available." That asymmetry is the invariant — top-level is driver-agnostic; everything driver-specific lives in `harmont.dev`.

### Public surface (full enumeration)

```python
# harmont/__init__.py — top-level (driver-agnostic)
hm.deploy(slug=None, *, name=None)                 # decorator
hm.Dep[T]                                           # PEP-593 marker for dep injection
hm.Deployment                                       # abstract dataclass; .name + .driver

# harmont/dev/__init__.py — local driver
hm.dev.deploy(*, image=None, from_=None, cmd=None,
              port_mapping=None, env=None,
              volumes=None, workdir=None)           # -> LocalDeployment
hm.dev.port()                                       # sentinel: OS picks free host port
hm.dev.LocalDeployment                              # concrete subclass of Deployment
hm.dev.dump_registry_json()                         # -> str (driver-filtered for local)
```

### Canonical example

```python
import harmont as hm

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
```

### Type hierarchy

```python
# harmont/_deploy.py
@dataclass(frozen=True)
class Deployment:
    name: str
    driver: str          # discriminator: "local" in v1

# harmont/dev/_deployment.py
@dataclass(frozen=True)
class LocalDeployment(Deployment):
    image: str | None
    from_step: Step | None
    cmd: tuple[str, ...] | None
    port_mapping: Mapping[int, _PortSentinel]
    env: Mapping[str, str]
    volumes: Mapping[str, str]
    workdir: str | None
    # __post_init__ enforces driver == "local"
```

### Fixture injection (parameters)

A `@hm.deploy`-decorated function's parameters carry typed markers, just like `@hm.target`:

- `hm.Dep[hm.Deployment]` — declares a dependency on another `@hm.deploy` by parameter name. The injected value is a `Deployment` with `.name` already resolved (the slug). The decorator builds the dep graph from these markers.
- `hm.Target[T]` — same `@hm.target` machinery already used by pipelines.

Rules (decoration-time):

- Every parameter must carry a marker or have a default; otherwise `ValueError` at decoration time, fix-directed message.
- `*args` / `**kwargs` / positional-only params are rejected.
- Duplicate slugs across `@hm.deploy` raise at decoration time (`hm.deploy(name="…")` is the disambiguation hatch — mirrors `@hm.target`).
- Dep cycles raise `RuntimeError` listing the path.

### Validation rules for `hm.dev.deploy(...)`

- Exactly one of `image=` and `from_=` must be set; else `ValueError`.
- `port_mapping` keys are ints in `[1, 65535]`; values must be `hm.dev.port()` sentinels in v1 (pinned-int values are future). Wrong type → `ValueError` w/ pointer to `hm.dev.port()`.
- `volumes` keys are host paths (relative resolved against worktree root, absolute kept as-is); values are container paths. Container paths must start with `/`.
- `cmd` must be a sequence of strings; coerced to `tuple[str, ...]`.
- `env` values must be strings; non-strings rejected at decoration time (avoid `str(int)` surprises mid-run).
- Slug must match `^[a-z][a-z0-9-]{0,30}$` (Docker container name rules, lowercased).

### `hm.dev.port()` sentinel

Returns a singleton `_PortSentinel` instance. It is `==` to itself, has no public attributes, and its `__repr__` is `<hm.dev.port>`. It is **only** valid as a value in `port_mapping`. Used anywhere else (env value, cmd arg, …) → `ValueError` at the point of use with a fix-directed message:

```
hm.dev.port() can only appear as a port_mapping value, not as an env value.
  → use a fixed value here, or query the resolved port via
    `hm dev port-of <slug> <container-port>` after `hm dev up`.
```

### Registry handoff (python → cli)

`harmont.dev.dump_registry_json()` walks `.harmont/*.py`, runs decorators, filters the registry to local-driver deployments, and emits:

```json
{
  "schema_version": "0",
  "worktree": "/home/marko/myrepo",
  "deployments": {
    "db":  {
      "driver": "local",
      "image":  "postgres:16",
      "from":   null,
      "cmd":    ["postgres", "-c", "shared_buffers=128MB"],
      "port_mapping": {"5432": "__hm_dev_port__"},
      "env":    {"POSTGRES_PASSWORD": "dev"},
      "volumes": {},
      "workdir": null,
      "deps":   []
    },
    "api": {
      "driver": "local",
      "image":  null,
      "from":   { "type": "step_chain", "pipeline_v0": { "version": "0", "steps": [/* ... */] } },
      "cmd":    null,
      "port_mapping": {"8000": "__hm_dev_port__"},
      "env":    {"DATABASE_URL": "postgres://db:5432/app"},
      "volumes": {".": "/workspace"},
      "workdir": "/workspace",
      "deps":   ["db"]
    },
    "prod-api": { "driver": "aws", "_unhandled": true }
  }
}
```

Non-local-driver deployments are emitted with `"_unhandled": true` and opaque-otherwise so `hm dev ls` can show them.

A separate `python -m harmont.dev --dump-registry` shim emits this to stdout. The CLI shells out to it.

---

## §2 CLI surface

### Container, network, and label scheme

```
session-id   = 6 random hex chars, generated per `hm dev up` invocation
worktree-hash = sha1(canonical_path(git rev-parse --show-toplevel))[:10]
container    = hm-<worktree-hash>-<slug>-<session>
network      = hm-<worktree-hash>-<session>
labels       = harmont.worktree=<hash>
               harmont.slug=<slug>
               harmont.session=<session>
               harmont.driver=local
```

Multiple `hm dev up`s in the same worktree are allowed — each gets its own session and its own bridge network. Sessions never see each other's containers.

If git is unavailable (no repo), worktree-hash falls back to sha1 of the absolute `cwd`. The CLI never refuses to run for lack of a git repo.

### Subcommand tree

```
hm dev up [SLUG ...]                 foreground; blocks until SIGINT
   --no-deps                         skip transitive deps
   --rebuild                         force image rebuild on Step-chain deployments

hm dev down [SLUG ...]               sweep this worktree's sessions
   --session <ID>                    sweep one specific session entirely
   --all                             sweep system-wide (every harmont.driver=local container)

hm dev ls                            list registered + running deployments

hm dev logs <SLUG> [--follow]        tail running container's logs from another terminal
   --session <ID>                    disambiguate when ≥2 sessions hold the slug

hm dev port-of <SLUG> <CPORT>        print host port for live deployment (designed for $())
   --session <ID>                    disambiguate

hm dev exec <SLUG> [-- CMD ...]      one-shot exec into live container; default `sh -l`
   --session <ID>                    disambiguate
```

### `hm dev up` UX

```
$ hm dev up
[hm] session 7a2f91. resolving deployments in .harmont/
[hm] graph: db → api → web   (3 deployments, 2 edges)
[hm] network hm-a1b2c3d4e5-7a2f91: created
[db]  pulling postgres:16…
[db]  ready  ( hm-a1b2c3d4e5-db-7a2f91 | localhost:42173 → :5432 )
[api] building from target api_image…
[api] ready  ( hm-a1b2c3d4e5-api-7a2f91 | localhost:42174 → :8000 )
[web] ready  ( hm-a1b2c3d4e5-web-7a2f91 | localhost:42175 → :3000 )
[hm] all up. Ctrl-C to tear down. Logs follow.
[db]  2026-05-21 12:00:00 UTC LOG: database system is ready to accept connections
[api] [info] listening on :8000
[web] [HMR] connected
^C
[hm] tearing down…
[web] stopped
[api] stopped
[db]  stopped
[hm] network hm-a1b2c3d4e5-7a2f91: removed
$
```

**Log mux:** each slug gets a stable color from a fixed 6-ANSI palette (cycle by `hash(slug) % 6`). Prefix is `[slug] ` in slug's color; raw line follows uncolored. Slug-width padded to longest registered slug for vertical alignment. Honor `--no-color` and `NO_COLOR` env (per `clig.dev`).

**Boot order:** topological. Each level boots in parallel; readiness is `docker inspect` reports `Running: true`. No log-grep or port-probe healthcheck in v1.

### Ambiguity rule (port-of / logs / exec)

When ≥2 live sessions in the current worktree hold the requested slug, error and enumerate:

```
$ hm dev port-of db 5432
hm: slug `db` matches multiple live sessions in this worktree:
  7a2f91  started 12:00:14  localhost:42173
  c4d8e0  started 12:05:31  localhost:42891
pass `--session <id>` or run `hm dev ls`.
exit 5
```

No silent "pick latest" — explicit per PRINCIPLES § 5.

### `hm dev ls` output

```
$ hm dev ls
SLUG       DRIVER  SESSION  STATUS    PORTS
db         local   7a2f91   running   localhost:42173 → :5432
api        local   7a2f91   running   localhost:42174 → :8000
db         local   c4d8e0   running   localhost:42891 → :5432
web        local   —        registered (not running)
prod-api   aws     —        registered (no local driver; use `hm aws up`)
```

Status comes from `docker inspect` filtered by `label=harmont.worktree=<this>`. The `prod-api` row is rendered from the registry dump's `_unhandled: true` rows.

### Exit codes (per PRINCIPLES § 4)

```
0    success
1    deployment-level failure (build chain failed, container failed to start)
2    usage error (clap parse)
3    auth (unused in v1, reserved)
4    slug known but not running   (port-of / logs / exec on a stopped slug)
5    API/network error            (docker daemon unreachable, slug unknown, ambiguous slug)
10   cancelled
130  SIGINT
```

---

## §3 Runtime & executor

### Process model

One `hm dev up` invocation is one Rust process, tokio-based, that:

1. Shells out to `python -m harmont.dev --dump-registry` to get the deployment registry JSON.
2. Computes the boot plan (topo sort, optionally pruned by `--no-deps`).
3. Creates the per-session bridge network.
4. Boots deployments level-by-level (parallel within a level).
5. Multiplexes logs from all containers to stdout until SIGINT/SIGTERM.
6. Tears down: stop, remove containers, remove network.

### Registry handoff

```
hm dev up  ──exec──►  python -m harmont.dev --dump-registry
                         │
                         ▼  (stdout: JSON per §1 schema)
                       parse via serde
```

Rust types live in `crates/hm/src/commands/dev/registry.rs`:

```rust
#[derive(Debug, Deserialize)]
struct DevRegistry {
    schema_version: String,
    worktree: String,
    deployments: BTreeMap<String, RegEntry>,
}

#[derive(Debug, Deserialize)]
#[serde(tag = "driver")]
enum RegEntry {
    #[serde(rename = "local")] Local(LocalSpec),
    #[serde(other)] Unhandled,
}
```

`Unhandled` entries flow through to `hm dev ls` and are skipped by `hm dev up`.

### Boot pipeline (per deployment)

For each `D` in topo order:

1. **Resolve image**
   - `D.image` set → `docker_client.image_exists(tag)`; pull if absent.
   - `D.from_step` set → run the embedded v0 IR pipeline via the existing `orchestrator::run_pipeline_local` codepath in a one-shot build container; on success `docker_client.commit_container(id, "hm-build-<wt>-<slug>:<chain-key>")`. If a tag with that `<chain-key>` already exists and `--rebuild` not set, skip the build.
2. **Translate volumes** — host paths resolved against worktree root; emit bind-mounts `"<host-abs>:<container>[:ro]"`.
3. **Translate port mapping** — for each `{cport: __hm_dev_port__}`, emit `PortBinding{HostPort: ""}` for `cport/tcp` → daemon assigns ephemeral host port.
4. **Start container** via new `docker_client::start_service(spec)`:

   ```rust
   pub struct ServiceSpec<'a> {
       pub image: &'a str,
       pub name: &'a str,
       pub env: Vec<String>,
       pub cmd: Option<Vec<String>>,
       pub workdir: Option<&'a str>,
       pub binds: Vec<String>,
       pub publish: Vec<u16>,
       pub network: &'a str,
       pub network_alias: &'a str,
       pub labels: HashMap<String, String>,
   }
   pub async fn start_service(&self, spec: ServiceSpec<'_>) -> Result<String>;
   ```

5. **Inspect for assigned ports** — `inspect_ports(container_id) -> HashMap<u16, u16>` (container → host). Stored in an in-memory `Session`.
6. **Start log stream** — `bollard::container::logs(id, LogsOptions{follow: true, …})` → `mpsc::UnboundedSender<LogLine>` consumed by the log mux task.

### Log mux

`crates/hm/src/commands/dev/logmux.rs`:

```rust
struct LogLine { slug: String, stream: Stream, bytes: Vec<u8> }
```

Per-slug `LinesReader` buffers partial chunks (docker streams may not be line-aligned), flushes on `\n`. Output format: `[<colored slug, padded>] <raw line>\n`. Stderr lines interleave with stdout in arrival order; v1 does not separate streams.

### Concurrency model

```rust
async fn up(args: UpArgs) -> Result<()> {
    let reg = registry::dump(&ctx).await?;
    let plan = topo::plan(&reg, &args)?;
    let docker = DockerClient::connect()?;
    let session_id = rand_hex(6);
    let net = network::create(&docker, &ctx, &session_id).await?;
    let mut session = Session::new(session_id, net.clone());

    let (log_tx, log_rx) = mpsc::unbounded_channel();
    let mut sig = signal::ctrl_c_then_term();

    for level in plan.levels() {
        let mut joinset = JoinSet::new();
        for slug in level {
            let spec = build_spec(&reg[slug], &ctx, &session, &net);
            joinset.spawn(boot_one(docker.clone(), spec, log_tx.clone()));
        }
        while let Some(res) = joinset.join_next().await {
            session.record(res??);
        }
    }

    tokio::spawn(logmux::run(log_rx, args.no_color));
    eprintln!("[hm] all up. Ctrl-C to tear down.");

    tokio::select! {
        _ = sig.recv() => {}
        _ = monitor_unexpected_exits(&docker, &session) => {}
    }

    teardown(&docker, &session).await
}
```

`monitor_unexpected_exits` polls `docker inspect` for each container at 2s intervals; on a transition to non-running it logs `[slug] exited (code N)` and marks the entry. It does not unilaterally tear down — user might want to keep inspecting the live ones.

### Build-chain reuse (`from_=Step`)

Existing `orchestrator/` already executes v0 IR pipelines locally. The build path calls into the same codepath with two differences:

| Step | `hm run` mode | `hm dev up` build mode |
|---|---|---|
| Final action | report run result | `commit_container` → tag `hm-build-<wt>-<slug>:<chain-key>` |
| Stdout target | user-facing run UI | log mux as `[slug build]` lines |
| Cleanup | always rm one-shot container | rm one-shot container; tagged image survives |

Single new function:

```rust
pub async fn build_image_from_pipeline(
    docker: &DockerClient,
    pipeline_v0_ir: &PipelineV0,
    image_tag: &str,
    ctx: &Context,
) -> Result<()>;
```

### Field semantics summary

| Field | Resolution |
|---|---|
| `cmd=["pg", "-c", "x"]` | Bollard `Config.cmd` — overrides image's CMD; entrypoint kept. |
| `env={"K": "V"}` | Bollard `Config.env: ["K=V", ...]`. Plain strings. Cross-deploy refs are decoration-time f-strings using `db.name`. |
| `volumes={".": "/workspace"}` | Host path resolved relative to worktree root; passed as `"<host-abs>:<container>[:ro]"`. RO opt-in via container-path suffix `":ro"`. |
| `workdir="/workspace"` | Bollard `Config.working_dir`. |
| `port_mapping={5432: hm.dev.port()}` | Bollard `HostConfig.port_bindings["5432/tcp"] = [{HostPort: ""}]` — daemon assigns ephemeral. |

---

## §4 Lifecycle & signals

### Boot

1. Lock-free. Each session has unique container + network names.
2. Boot levels execute in topo order; failure of any one boot in a level fails the whole `up`. Partial teardown removes containers already started in this session plus the network.
3. Build-chain failures are reported as `[slug build] step X failed: <exit code>` and propagate.

### Steady state

- One log-mux task per session.
- One inspect-poller task at 2 s cadence detects unexpected container exits and logs them; does not tear down others.
- No automatic restarts.

### Teardown

- **First SIGINT/SIGTERM:** orderly teardown.
  - For each container in reverse boot order: `docker stop` (10 s grace → SIGKILL), then `docker rm`.
  - `docker network rm`.
  - Exit 130 (SIGINT) or 143 (SIGTERM).
- **Second SIGINT during teardown:** hard exit (`process::exit(130)`); leftover containers + network are orphaned. User runs `hm dev down` to recover.
- **Process crashes (panic):** rust panic handler flushes a teardown call on best-effort; same recovery via `hm dev down`.

### Orphan recovery

`hm dev down` (no args) lists all containers labelled `harmont.worktree=<current-hash>` and removes them plus any associated networks. Idempotent.

---

## §5 Error handling

All errors follow PRINCIPLES § 5: point precisely, state observed, state fix.

### Decoration-time (raised by `harmont-py`)

```
ValueError: hm.deploy slug must match ^[a-z][a-z0-9-]{0,30}$, got "API Service"
  → rename the slug to a docker-safe form, e.g. "api-service"

ValueError: hm.dev.port() can only appear as a port_mapping value, not as an env value.
  → use a fixed value here, or query the resolved port via
    `hm dev port-of <slug> <container-port>` after `hm dev up`.

ValueError: hm.dev.deploy requires exactly one of `image=` or `from_=`, both were set.
  → pick one. Use `image=` for a published image, `from_=` to build from a Step chain.

RuntimeError: hm.deploy dep cycle: api -> db -> web -> api
  → remove the cycle, or factor shared state into a target.

ValueError: parameter `db` on @hm.deploy("api") has no type annotation. Every
parameter must carry a marker.
  → add `db: hm.Dep[hm.Deployment]` (or `hm.Target[T]`) to inject it,
    or give the parameter a default value.
```

### Runtime (raised by `hm dev`)

```
hm: docker daemon unreachable (Cannot connect to /var/run/docker.sock).
  → start Docker Desktop, or run `sudo systemctl start docker`.
exit 5

hm: pull `postgres:16` failed: manifest unknown
  → check the tag; `docker pull postgres:16` reproduces the failure.
exit 5

hm: build for `api` failed at step `cabal build all` (exit 1)
  → see [api build] log lines above; run `hm run <pipeline>` to debug.
exit 1

hm: slug `redis` not registered in this worktree's .harmont/
  → run `hm dev ls` to see registered slugs.
exit 5

hm: slug `db` matches multiple live sessions in this worktree:
  7a2f91  started 12:00:14  localhost:42173
  c4d8e0  started 12:05:31  localhost:42891
pass `--session <id>` or run `hm dev ls`.
exit 5

hm: slug `db` registered but not running in this worktree.
  → run `hm dev up db` first.
exit 4
```

---

## §6 Testing

### `harmont-py` unit tests (pytest)

`tests/dev/` (new):

- `test_decorator.py` — slug regex, duplicate-slug rejection, dep cycle detection, parameter-marker enforcement, fixture-injection produces a `Deployment` with `.name`.
- `test_port_sentinel.py` — `port()` outside `port_mapping` raises; sentinel equality; `repr`.
- `test_deploy_factory.py` — XOR of `image=` vs `from_=`; port_mapping value-type validation; env value-type validation; cmd coercion to tuple; volume path validation.
- `test_registry_dump.py` — golden JSON for the canonical db+api+web example; non-local entries marked `_unhandled`; deps list reflects fixture graph.
- `test_dump_cli.py` — `python -m harmont.dev --dump-registry` against a temp `.harmont/` writes the expected JSON to stdout.

### `harmont-cli` unit tests (cargo test)

`crates/hm/src/commands/dev/`:

- `registry::tests` — serde round-trip of the v0 schema; unknown drivers parse as `Unhandled`.
- `topo::tests` — boot levels for db→api→web; `--no-deps` prunes correctly; cycle detection (defensive — should already be caught python-side).
- `logmux::tests` — partial-line buffering; ANSI prefix shape; `NO_COLOR` env strips colors.
- `port_of::tests` — single session returns plain int; multiple sessions return ambiguity error; missing slug exits 5; stopped slug exits 4.
- `naming::tests` — worktree-hash stable across invocations; session-id format `[0-9a-f]{6}`.

### `harmont-cli` integration tests (cargo test, feature-gated)

`crates/hm/tests/dev_integration.rs`, gated `--features docker-integration` and skipped when `DOCKER_HOST` unreachable:

- Boot a single `postgres:16` deployment; assert `port-of` returns the inspected port; assert `psql -h localhost -p <port> -U postgres -c 'select 1'` succeeds; teardown removes container + network.
- Boot db+api on bridge net; assert api container can `getent hosts db` and connect via `db:5432`.

### Cross-repo "vibe" check (manual, documented in RELEASING.md)

```bash
# In a temp dir
mkdir -p .harmont && cat > .harmont/pipelines.py <<'EOF'
import harmont as hm

@hm.deploy("hello")
def hello():
    return hm.dev.deploy(
        image="python:3.12-alpine",
        cmd=["python", "-m", "http.server", "5678"],
        port_mapping={5678: hm.dev.port()},
    )
EOF
hm dev up hello &
sleep 2
curl -fsS "http://localhost:$(hm dev port-of hello 5678)" | grep -q "Directory listing"
kill %1; wait
hm dev ls   # should show nothing running
```

---

## Cross-repo file map

### `harmont-py`

```
harmont/
  __init__.py                # re-export hm.deploy, hm.Dep, hm.Deployment, hm.dev
  _deploy.py                 # NEW: Deployment dataclass, top-level decorator,
                             #      Dep[T] marker, dep-graph builder
  _registry.py               # MODIFY: add DEPLOYMENTS dict alongside REGISTRATIONS
  dev/
    __init__.py              # NEW: re-export hm.dev.deploy, hm.dev.port,
                             #      hm.dev.LocalDeployment, hm.dev.dump_registry_json
    __main__.py              # NEW: `python -m harmont.dev --dump-registry` entry
    _deployment.py           # NEW: LocalDeployment dataclass + validation
    _port.py                 # NEW: _PortSentinel + hm.dev.port()
    _factory.py              # NEW: hm.dev.deploy(...) factory
    _registry_dump.py        # NEW: dump_registry_json + JSON serializer

tests/
  dev/
    __init__.py              # NEW
    test_decorator.py        # NEW
    test_port_sentinel.py    # NEW
    test_deploy_factory.py   # NEW
    test_registry_dump.py    # NEW
    test_dump_cli.py         # NEW
```

### `harmont-cli`

```
crates/hm/src/
  cli.rs                     # MODIFY: add Dev(DevCommand) variant + subcommands
  commands/
    mod.rs                   # MODIFY: register dev module
    dev/
      mod.rs                 # NEW: subcommand dispatcher
      registry.rs            # NEW: invoke `python -m harmont.dev` + serde types
      naming.rs              # NEW: worktree-hash, session-id, container/network names
      topo.rs                # NEW: dep-graph topo sort + level grouping
      network.rs             # NEW: create/remove bridge network via bollard
      logmux.rs              # NEW: multi-source line-prefixed colored log stream
      service_spec.rs        # NEW: ServiceSpec + build_spec(reg, ctx, session, net)
      up.rs                  # NEW: orchestrate boot + signal + teardown
      down.rs                # NEW: orphan sweep
      ls.rs                  # NEW: registry walk + docker inspect merge
      logs.rs                # NEW: docker logs --follow shim
      port_of.rs             # NEW: inspect → host port lookup + ambiguity error
      exec.rs                # NEW: docker exec shim w/ TTY
  orchestrator/
    docker_client.rs         # MODIFY: add create_network, remove_network,
                             #         attach_to_network, port_inspect,
                             #         start_service, commit_container
    mod.rs                   # MODIFY: pub fn build_image_from_pipeline

crates/hm/tests/
  dev_integration.rs         # NEW: feature-gated docker integration tests
```

---

## Open items deferred to follow-up specs

- AWS / Fly / k8s drivers — when added, formalize a wire-format JSON IR for deployments and lift driver dispatch out of `hm dev` into a shared layer.
- Pipeline ↔ deployment auto-wiring (test pipelines that require deployments).
- Healthcheck DSL (`hm.dev.healthcheck(cmd=..., interval=...)`).
- Persistent named volumes.
- Daemon-mode `hm dev up --detach`.
- `hm dev up --watch` for hot-reload on `.harmont/*.py` changes.
