import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CORE_SOURCE = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SOURCE) not in sys.path:
    sys.path.insert(0, str(CORE_SOURCE))

from jaya_core.brain_v2.engine.runtime import IronEngine


def main() -> int:
    password = os.environ.get("JAYA_SOUL_PASSWORD", "").strip()
    if not password:
        print(
            json.dumps(
                {"status": "MODEL_NOT_CONFIGURED", "missing": ["JAYA_SOUL_PASSWORD"]}
            )
        )
        return 2
    model_path = os.environ.get(
        "JAYA_MODEL_PATH",
        str(ROOT / "data" / "models" / "jaya-core" / "JAYA_SOVEREIGN_V18.jay"),
    )
    engine = IronEngine(model_path=model_path, password=password, enable_twin=False)
    engine.ignite()

    health = engine.healthcheck()
    readiness = engine.readiness_report()
    smoke = engine.execute_intent("open desktop")

    payload = {
        "healthcheck": health,
        "readiness_report": readiness,
        "smoke_test": {
            "ok": bool(smoke.get("ok")),
            "moe_primary_expert": smoke.get("moe_primary_expert"),
            "activation_topk": smoke.get("activation_topk"),
        },
    }
    print(json.dumps(payload, indent=2, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
