
from AppOpener import open as app_opener
import logging
from pydantic import BaseModel, Field
from src.tools.base import BaseTool

logger = logging.getLogger("Tool:OpenApp")

class OpenAppInput(BaseModel):
    app_name: str = Field(..., description="The name of the application to open (e.g., 'notepad', 'spotify').")

class OpenAppTool(BaseTool):
    @property
    def name(self) -> str:
        return "system_open_app"

    @property
    def description(self) -> str:
        return "Opens a desktop application by name."

    @property
    def parameters(self):
        return OpenAppInput

    def execute(self, app_name: str) -> str:
        logger.info(f"Opening App: {app_name}")
        try:
            app_opener(app_name, match_closest=True, output=False)
            return f"Opening {app_name}..."
        except Exception as e:
            return f"Failed to open {app_name}: {e}"
