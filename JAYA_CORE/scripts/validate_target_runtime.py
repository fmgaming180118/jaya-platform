import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "JAYA_CORE") not in sys.path:
    sys.path.insert(0, str(ROOT / "JAYA_CORE"))

from src.brain_v2.engine.runtime import IronEngine


def main() -> int:
    model_path = str(ROOT / "JAYA_CORE" / "JAYA_SOVEREIGN_V18.jay")
    engine = IronEngine(model_path=model_path, password="x", enable_twin=False)
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
