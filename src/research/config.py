"""
Configuration management for JAYA Research Assistant
"""
import os
import yaml
from pathlib import Path
from typing import Dict, Any

class ResearchConfig:
    """Research Assistant Configuration Manager"""
    
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.path.join(
                Path(__file__).parent.parent.parent,
                "configs",
                "research_config.yaml"
            )
        
        self.config_path = config_path
        self.config = self.load_config()
    
    def load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def get(self, key: str, default=None):
        """Get configuration value by dot-notation key"""
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        
        return value if value is not None else default
    
    @property
    def max_queries(self) -> int:
        return self.get('research.max_queries', 10)
    
    @property
    def max_iterations(self) -> int:
        return self.get('research.max_iterations', 3)
    
    @property
    def reasoning_model(self) -> str:
        return self.get('models.reasoning.name')
    
    @property
    def writing_model(self) -> str:
        return self.get('models.writing.name')
    
    @property
    def embedding_model(self) -> str:
        return self.get('models.embedding.name')
    
    @property
    def reports_dir(self) -> str:
        return self.get('output.reports_dir', 'reports')
    
    def get_prompt(self, prompt_name: str, **kwargs) -> str:
        """Get and format prompt template"""
        template = self.get(f'prompts.{prompt_name}', '')
        return template.format(**kwargs)


# Global config instance
_config = None

def get_config() -> ResearchConfig:
    """Get global config instance"""
    global _config
    if _config is None:
        _config = ResearchConfig()
    return _config
