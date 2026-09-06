# Acceptance Criteria

A release candidate must satisfy all of the following:

- Clean-clone setup succeeds without `jaya-platform`.
- Backend offline tests pass.
- UI lint, contract tests, and production build pass.
- Documentation and repository-boundary validators pass.
- No tracked secrets, private data, runtime databases, or model weights exist.
- Upload, provider, authentication, and failure-path tests pass.
- Deployment health checks, logs, backup, rollback, and secret rotation are
  exercised.
- Research output retains provenance and is marked for human review where
  evidence is incomplete.
