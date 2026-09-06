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
        print("MODEL_NOT_CONFIGURED: JAYA_SOUL_PASSWORD is required", file=sys.stderr)
        return 2
    model_path = os.environ.get(
        "JAYA_MODEL_PATH",
        str(ROOT / "data" / "models" / "jaya-core" / "JAYA_SOVEREIGN_V18.jay"),
    )
    engine = IronEngine(model_path=model_path, password=password, enable_twin=False)
    engine.ignite()

    print("JAYA chat siap. Ketik pertanyaan Anda. Ketik 'exit' atau 'quit' untuk keluar.")
    print(engine.greet())

    while True:
        try:
            text = input("Anda> ").strip()
        except EOFError:
            print("\nMenutup sesi chat JAYA.")
            return 0
        except KeyboardInterrupt:
            print("\nMenutup sesi chat JAYA.")
            return 0

        if not text:
            continue
        if text.lower() in {"exit", "quit"}:
            print("Menutup sesi chat JAYA.")
            return 0

        print(f"JAYA> {engine.chat(text)}")


if __name__ == "__main__":
    raise SystemExit(main())
