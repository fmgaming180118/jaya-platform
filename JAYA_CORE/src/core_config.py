"""
JAYA_CORE Centralized Configuration Manager
All secrets and paths must come from environment variables or .env file.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from JAYA_CORE root
_CORE_DIR = Path(__file__).parent.parent.absolute()
load_dotenv(dotenv_path=_CORE_DIR / ".env")


class CoreConfig:
    """Single source of truth for all JAYA_CORE configuration."""

    # ── Sovereign Identity ─────────────────────────────────────────────
    # AES-256 password used to encrypt/decrypt .jay soul files.
    # NEVER hardcode this. Must be set in .env as JAYA_SOUL_PASSWORD.
    SOUL_PASSWORD: str = os.getenv("JAYA_SOUL_PASSWORD", "")

    # Path to the active .jay model file
    MODEL_PATH: str = os.getenv(
        "JAYA_MODEL_PATH",
        str(_CORE_DIR / "JAYA_SOVEREIGN_V18.jay"),
    )

    # ── Data Directories ───────────────────────────────────────────────
    DATA_DIR: Path = Path(os.getenv("JAYA_CORE_DATA_DIR", str(_CORE_DIR / "data")))

    # Pillar 33 — Agentic RAG database
    AGENTIC_RAG_PATH: str = os.getenv(
        "JAYA_AGENTIC_RAG_PATH",
        str(DATA_DIR / "rag_runtime.db"),
    )

    # Pillar 31 — Narrative Continuity persistence
    NARRATIVE_PATH: str = os.getenv(
        "JAYA_NARRATIVE_PATH",
        str(DATA_DIR / "narrative.json"),
    )

    # ── Twin Protocol ──────────────────────────────────────────────────
    # Pillar 30 — shared secret for P2P twin handshakes
    TWIN_SHARED_SECRET: str = os.getenv("JAYA_TWIN_SHARED_SECRET", "")
    # Unique node identifier for this JAYA instance
    NODE_ID: str = os.getenv("JAYA_NODE_ID", "")

    # ── Research Bridge ────────────────────────────────────────────────
    # Path to JAYA_RESEARCH evolution memory for the discovery bridge
    RESEARCH_MEMORY_PATH: str = os.getenv(
        "JAYA_RESEARCH_MEMORY_PATH",
        str(_CORE_DIR.parent / "JAYA_RESEARCH" / "data" / "evolution_memory.json"),
    )

    def validate(self) -> None:
        """Warn on missing critical secrets at startup."""
        if not self.SOUL_PASSWORD:
            import logging
            logging.getLogger("CoreConfig").warning(
                "[SECURITY] JAYA_SOUL_PASSWORD is not set. "
                "The .jay file cannot be decrypted. Set it in JAYA_CORE/.env"
            )


# Global singleton — import this everywhere
core_config = CoreConfig()
