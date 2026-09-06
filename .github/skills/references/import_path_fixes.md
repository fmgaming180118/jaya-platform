# Import Path Fixing Reference

## Canonical package layout

JAYA memakai Python src layout:

| Package root | Import namespace |
|---|---|
| `packages/jaya-core/src/jaya_core` | `jaya_core` |
| `packages/jaya-agent/src/jaya_agent` | `jaya_agent` |
| `packages/jaya-os/src/jaya_os` | `jaya_os` |
| `packages/jaya-research/src/jaya_research` | `jaya_research` |

Jangan menambah kembali import `JAYA_CORE.src`, `JAYA_RESEARCH.src`, atau
namespace generik seperti `from research ...`.

## Fix pattern

```python
# Legacy
from src.brain_v2.model.readiness import Readiness
from brain_v2.model.nano_artifact import NanoArtifactError

# Canonical
from jaya_core.brain_v2.model.readiness import Readiness
from jaya_core.brain_v2.model.nano_artifact import NanoArtifactError
```

Untuk migrasi mekanis yang dapat diaudit:

```powershell
python scripts/migration/rewrite_monorepo_imports.py --root .
```

## Test command

```powershell
$env:PYTHONPATH='packages/jaya-core/src;packages/jaya-agent/src;packages/jaya-os/src;packages/jaya-research/src'
python -c "import jaya_core, jaya_agent, jaya_os, jaya_research"
```
