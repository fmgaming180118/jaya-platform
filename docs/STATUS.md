# Current Status

Status: **pre-release research prototype**.

## Verified

- Research API phase-A test: 79 tests passed in the current workspace.
- Runtime data, logs, databases, and local provider configuration are ignored by
  Git.
- Optional digital-twin behavior is disabled by default and bounded when enabled.

## Open release blockers

- Root `pyproject.toml` still needs to be aligned with the proprietary license.
- Canonical documentation validation passes for 23 canonical documents and 40 pillar documents.
- A bounded, non-root API container baseline with healthcheck is available in `docker/`.
- Python dependency resolution is recorded in `uv.lock`.
- UI clean install, lint, contract tests, production build, and high-severity
  dependency audit pass.
- Docker API image builds successfully and a bounded container smoke test
  confirms 1 GiB memory, 1 CPU, and 128 PID limits.
- Clean-clone installation is not yet verified with `uv sync --locked`.
- Root meta-package packaging still needs an explicit Hatch wheel selection so
  a plain `uv sync --locked` can install the workspace root.
- Production deployment, authentication, observability, backup, and rollback
  still need execution evidence; the container files are a baseline, not proof.
- Full UI and cross-package release validation is pending.
