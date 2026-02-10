import os
import json
import shutil
from pathlib import Path
from typing import List, Dict, Optional

class WorkspaceManager:
    """
    Manages Research Workspaces (Rooms).
    Each workspace has its own vector store and knowledge graph.
    """
    def __init__(self, base_dir="data/workspaces"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.current_workspace = "default"
        self._ensure_workspace("default")

    def _ensure_workspace(self, name: str):
        """Creates workspace directory if it doesn't exist."""
        ws_path = self.base_dir / name
        ws_path.mkdir(parents=True, exist_ok=True)
        
        # Create metadata file
        meta_path = ws_path / "metadata.json"
        if not meta_path.exists():
            with open(meta_path, 'w') as f:
                json.dump({
                    "name": name,
                    "created_at": __import__('time').time(),
                    "description": f"Workspace for {name}"
                }, f)

    def create_workspace(self, name: str, description: str = "") -> Dict:
        """Creates a new workspace."""
        # Sanitize name (simple version)
        safe_name = "".join([c if c.isalnum() else "_" for c in name]).lower()
        ws_path = self.base_dir / safe_name
        
        if ws_path.exists():
            return {"status": "error", "message": "Workspace already exists"}
            
        self._ensure_workspace(safe_name)
        
        # Update metadata description
        with open(ws_path / "metadata.json", 'w') as f:
            json.dump({
                "name": name,
                "id": safe_name,
                "created_at": __import__('time').time(),
                "description": description
            }, f)
            
        return {"status": "success", "id": safe_name, "path": str(ws_path)}

    def list_workspaces(self) -> List[Dict]:
        """Lists all available workspaces."""
        workspaces = []
        for item in self.base_dir.iterdir():
            if item.is_dir() and (item / "metadata.json").exists():
                try:
                    with open(item / "metadata.json", 'r') as f:
                        meta = json.load(f)
                        workspaces.append(meta)
                except:
                    workspaces.append({"id": item.name, "name": item.name})
        return workspaces

    def get_paths(self, workspace_id: str) -> Dict[str, str]:
        """Returns paths for vector store and graph for a given workspace."""
        ws_path = self.base_dir / workspace_id
        if not ws_path.exists():
            raise ValueError(f"Workspace {workspace_id} not found")
            
        return {
            "vector_store": str(ws_path / "vector_store.json"),
            "knowledge_graph": str(ws_path / "knowledge_graph.json")
        }
