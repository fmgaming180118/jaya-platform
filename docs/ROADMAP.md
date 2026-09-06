# Roadmap

## Release hardening

1. Align root README and root package metadata with the proprietary license.
2. Complete canonical documentation and make the documentation validator pass.
3. Remove remaining default credentials and add negative tests for secret use.
4. Pin Python dependencies and verify a clean-clone installation.
5. Add a reproducible backend/frontend deployment with health checks and secret
   management.
6. Run UI, API, security, boundary, and rollback checks in CI.

A production label is allowed only after every release-hardening item has
executable evidence attached to the release.
