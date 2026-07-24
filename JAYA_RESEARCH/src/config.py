import os
import yaml
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def _load_yaml_config() -> dict:
    """Helper to load root or local nvidia_nim_config.yaml."""
    base_dir = Path(__file__).resolve().parent.parent
    root_dir = base_dir.parent

    yaml_candidates = [
        root_dir / "nvidia_nim_config.yaml",
        base_dir / "nvidia_nim_config.yaml",
        base_dir / "config.yaml",
    ]

    for cand in yaml_candidates:
        if cand.exists():
            try:
                with open(cand, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception:
                pass
    return {}


_raw_yaml = _load_yaml_config()
_api_cfg = _raw_yaml.get("api_settings", {})
_models_cfg = _raw_yaml.get("models", {})
_rag_cfg = _raw_yaml.get("rag_settings", {})


class Config:
    """Centralized Configuration Manager for JAYA"""

    # Base Directories
    BASE_DIR = Path(__file__).resolve().parent.parent   # JAYA_RESEARCH/
    ROOT_DIR = BASE_DIR.parent
    DATA_DIR = Path(os.getenv("JAYA_DATA_DIR", "")).resolve() if os.getenv("JAYA_DATA_DIR") else (BASE_DIR / "data")

    # Ensure base data dir exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _env(key: str, default) -> str:
        """Ambil env var; jika kosong/tidak ada, gunakan default."""
        v = os.getenv(key, "").strip()
        return str(Path(v).resolve()) if v else str(default)

    # ==========================================
    # API Endpoints & Keys (Configurable via YAML & Env)
    # ==========================================
    NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
    NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", _api_cfg.get("base_url", "https://integrate.api.nvidia.com/v1"))
    NVIDIA_VLM_ENDPOINT = os.getenv("NVIDIA_VLM_ENDPOINT", _api_cfg.get("vlm_endpoint", "https://integrate.api.nvidia.com/v1/chat/completions"))
    NVIDIA_LLAMA31_BASE_URL = os.getenv("NVIDIA_LLAMA31_BASE_URL", NVIDIA_BASE_URL)

    SEMANTIC_SCHOLAR_BASE_URL = os.getenv("SEMANTIC_SCHOLAR_BASE_URL", "https://api.semanticscholar.org/graph/v1/paper")

    # ==========================================
    # Dynamic NVIDIA NIM Model Registry
    # ==========================================
    NVIDIA_REASONING_MODEL = os.getenv("NVIDIA_REASONING_MODEL", _models_cfg.get("reasoning_model", "nvidia/nemotron-super-120b"))
    NVIDIA_CHAT_MODEL = os.getenv("NVIDIA_CHAT_MODEL", _models_cfg.get("chat_model", "nvidia/nemotron-super-120b"))
    NVIDIA_CODING_MODEL = os.getenv("NVIDIA_CODING_MODEL", _models_cfg.get("coding_model", "nvidia/nemotron-super-120b"))
    NVIDIA_VISION_MODEL = os.getenv("NVIDIA_VISION_MODEL", _models_cfg.get("vision_model", "nvidia/neva-22b"))
    NVIDIA_IMAGE_GEN_MODEL = os.getenv("NVIDIA_IMAGE_GEN_MODEL", _models_cfg.get("image_gen_model", "black-forest-labs/flux.1-dev"))
    NVIDIA_VIDEO_SUMMARY_MODEL = os.getenv("NVIDIA_VIDEO_SUMMARY_MODEL", _models_cfg.get("video_summary_model", "nvidia/video-search-and-summarization"))
    NVIDIA_TTS_MODEL = os.getenv("NVIDIA_TTS_MODEL", _models_cfg.get("tts_model", "nvidia/riva-tts-fastpitch"))
    NVIDIA_STT_MODEL = os.getenv("NVIDIA_STT_MODEL", _models_cfg.get("stt_model", "nvidia/parakeet-ctc-0.6b"))
    NVIDIA_EMBEDDING_MODEL = os.getenv("NVIDIA_EMBEDDING_MODEL", _models_cfg.get("embedding_model", os.getenv("RAG_EMBEDDING_MODEL", "nvidia/nv-embedqa-e5-v5")))
    NVIDIA_RERANK_MODEL = os.getenv("NVIDIA_RERANK_MODEL", _models_cfg.get("rerank_model", "nvidia/nv-rerankqa-mistral-4b-v3"))
    NVIDIA_GUARDRAILS_MODEL = os.getenv("NVIDIA_GUARDRAILS_MODEL", _models_cfg.get("guardrails_model", "nvidia/llama-guard-3-8b"))

    # ==========================================
    # RAG Settings
    # ==========================================
    RAG_CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", str(_rag_cfg.get("chunk_size", 512))))
    RAG_CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", str(_rag_cfg.get("chunk_overlap", 128))))
    RAG_EMBED_BATCH_SIZE = int(os.getenv("RAG_EMBED_BATCH_SIZE", str(_rag_cfg.get("embed_batch_size", 32))))
    RAG_EMBED_DIMENSION = int(os.getenv("RAG_EMBED_DIMENSION", str(_rag_cfg.get("embed_dimension", 1024))))
    RAG_RERANK_ENABLED = os.getenv("RAG_RERANK_ENABLED", str(_rag_cfg.get("rerank_enabled", False))).lower() == "true"

    # ==========================================
    # RAG & Memory Paths
    # ==========================================
    VECTOR_STORE_PATH     = _env.__func__("VECTOR_STORE_PATH",     DATA_DIR / "vector_store.json")
    EVOLUTION_MEMORY_PATH = _env.__func__("EVOLUTION_MEMORY_PATH", DATA_DIR / "evolution_memory.json")
    DISCOVERY_MEMORY_PATH = _env.__func__("DISCOVERY_MEMORY_PATH", DATA_DIR / "discovery_memory.json")
    KNOWLEDGE_GRAPH_PATH  = _env.__func__("KNOWLEDGE_GRAPH_PATH",  DATA_DIR / "knowledge_graph.json")
    NATIVE_MEMORY_PATH    = _env.__func__("NATIVE_MEMORY_PATH",    DATA_DIR / "native_memory.json")
    EVOLUTION_BACKUPS_DIR = _env.__func__("EVOLUTION_BACKUPS_DIR", DATA_DIR / "evolution" / "backups")
    LANGUAGE_EVOLUTION_DIR= _env.__func__("LANGUAGE_EVOLUTION_DIR",DATA_DIR / "language_evolution")
    CRUCIBLE_DIR          = _env.__func__("CRUCIBLE_DIR",          DATA_DIR / "crucible")

    # ==========================================
    # Modality Paths (Video & Voice)
    # ==========================================
    VIDEO_CACHE_DIR = str(Path(os.getenv("VIDEO_CACHE_DIR", DATA_DIR / "video_cache")))
    VOICE_PROFILES_DIR = str(Path(os.getenv("VOICE_PROFILES_DIR", DATA_DIR / "voice_profiles")))
    VOICE_SAMPLES_DIR = str(Path(os.getenv("VOICE_SAMPLES_DIR", DATA_DIR / "voice_samples")))
    VOICE_MODELS_DIR = str(Path(os.getenv("VOICE_MODELS_DIR", DATA_DIR / "models")))

    # ==========================================
    # Academic & Tools
    # ==========================================
    WORKSPACES_DIR = str(Path(os.getenv("WORKSPACES_DIR", DATA_DIR / "workspaces")))
    EXPERIMENTS_DIR = str(Path(os.getenv("EXPERIMENTS_DIR", DATA_DIR / "experiments")))
    PAPERS_TEMP_DIR = str(Path(os.getenv("PAPERS_TEMP_DIR", DATA_DIR / "papers_temp")))
    SEED_DATASET_PATH = str(Path(os.getenv("SEED_DATASET_PATH", DATA_DIR / "seed_dataset.json")))
    TOKENIZER_PATH = str(Path(os.getenv("TOKENIZER_PATH", DATA_DIR / "tokenizer.json")))


# Global instance for easy access
config = Config()
