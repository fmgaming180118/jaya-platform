# JAYA Core

Canonical Python package for JAYA cognitive runtime capabilities.

The dynamic pillar catalog lives in `jaya_core.pillars`. The original forty
pillar IDs remain stable for compatibility, while future pillars are validated
catalog records stored in SQLite. Registering a pillar never activates code;
runtime availability requires a real healthy capability binding.

Example:

```powershell
python -m jaya_core.pillars.cli `
  --db .\var\databases\pillars.db `
  --manifest .\packages\jaya-core\src\jaya_core\contracts\40_pillars.yaml `
  list
```
