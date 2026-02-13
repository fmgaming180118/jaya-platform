
from abc import ABC, abstractmethod
from typing import Dict, Any, Type
from pydantic import BaseModel

class BaseTool(ABC):
    """
    Abstract base class for all tools in the system.
    Each tool must be its own file in src/tools/.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for the tool (e.g., 'system_open_app')"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Natural language description for the LLM"""
        pass

    @property
    def parameters(self) -> Type[BaseModel]:
        """Pydantic model defining the input parameters"""
        return BaseModel

    @abstractmethod
    def execute(self, **kwargs) -> Any:
        """Main execution logic"""
        pass

    def to_schema(self) -> Dict[str, Any]:
        """
        Converts the tool definition to OpenAI/NVIDIA function schema.
        """
        schema = self.parameters.model_json_schema()
        return {
            "name": self.name,
            "description": self.description,
            "parameters": schema
        }
