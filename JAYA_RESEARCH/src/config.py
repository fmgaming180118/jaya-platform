import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Centralized Configuration Manager for JAYA"""
    
    # Base Directories — selalu absolut dari lokasi config.py
    BASE_DIR = Path(__file__).resolve().parent.parent   # JAYA_RESEARCH/
    DATA_DIR = Path(os.getenv("JAYA_DATA_DIR", "")).resolve() if os.getenv("JAYA_DATA_DIR") else (BASE_DIR / "data")

    # Ensure base data dir exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _env(key: str, default) -> str:
        """Ambil env var; jika kosong/tidak ada, gunakan default."""
        v = os.getenv(key, "").strip()
        return str(Path(v).resolve()) if v else str(default)
    
    # ==========================================
    # API Endpoints & Keys
    # ==========================================
    NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
    NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
    NVIDIA_VLM_ENDPOINT = os.getenv("NVIDIA_VLM_ENDPOINT", "https://integrate.api.nvidia.com/v1/chat/completions")
    NVIDIA_LLAMA31_BASE_URL = os.getenv("NVIDIA_LLAMA31_BASE_URL", "https://integrate.api.nvidia.com/v1")
    
    SEMANTIC_SCHOLAR_BASE_URL = os.getenv("SEMANTIC_SCHOLAR_BASE_URL", "https://api.semanticscholar.org/graph/v1/paper")
    
    # ==========================================
    # RAG Settings
    # ==========================================
    RAG_CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "512"))
    RAG_CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "128"))
    NVIDIA_EMBEDDING_MODEL = os.getenv("NVIDIA_EMBEDDING_MODEL", "nvidia/nv-embedqa-e5-v5")
    RAG_EMBED_BATCH_SIZE = int(os.getenv("RAG_EMBED_BATCH_SIZE", "32"))
    RAG_EMBED_DIMENSION = int(os.getenv("RAG_EMBED_DIMENSION", "1024"))
    RAG_RERANK_ENABLED = os.getenv("RAG_RERANK_ENABLED", "false").lower() == "true"

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
