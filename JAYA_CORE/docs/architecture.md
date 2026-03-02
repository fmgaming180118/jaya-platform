# JAYA_CORE Architecture (v16)

The central component of the JAYA project is the `JAYA_CORE` package, which
contains a lightweight semi‑AGI "liquid brain" designed for resource‑constrained
execution. Core pillars include:

* **Sparse Gating Engine** — top‑k sparse ternary network runtime.
* **Hardware binding & protection** — immutable identifiers, cryptographic
  skin, and environment locking.
* **Twin Protocol** — basic networking allowing multiple instances to verify
  one another.

## Digital Twin Subsystem (Optional)

To support self‑improvement, the core now provides an **optional digital twin
extension**.  When enabled with `--enable-twin`, the engine loads
`src.brain_v2.extensions.twin.CoreTwin` which runs a minimal background loop
and exposes a simple `run_experiment()` API.  The twin is deliberately kept
lightweight; it does not pull in research‑oriented dependencies.

The engine exposes two helper methods to interact with the twin:

* `engine.request_twin_action(config: dict)` — fire an experiment.
* `engine.receive_twin_feedback(result)` — ingest results for possible
  weight/config adjustments.

## Omniverse Hook (Conceptual)

We provide a stubbed `src.brain_v2.extensions.twin.omniverse` module that
defines a stable interface for future physical‑world simulation support.  At
present the functions log warnings and return failure; when the NVIDIA
Omniverse SDK is later integrated, this module will be replaced with a real
implementation.  Enabling the omniverse flag (`--omniverse`) simply informs
the engine to attempt initialization.

The core package remains fully functional without the twin or Omniverse
support active, ensuring it can "run in any condition" as per the project
vision.