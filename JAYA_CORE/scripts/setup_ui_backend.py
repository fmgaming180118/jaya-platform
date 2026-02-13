import os
from pathlib import Path

# Define structure
STRUCTURE = {
    "src/network": [
        "research_api.py",  # FastAPI entry point
        "api_models.py",    # Pydantic models
    ],
    "src/research": [
        "video_processor.py", # Adapter for Video Blueprint
        "youtube_loader.py",  # Youtube transcript/download
        "graph_engine.py",    # Knowledge Graph logic
    ],
    "ui": [], # Frontend root
}

def create_structure():
    base_dir = Path("d:/Kampus/coba-coba/jaya-research")
    
    for folder, files in STRUCTURE.items():
        folder_path = base_dir / folder
        os.makedirs(folder_path, exist_ok=True)
        print(f"Created: {folder}")
        
        for file in files:
            file_path = folder_path / file
            if not file_path.exists():
                with open(file_path, 'w') as f:
                    if file.endswith('.py'):
                        f.write(f'"""\nAuto-generated: {file}\n"""\n')
                print(f"  Created file: {file}")
            else:
                print(f"  Skipped (exists): {file}")

if __name__ == "__main__":
    create_structure()
