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