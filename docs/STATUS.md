# Current Status

Status: **pre-release research prototype**.

## Verified

- Research API phase-A test: 79 tests passed in the current workspace.
- Runtime data, logs, databases, and local provider configuration are ignored by
  Git.
- Optional digital-twin behavior is disabled by default and bounded when enabled.

## Open release blockers

- Root `pyproject.toml` is aligned with the proprietary license and Hatch wheel configuration.
- Public documentation validation passes for the reduced operational documentation set.
- Internal prompts, 40-pillar construction records, and Core/Mesh blueprints are
  excluded from the public snapshot.
- A bounded, non-root API container baseline with healthcheck is available in `docker/`.
- Python dependency resolution is recorded in `uv.lock`.
- UI clean install, lint, contract tests, production build, and high-severity
  dependency audit pass.
- Docker API image builds successfully and a bounded container smoke test
  confirms 1 GiB memory, 1 CPU, and 128 PID limits.
- Clean-clone installation with `uv sync --locked` passes on the release branch.
- Production deployment, authentication, observability, backup, and rollback
  still need execution evidence; the container files are a baseline, not proof.
- Full UI and cross-package release validation is pending.
