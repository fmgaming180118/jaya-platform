import os

src_dir = "d:/Kampus/coba-coba/jaya-research/JAYA_RESEARCH/src"

replacements = {
    '"data/vector_store.json"': 'config.VECTOR_STORE_PATH',
    '"data/evolution_memory.json"': 'config.EVOLUTION_MEMORY_PATH',
    '"data/discovery_memory.json"': 'config.DISCOVERY_MEMORY_PATH',
    '"data/knowledge_graph.json"': 'config.KNOWLEDGE_GRAPH_PATH',
    '"data/native_memory.json"': 'config.NATIVE_MEMORY_PATH',
    '"data/video_cache"': 'config.VIDEO_CACHE_DIR',
    '"data/voice_profiles"': 'config.VOICE_PROFILES_DIR',
    '"data/voice_samples"': 'config.VOICE_SAMPLES_DIR',
    '"data/models"': 'config.VOICE_MODELS_DIR',
    '"data/workspaces"': 'config.WORKSPACES_DIR',
    '"data/experiments"': 'config.EXPERIMENTS_DIR',
    '"data/papers_temp"': 'config.PAPERS_TEMP_DIR',
    '"data/seed_dataset.json"': 'config.SEED_DATASET_PATH',
    '"data/tokenizer.json"': 'config.TOKENIZER_PATH',
    '"data/evolution/backups"': 'config.EVOLUTION_BACKUPS_DIR',
    '"data/language_evolution"': 'config.LANGUAGE_EVOLUTION_DIR',
    '"JAYA_RESEARCH/data/crucible"': 'config.CRUCIBLE_DIR',
    '"data/evolution/memory.json"': 'config.EVOLUTION_MEMORY_PATH',
    '"https://integrate.api.nvidia.com/v1"': 'config.NVIDIA_BASE_URL',
    '"https://integrate.api.nvidia.com/v1/chat/completions"': 'config.NVIDIA_VLM_ENDPOINT',
    '"https://api.semanticscholar.org/graph/v1/paper"': 'config.SEMANTIC_SCHOLAR_BASE_URL',
}

for root, dirs, files in os.walk(src_dir):
    for f in files:
        if f.endswith('.py') and f != 'config.py' and f != 'refactor.py':
            filepath = os.path.join(root, f)
            with open(filepath, 'r', encoding='utf-8') as file:
                content = file.read()
            
            modified = False
            for k, v in replacements.items():
                if k in content:
                    content = content.replace(k, v)
                    modified = True
                    
            if modified:
                # Determine import statement based on directory depth
                rel_path = os.path.relpath(src_dir, root)
                if rel_path == '.':
                    import_stmt = 'from config import config\n'
                else:
                    import_stmt = 'import sys, os\nsys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "' + rel_path + '")))\nfrom config import config\n'
                
                if 'from config import config' not in content:
                    content = import_stmt + content
                     
                with open(filepath, 'w', encoding='utf-8') as file:
                    file.write(content)
                print(f"Refactored: {filepath}")
