# Architecture

The repository is a monorepo with public package boundaries:

- `packages/jaya-research`: ingestion, retrieval, evidence, API, and UI.
- `packages/jaya-core`: cognitive runtime contracts used by the Research package.
- `packages/jaya-agent`: task and tool orchestration contracts.
- `packages/jaya-os`: runtime and sandbox adapters.
- `native`: optional performance components.

Research output is evidence-oriented. It must not directly mutate Core source,
install artifacts, or promote model changes. Integrations use package APIs,
configuration, or explicit artifacts.

The private `jaya-platform` directory is an experiment workspace and is not an
architectural dependency of this repository.
