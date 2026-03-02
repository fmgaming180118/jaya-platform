# Omniverse Integration (Conceptual)

The JAYA_CORE project plans to leverage NVIDIA's Omniverse platform to supply
rich physical‑world simulations that the digital twin can learn from.  Rather
than embedding the heavy SDK directly into the core, we define an interface
now and postpone actual implementation until the design stabilizes.

The stub module `src.brain_v2.extensions.twin.omniverse` exposes the
following functions:

* `initialize_sdk() -> bool` – attempt to import and configure the Omniverse
  Kit.  Returns `True` on success, `False` otherwise (stub always returns
  `False`).
* `load_scene(path: str) -> bool` – load a scene file.
* `step(actions)` – advance the simulation by one timestep, returning
  observations.
* `shutdown()` – cleanly shut down the SDK.

When the SDK becomes available, this module should be rewritten to call the
real APIs.  Until then, the stub logs warnings so that enabling the omniverse
feature has no runtime cost.

Enabling omniverse support is done by launching the core with the
`--omniverse` command‑line flag; the engine records the request and will pass
it to the twin on initialization.  Without a real SDK the flag has no effect.