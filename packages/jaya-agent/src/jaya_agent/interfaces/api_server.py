"""
FastAPI REST & WebServer Interface for JAYA_AGENT.
Exposes endpoints: /agent/chat, /agent/tools, /agent/voice, and /agent/status.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, Optional, List

from jaya_agent.runtime.agent_loop import AgentLoop
from jaya_agent.runtime.perception import EventType
from jaya_agent.skills.base_skill import SkillRegistry


class ChatRequest(BaseModel):
    prompt: str
    session_id: Optional[str] = "default"


class VoiceRequest(BaseModel):
    transcript: str


def create_api_app(agent_loop: Optional[AgentLoop] = None) -> FastAPI:
    """Factory creating configured FastAPI application for JAYA_AGENT."""
    loop = agent_loop or AgentLoop()
    app = FastAPI(title="JAYA_AGENT API Server", version="1.0.0")

    # Add CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/agent/status")
    async def get_status():
        """Returns health, working memory count, and system status."""
        return {
            "ok": True,
            "working_memory_count": len(loop.working_memory),
            "teacher_active": loop.teacher is not None,
            "registered_tools_count": len(SkillRegistry.get_all_tool_schemas())
        }

    @app.get("/agent/tools")
    async def get_tools():
        """Returns all Hermes-compatible JSON tool schemas."""
        return {
            "ok": True,
            "tools": SkillRegistry.get_all_tool_schemas()
        }

    @app.post("/agent/chat")
    async def chat_endpoint(req: ChatRequest):
        """Chat endpoint processing user prompt through AgentLoop."""
        if not req.prompt:
            raise HTTPException(status_code=400, detail="Prompt is required.")
        res = loop.process_step(req.prompt, event_type=EventType.TEXT)
        return {
            "ok": True,
            "result": res
        }

    @app.post("/agent/voice")
    async def voice_endpoint(req: VoiceRequest):
        """Voice endpoint processing STT transcript."""
        if not req.transcript:
            raise HTTPException(status_code=400, detail="Transcript is required.")
        res = loop.process_step(req.transcript, event_type=EventType.VOICE)
        return {
            "ok": True,
            "result": res
        }

    return app
