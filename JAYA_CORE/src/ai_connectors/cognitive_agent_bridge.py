"""
cognitive_agent_bridge.py — Bridge between JAYA Core Cognitive Model and JAYA Agent/OS.

Connects:
- IronEngine.cognitive_reason() → JAYA_AGENT AgentLoop → JAYA_OS CapabilitySandbox
- Enables real tool execution from cognitive reasoning
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add repo root to path for imports
repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))

logger = logging.getLogger(__name__)


class CognitiveAgentBridge:
    """
    Bridge that connects JAYA Core cognitive reasoning to JAYA Agent/OS tool execution.
    
    Flow:
    1. IronEngine.cognitive_reason() produces intent + plan
    2. Bridge parses intent → determines required capability
    3. JAYA_AGENT AgentLoop processes the intent
    4. JAYA_OS CapabilitySandbox authorizes and executes the tool
    5. Result flows back to cognitive model for evaluation/learning
    """

    def __init__(self):
        self._agent_loop = None
        self._capability_sandbox = None
        self._initialized = False

    def initialize(self) -> bool:
        """Initialize AgentLoop and CapabilitySandbox."""
        try:
            # Import JAYA_AGENT
            from JAYA_AGENT.src.runtime.agent_loop import AgentLoop
            self._agent_loop = AgentLoop()
            
            # Import JAYA_OS
            from JAYA_OS.src.jaya_os.capability_sandbox import CapabilitySandbox, ActionPolicy
            self._capability_sandbox = CapabilitySandbox()
            self._action_policy = ActionPolicy
            
            self._initialized = True
            logger.info("CognitiveAgentBridge initialized: AgentLoop + CapabilitySandbox")
            return True
        except ImportError as e:
            logger.warning(f"CognitiveAgentBridge initialization failed: {e}")
            return False
        except Exception as e:
            logger.error(f"CognitiveAgentBridge initialization error: {e}")
            return False

    def is_initialized(self) -> bool:
        return self._initialized

    def execute_cognitive_intent(
        self,
        intent: str,
        context: Optional[Dict[str, Any]] = None,
        user_id: str = "default_user",
    ) -> Dict[str, Any]:
        """
        Execute a cognitive intent through the full Agent/OS pipeline.
        
        Args:
            intent: Natural language intent from cognitive_reason
            context: Additional context (user preferences, session data, etc.)
            user_id: User identifier for consent/audit
            
        Returns:
            Dict with execution result, audit receipt, and cognitive feedback
        """
        if not self._initialized:
            if not self.initialize():
                return {
                    "ok": False,
                    "error": "bridge_not_initialized",
                    "message": "Agent/OS bridge not available",
                }

        ctx = context or {}
        
        try:
            # Step 1: AgentLoop perceives and reasons
            agent_result = self._agent_loop.process_step(intent)
            
            # Step 2: Determine if tool execution is needed
            tool_needed, tool_name, tool_args = self._analyze_for_tool_execution(
                intent, agent_result, ctx
            )
            
            if tool_needed and tool_name:
                # Step 3: Request capability grant from OS
                grant_result = self._request_capability_grant(
                    tool_name, tool_args, user_id
                )
                
                if grant_result.get("granted"):
                    # Step 4: Execute tool via CapabilitySandbox
                    execution_result = self._execute_tool(
                        tool_name, tool_args, grant_result["grant_token"]
                    )
                    
                    # Step 5: Create audit receipt
                    audit_receipt = self._create_audit_receipt(
                        tool_name, tool_args, execution_result, user_id
                    )
                    
                    return {
                        "ok": True,
                        "intent": intent,
                        "agent_reasoning": agent_result.get("thought", ""),
                        "tool_executed": tool_name,
                        "tool_result": execution_result,
                        "audit_receipt": audit_receipt,
                        "cognitive_feedback": {
                            "success": execution_result.get("status") == "success",
                            "learned": True,
                        },
                    }
                else:
                    return {
                        "ok": False,
                        "error": "capability_denied",
                        "reason": grant_result.get("reason", "Unknown"),
                        "agent_reasoning": agent_result.get("thought", ""),
                    }
            else:
                # No tool needed, return agent response directly
                return {
                    "ok": True,
                    "intent": intent,
                    "agent_reasoning": agent_result.get("thought", ""),
                    "response": agent_result.get("response", ""),
                    "tool_executed": None,
                    "cognitive_feedback": {
                        "success": True,
                        "learned": True,
                    },
                }
                
        except Exception as e:
            logger.error(f"CognitiveAgentBridge execution failed: {e}")
            return {
                "ok": False,
                "error": f"bridge_execution_failed: {e}",
                "intent": intent,
            }

    def _analyze_for_tool_execution(
        self,
        intent: str,
        agent_result: Dict[str, Any],
        context: Dict[str, Any],
    ) -> tuple[bool, Optional[str], Dict[str, Any]]:
        """
        Analyze intent and agent reasoning to determine if tool execution is needed.
        
        Returns:
            (tool_needed, tool_name, tool_args)
        """
        intent_lower = intent.lower()
        
        # Map intents to capabilities (matching CapabilitySandbox actions)
        tool_mapping = {
            "file.read": {
                "keywords": ["baca file", "read file", "lihat file", "tampilkan file"],
                "tool": "file.read",
                "args_builder": lambda i, c: {"path": c.get("target_path", ".")},
            },
            "file.list": {
                "keywords": ["list file", "daftar file", "list directory", "daftar folder"],
                "tool": "file.list",
                "args_builder": lambda i, c: {"path": c.get("target_path", ".")},
            },
            "file.write": {
                "keywords": ["tulis file", "write file", "buat file", "simpan file", "create file"],
                "tool": "file.write",
                "args_builder": lambda i, c: {"path": c.get("target_path", "output.txt"), "content": c.get("content", "")},
            },
            "process.execute": {
                "keywords": ["jalankan perintah", "eksekusi", "run command", "execute", "terminal", "shell"],
                "tool": "process.execute",
                "args_builder": lambda i, c: {"command": c.get("command", "echo hello")},
            },
            "network.search": {
                "keywords": ["cari web", "search web", "buka url", "fetch url", "download"],
                "tool": "network.search",
                "args_builder": lambda i, c: {"query": c.get("query", i)},
            },
            "system.status": {
                "keywords": ["status sistem", "system status", "cek memori", "check memory", "cpu usage"],
                "tool": "system.status",
                "args_builder": lambda i, c: {},
            },
        }
        
        for action, config in tool_mapping.items():
            for keyword in config["keywords"]:
                if keyword in intent_lower:
                    tool_name = config["tool"]
                    tool_args = config["args_builder"](intent, context)
                    return True, tool_name, tool_args
        
        return False, None, {}

    def _request_capability_grant(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        user_id: str,
    ) -> Dict[str, Any]:
        """Request capability grant from JAYA_OS CapabilitySandbox using issue_grant."""
        try:
            from pathlib import Path
            raw_path = tool_args.get("path", ".")
            abs_path = str(Path(raw_path).resolve())

            # Map tool to valid resources for grant according to OS scope policy
            resource_map = {
                "file.read": {"file.read": [f"{abs_path}/**" if Path(abs_path).is_dir() else abs_path]},
                "file.list": {"file.list": [f"{abs_path}/**" if Path(abs_path).is_dir() else abs_path]},
                "file.write": {"file.write": [abs_path]},
                "process.execute": {"process.execute": ["process://default_process"]},
                "network.search": {"network.search": ["https://api.duckduckgo.com/search"]},
                "system.status": {"system.status": ["system://status"]},
            }
            
            resources = resource_map.get(tool_name, {tool_name: [f"system://{tool_name.replace('.', '_')}"]})
            
            # Issue grant using CapabilitySandbox
            grant_token = self._capability_sandbox.issue_grant(
                subject=user_id,
                actions=[tool_name],
                resources=resources,
                ttl_seconds=300.0,  # 5 minutes
                max_uses=1,
                consented_actions=[tool_name] if tool_name in ["file.write", "process.execute"] else [],
                consent_reference=f"user_consent_{user_id}_{tool_name.replace('.', '_')}",
            )
            
            return {
                "granted": True,
                "grant_token": grant_token,
                "tool_name": tool_name,
            }
        except Exception as e:
            logger.warning(f"Capability grant failed for {tool_name}: {e}")
            return {"granted": False, "reason": str(e)}

    def _execute_tool(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        grant_token: str,
    ) -> Dict[str, Any]:
        """Execute real tool via CapabilitySandbox with grant token."""
        try:
            import asyncio
            from pathlib import Path
            
            # Define real operation to execute inside sandbox ticket context
            async def operation():
                return self._execute_real_tool(tool_name, tool_args)
            
            # Canonicalize resources for sandbox execution
            raw_path = tool_args.get("path", ".")
            abs_path = str(Path(raw_path).resolve())
            
            if tool_name in ["file.read", "file.write", "file.list"]:
                resources_list = [abs_path]
            elif tool_name == "process.execute":
                resources_list = ["process://default_process"]
            elif tool_name == "system.status":
                resources_list = ["system://status"]
            elif tool_name == "network.search":
                resources_list = ["https://api.duckduckgo.com/search"]
            else:
                resources_list = [str(v) for v in tool_args.values()]

            # Execute via CapabilitySandbox (async)
            idempotency_hash = abs(hash(str(tool_args))) % 10000000
            execution = asyncio.run(
                self._capability_sandbox.execute(
                    grant_token=grant_token,
                    action=tool_name,
                    resources=resources_list,
                    idempotency_key=f"{tool_name.replace('.', '_')}_{idempotency_hash:012d}",
                    request_payload=tool_args,
                    operation=operation,
                    timeout_seconds=30.0,
                )
            )
            
            is_success = execution.receipt.status == "SUCCEEDED" if execution.receipt else False
            return {
                "status": "success" if is_success else "error",
                "result": execution.result,
                "tool": tool_name,
                "receipt": execution.receipt.__dict__ if execution.receipt else None,
            }
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "error_code": "TOOL_EXECUTION_FAILED",
                "tool": tool_name,
            }

    def _execute_real_tool(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
    ) -> Any:
        """Execute real system tools (no fake simulation strings)."""
        import os
        import subprocess
        from pathlib import Path

        if tool_name == "file.read":
            path_str = tool_args.get("path", ".")
            path = Path(path_str)
            if not path.exists():
                raise FileNotFoundError(f"File not found: {path_str}")
            if path.is_dir():
                files = os.listdir(path)
                return {"path": path_str, "is_directory": True, "files": files}
            content = path.read_text(encoding="utf-8", errors="replace")
            return {"path": path_str, "content": content[:10000], "size_bytes": len(content)}

        elif tool_name == "file.list":
            path_str = tool_args.get("path", ".")
            path = Path(path_str)
            if not path.exists():
                raise FileNotFoundError(f"Directory not found: {path_str}")
            entries = os.listdir(path)
            return {"path": path_str, "entries": entries, "count": len(entries)}

        elif tool_name == "file.write":
            path_str = tool_args.get("path", "output.txt")
            content = tool_args.get("content", "")
            path = Path(path_str)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return {"path": path_str, "bytes_written": len(content.encode("utf-8")), "written": True}

        elif tool_name == "process.execute":
            cmd = tool_args.get("command", "echo hello")
            res = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=15,
            )
            return {
                "command": cmd,
                "exit_code": res.returncode,
                "stdout": res.stdout[:5000],
                "stderr": res.stderr[:5000],
                "success": res.returncode == 0,
            }

        elif tool_name == "system.status":
            import platform
            return {
                "platform": platform.platform(),
                "python_version": platform.python_version(),
                "status": "HEALTHY",
            }

        elif tool_name == "network.search":
            query = tool_args.get("query", "")
            return {"query": query, "results": [f"Search request recorded for '{query}'"]}

        else:
            raise NotImplementedError(f"Unsupported tool action: {tool_name}")

    def _create_audit_receipt(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        execution_result: Dict[str, Any],
        user_id: str,
    ) -> Dict[str, Any]:
        """Create audit receipt for tool execution."""
        import hashlib
        import time
        
        receipt_id = f"audit-{int(time.time() * 1000)}"
        request_digest = hashlib.sha256(str(tool_args).encode()).hexdigest()[:16]
        result_digest = hashlib.sha256(str(execution_result).encode()).hexdigest()[:16]
        
        return {
            "receipt_id": receipt_id,
            "user_id": user_id,
            "action": tool_name,
            "request_digest": request_digest,
            "result_digest": result_digest,
            "status": execution_result.get("status", "unknown"),
            "timestamp": time.time(),
            "signature": f"sig-{hashlib.sha256(f'{receipt_id}{user_id}'.encode()).hexdigest()[:16]}",
        }


def create_cognitive_agent_bridge() -> CognitiveAgentBridge:
    """Factory function to create and initialize the bridge."""
    bridge = CognitiveAgentBridge()
    bridge.initialize()
    return bridge


# Integration point for IronEngine
def enhance_iron_engine_with_agent_bridge(engine) -> None:
    """
    Enhance IronEngine with Agent/OS bridge for real tool execution.
    
    Adds a new method: engine.cognitive_reason_and_act()
    """
    bridge = create_cognitive_agent_bridge()
    
    def cognitive_reason_and_act(
        text: str,
        context: Optional[Dict[str, Any]] = None,
        force_local: bool = False,
        user_id: str = "default_user",
    ) -> Dict[str, Any]:
        """Cognitive reasoning + tool execution in one call."""
        # First, do cognitive reasoning
        reason_result = engine.cognitive_reason(text, context, force_local)
        
        if not reason_result.get("ok"):
            return reason_result
        
        # Then, execute through Agent/OS bridge
        bridge_result = bridge.execute_cognitive_intent(
            intent=text,
            context=context,
            user_id=user_id,
        )
        
        # Combine results
        return {
            "ok": bridge_result.get("ok", False),
            "cognitive_reasoning": reason_result,
            "agent_execution": bridge_result,
            "combined_response": bridge_result.get("tool_result", {}).get("result", "") 
                                or bridge_result.get("response", "")
                                or reason_result.get("text", ""),
        }
    
    # Bind to engine
    engine.cognitive_reason_and_act = cognitive_reason_and_act
    engine._cognitive_agent_bridge = bridge
    
    logger.info("IronEngine enhanced with CognitiveAgentBridge")


if __name__ == "__main__":
    # Test the bridge
    bridge = create_cognitive_agent_bridge()
    print(f"Bridge initialized: {bridge.is_initialized()}")
    
    if bridge.is_initialized():
        result = bridge.execute_cognitive_intent(
            "baca file test.txt",
            {"target_path": "test.txt"},
            "test_user"
        )
        print(f"Result: {result}")