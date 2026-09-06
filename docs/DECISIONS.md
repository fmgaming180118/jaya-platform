# Architecture Decisions

## Public boundary

`jaya-research` is a public proprietary release. The private `jaya-platform`
workspace is not a runtime or source dependency.

## Evidence boundary

Research may produce evidence artifacts, but it must not directly modify Core,
install runtime changes, or promote model updates. Promotion requires the gates
in [GOVERNANCE.md](GOVERNANCE.md).

## Optional capabilities

Provider, voice, OCR, GPU, and autonomous capabilities remain optional and are
disabled or bounded by default when their configuration is absent.
