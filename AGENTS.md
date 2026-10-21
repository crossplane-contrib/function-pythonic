# AGENTS.md

This file provides guidance to AI coding agents working with code in this repository.

## Commands

Managed with `uv`; tasks are defined with poethepoet in `pyproject.toml`.

- `uv run poe generate-protoc` — **required before tests or builds on a fresh checkout.** `src/crossplane/pythonic/proto/v1/run_function_pb2*` are generated from `run_function.proto` and gitignored.
- `uv run poe test` — full suite, stops on first failure, coverage to `reports/`.
- Single test: `uv run pytest tests/test_fn.py -k <case-stem>` (parametrized ids are the YAML file stems, e.g. `-k conditions`).
- `uv run ruff format` / `uv run ruff check` — CI runs `ruff format --diff` and `ruff check`; both must pass.
- Local render: `uv run function-pythonic render xr.yaml composition.yaml` (the second arg may instead be a `module.Class` path; `--kube-context` pulls required resources/connections from a live cluster). Each `examples/*/render.sh` runs this; `examples/run-all.sh` runs them all.

## Test layout

- `tests/test_fn.py` — each `tests/fn_cases/*.yaml` holds a `request` and the expected `response` delta; the harness merges them over a default request/response and calls `FunctionRunner.RunFunction` directly.
- `tests/test_examples.py` — renders every `examples/**/xr.yaml` (with sibling `composition.yaml`, `observed.yaml`, `resources.yaml`) and compares against `tests/examples/<path>.yaml`. Regenerate expected output with `PYTEST_GENERATE_EXPECTED=true uv run pytest tests/test_examples.py`, then review the diff. A `tests/examples/<name>.python-path` file adds example dirs to `sys.path` for that render.
- `tests/test_protobuf_messages.py` compiles `tests/protobuf/pytest.proto` at test time.

## Architecture

The function is a gRPC server (`grpc.py`) wrapping `function.FunctionRunner`. CLI entry is `main.py`, which registers subcommands `grpc`, `render`, and `version`.

Request flow in `FunctionRunner.run_function`:
1. The step input `composite` is either an inline script (contains a newline → `exec`'d, must define exactly one `BaseComposite` subclass) or a dotted `module.Class` path imported via `importlib`. Classes are cached in `self.clazzes` keyed by that string; `invalidate_module` clears entries when package sources change. `inlined` input instead reads the script from the XR's `spec.<inlined>`. No observed composite means it runs as a Crossplane Operation.
2. Per-step iteration state is kept in the response context under `_pythonic[<step>]` (step defaults to a hash of the script).
3. `compose()` runs (sync or async). If it requested required resources/schemas, the function returns early so Crossplane can supply them; otherwise it processes Usages, then unknowns, then auto-ready.

Key modules:
- `protobuf.py` — the "pythonic" layer: `Message`/`MapMessage`/`RepeatedMessage`/`Value` wrap protobuf messages and `google.protobuf.Struct` so attribute access auto-creates paths. Reading a field that does not exist yet yields an *unknown* value rather than raising; this is the basis of automatic dependency ordering.
- `composite.py` — the user-facing API (`BaseComposite`, `Resources`/`Resource`, `Requireds`, `Schemas`, `Conditions`, `Results`, connections, TTL, ready). See `docs/composite.md` and `docs/protobuf.md`.
- `function.py` `process_unknowns` — composed resources containing unknown values are withheld from desired state until their inputs exist; if an already-created resource becomes unknown, behavior follows `unknownsFatal` (per-resource `None` inherits the composite's; the composite defaults to `False`, i.e. fall back to observed values). `process_usages` generates Crossplane Usage resources.
- `auto_ready.py` — readiness heuristics used when a resource's `ready` isn't set explicitly.
- `packages.py` — optional kopf operator (`packages` extra) that watches labelled ConfigMaps/Secrets/EnvironmentConfigs/Compositions (`function-pythonic.package` label), writes their python sources into a packages dir on `sys.path`, and invalidates cached classes.
- `render.py` — local equivalent of `crossplane render`. Per pipeline step it re-runs the function (up to 5 rounds) while it keeps requesting new required resources/schemas, mirroring Crossplane's requirements loop; live lookups go through `kr8s`.

`--crossplane-v1` switches behaviors for Crossplane v1 (e.g. connection details handling); tests opt in via `v1: true` in fn_case YAML.

## Packaging

`package/crossplane.yaml` and `package/input-definition.yaml` define the xpkg; `Dockerfile` copies `dist/*.whl` (so run `uv build` first) and installs it with the `packages` and `pip-install` extras; the entrypoint is `function-pythonic grpc` on port 9443. CI rewrites the `pyproject.toml` version at build time — leave it at `0.0.0`.
