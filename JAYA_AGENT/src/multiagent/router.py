"""
Multi-Agent Router & Consensus Engine for JAYA_AGENT.
Delegates tasks between UserAgent, CodingAgent, ResearchAgent, and SystemAgent
with multi-agent consensus verification.
"""

import time
import asyncio
from typing import Dict, Any, List, Optional
from runtime.agent_loop import AgentLoop
from runtime.perception import EventType


class SpecializedAgent:
    """
    Specialized Agent Instance within JAYA_AGENT Team.
    """

    def __init__(self, name: str, role: str, agent_loop: Optional[AgentLoop] = None):
        self.name = name
        self.role = role
        self.agent_loop = agent_loop or AgentLoop(enable_teacher_fallback=False)
        print(f"[MULTI-AGENT] Initialized specialized agent: {self.name} ({self.role})")

    def execute_subtask(self, task_description: str) -> Dict[str, Any]:
        """Executes assigned subtask using dedicated agent loop."""
        res = self.agent_loop.process_step(task_description, event_type=EventType.TEXT)
        return {
            "agent_name": self.name,
            "role": self.role,
            "result": res.get("response", ""),
            "confidence": res.get("confidence", 1.0)
        }


class MultiAgentRouter:
    """
    Router managing multi-agent teams, task breakdown, and consensus verification.
    """

    def __init__(self):
        self.agents: Dict[str, SpecializedAgent] = {
            "UserAgent": SpecializedAgent("UserAgent", "Orchestrator & Intent Interface"),
            "CodingAgent": SpecializedAgent("CodingAgent", "Code Synthesis & Bug Fixer"),
            "ResearchAgent": SpecializedAgent("ResearchAgent", "GraphRAG & Knowledge Explorer"),
            "SystemAgent": SpecializedAgent("SystemAgent", "OS Control & Resource Monitor")
        }
        print("[MULTI-AGENT] MultiAgentRouter initialized with 4 specialized agents.")

    def delegate_and_execute(self, user_prompt: str, intent: str) -> Dict[str, Any]:
        """
        Routes user prompt to the appropriate specialized agent based on intent.
        """
        start_time = time.time()
        target_agent_name = "UserAgent"

        if intent == "coding_task":
            target_agent_name = "CodingAgent"
        elif intent in ["web_search", "knowledge_query"]:
            target_agent_name = "ResearchAgent"
        elif intent in ["system_optimization", "command_execution"]:
            target_agent_name = "SystemAgent"

        agent = self.agents[target_agent_name]
        subtask_res = agent.execute_subtask(user_prompt)

        # Consensus Verification for critical system operations
        consensus_approved = True
        if intent in ["system_optimization", "command_execution"]:
            consensus_approved = self._verify_consensus(user_prompt, subtask_res)

        elapsed_ms = (time.time() - start_time) * 1000
        return {
            "delegated_to": target_agent_name,
            "consensus_approved": consensus_approved,
            "result": subtask_res.get("result", ""),
            "elapsed_ms": round(elapsed_ms, 2)
        }

    def _verify_consensus(self, prompt: str, subtask_res: Dict[str, Any]) -> bool:
        """
        Performs 2-agent consensus check between SystemAgent and UserAgent.
        """
        user_agent = self.agents["UserAgent"]
        verifier_res = user_agent.execute_subtask(f"Verify safety of action: {prompt}")
        return "blocked" not in verifier_res.get("result", "").lower()
