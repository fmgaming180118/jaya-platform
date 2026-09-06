# Release Remediation Checklist

- [x] Align root README with the proprietary license.
- [x] Align root `pyproject.toml` with the proprietary license.
- [x] Complete the public documentation validator contract.
- [x] Remove the shell hardcoded vault password.
- [x] Add a Python lockfile.
- [ ] Verify clean-clone installation with `uv sync --locked` after root Hatch fix.
- [x] UI clean install, lint, contract tests, production build, and high-severity
	dependency audit pass.
- [x] Add reproducible backend API deployment assets with healthcheck and resource bounds.
- [x] Build and smoke-test the container on a Docker-enabled host.
- [ ] Verify authentication, secret rotation, upload limits, and rate limits.
- [ ] Run full UI, API, security, boundary, and rollback checks.
- [ ] Attach command output and environment details to the release record.
