# Product Scope

JAYA Research provides a local-first research workspace for document
ingestion, retrieval, evidence-grounded analysis, knowledge graph exploration,
and bounded research workflows.

## Supported scope

- Research API and web UI in `packages/jaya-research`.
- Offline test mode without external model providers.
- Optional provider integrations configured through environment variables.
- Evidence and workspace boundaries enforced by the Research package.

## Out of scope

- Autonomous self-modification or unattended promotion.
- Production hosting of user data by this repository.
- A guarantee that generated research is correct without human review.
- Runtime dependence on the private `jaya-platform` workspace.
