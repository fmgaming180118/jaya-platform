# Validation Debugging Script

Run this to check pillar statuses from the contract source of truth:

```bash
python -c "
import yaml
with open('packages/jaya-core/src/jaya_core/contracts/40_pillars.yaml') as f:
    data = yaml.safe_load(f)
for p in data:
    print(f'{p[\"id\"]:2d} | {p[\"name\"]:30s} | {p[\"status\"]}')
"
```

## Expected Output Format
```
 1 | Pure Logic                   | VERIFIED
 2 | Resource Aware               | VERIFIED
 3 | Active Dreaming              | IMPLEMENTED_LOCAL
 4 | Multimodal Reflex            | IMPLEMENTED_LOCAL
 5 | Logical Homeostasis          | VERIFIED
 6 | Stochastic Spontaneity       | NOT_IMPLEMENTED
 7 | Cognitive Silence            | NOT_IMPLEMENTED
...
```

## Usage
Run after each pillar update to verify contract sync before running validators.
