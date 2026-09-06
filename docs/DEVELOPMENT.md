# Development

## Local setup

Use Python 3.11+ and Node.js 18+. From the repository root:

```powershell
python -m pip install -r packages/jaya-research/requirements-ci.txt
python -m pytest packages/jaya-research/tests/test_research_api_phase_a.py -q
Set-Location packages/jaya-research/ui
npm ci
npm run lint
npm run build
npm run test:contracts
```

The full `requirements.txt` includes optional provider, audio, OCR, and system
integrations. Install it only when those capabilities are required.

## Required checks before release

- Research offline test suite passes.
- UI lint, contract tests, and production build pass.
- `python scripts/validate_docs.py` passes.
- Repository boundary and security audits pass.
- A clean clone can start without files from `jaya-platform`.
- Provider credentials are supplied through a secret store or environment, not
  committed files.

## Container deployment

The API deployment baseline is in `docker/`. Use
`docker/compose.production.yml` only after replacing all placeholder values in
`.env`. It runs with a non-root user, a read-only root filesystem, bounded
memory/CPU/processes, a persistent data volume, and a healthcheck. Keep port
8000 on loopback behind an authenticated TLS reverse proxy.

Docker image build and a clean-clone smoke test are release evidence and must
run in CI or on a host with Docker installed.

Do not run autonomous loops, self-modification, or promotion without an explicit
operator scope, budget, timeout, audit trail, and kill switch.
