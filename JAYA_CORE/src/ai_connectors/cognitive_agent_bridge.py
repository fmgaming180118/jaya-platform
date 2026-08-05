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
                    tool_name, tool_args, user_id, context=ctx
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
                    
                    # P0.5 Fix: ok is True ONLY IF execution_result status is success
                    is_tool_success = execution_result.get("status") == "success"
                    
                    return {
                        "ok": is_tool_success,
                        "intent": intent,
                        "agent_reasoning": agent_result.get("thought", ""),
                        "tool_executed": tool_name,
                        "tool_result": execution_result,
                        "audit_receipt": audit_receipt,
                        "cognitive_feedback": {
                            "success": is_tool_success,
                            "learned": True,
                        },
                        "error": execution_result.get("error") if not is_tool_success else None,
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

    def execute_action_step(
        self,
        step: Any,
        context: Optional[Dict[str, Any]] = None,
        user_id: str = "default_user",
    ) -> Dict[str, Any]:
        """
        Execute a structured ActionStep directly without string keyword matching.
        """
        ctx = context or {}
        action_type = getattr(step, "action_type", "") or getattr(step, "required_capability", "")
        inputs = getattr(step, "inputs", {}) or {}

        # Resolve action_type to tool_name
        tool_name = action_type
        if tool_name not in ["file.read", "file.list", "file.write", "process.execute", "network.search", "system.status"]:
            if "read" in action_type:
                tool_name = "file.read"
            elif "write" in action_type:
                tool_name = "file.write"
            elif "list" in action_type:
                tool_name = "file.list"
            elif "process" in action_type or "exec" in action_type or "run" in action_type:
                tool_name = "process.execute"
            elif "search" in action_type:
                tool_name = "network.search"
            else:
                return {
                    "ok": False,
                    "error": "UNSUPPORTED_ACTION",
                    "action_type": action_type,
                }

        grant_result = self._request_capability_grant(tool_name, inputs, user_id, context=ctx)
        if not grant_result.get("granted"):
            return {
                "ok": False,
                "error": "capability_denied",
                "reason": grant_result.get("reason", "Unknown"),
            }

        execution_result = self._execute_tool(tool_name, inputs, grant_result["grant_token"])
        is_success = execution_result.get("status") == "success"
        audit_receipt = self._create_audit_receipt(tool_name, inputs, execution_result, user_id)

        return {
            "ok": is_success,
            "action_type": action_type,
            "tool_executed": tool_name,
            "tool_result": execution_result,
            "audit_receipt": audit_receipt,
            "cognitive_feedback": {
                "success": is_success,
                "learned": True,
            },
            "error": execution_result.get("error") if not is_success else None,
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
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Request capability grant from JAYA_OS CapabilitySandbox using issue_grant."""
        try:
            from pathlib import Path
            ctx = context or {}
            raw_path = tool_args.get("path", ".")
            
            # Resolve workspace boundary
            workspace_root = repo_root.resolve()
            target_path = (workspace_root / raw_path).resolve()
            abs_path = str(target_path)

            # Map tool to valid resources for grant according to OS scope policy
            resource_map = {
                "file.read": {"file.read": [f"{abs_path}/**" if target_path.is_dir() else abs_path]},
                "file.list": {"file.list": [f"{abs_path}/**" if target_path.is_dir() else abs_path]},
                "file.write": {"file.write": [abs_path]},
                "process.execute": {"process.execute": ["process://default_process"]},
                "network.search": {"network.search": ["https://api.duckduckgo.com/search"]},
                "system.status": {"system.status": ["system://status"]},
            }
            
            resources = resource_map.get(tool_name, {tool_name: [f"system://{tool_name.replace('.', '_')}"]})
            
            # P0.2 Fix: Check for explicit consent/approval token instead of self-generating fake consent
            consented_actions = []
            consent_ref = ""
            if tool_name in ["file.write", "process.execute"]:
                # Check if approval receipt or consent is explicitly passed in context
                passed_consent = ctx.get("consent_reference") or ctx.get("approval_receipt") or ctx.get("user_consent")
                if passed_consent:
                    consented_actions = [tool_name]
                    consent_ref = str(passed_consent)
                elif ctx.get("auto_consent") is True:
                    # Explicit auto_consent flag allowed for automated test harnesses
                    consented_actions = [tool_name]
                    consent_ref = f"test_harness_consent_{user_id}_{tool_name.replace('.', '_')}"
                else:
                    # Consent missing for dangerous action
                    return {"granted": False, "reason": f"USER_CONSENT_REQUIRED: Consent token needed for action '{tool_name}'"}

            # Issue grant using CapabilitySandbox
            grant_token = self._capability_sandbox.issue_grant(
                subject=user_id,
                actions=[tool_name],
                resources=resources,
                ttl_seconds=300.0,  # 5 minutes
                max_uses=1,
                consented_actions=consented_actions,
                consent_reference=consent_ref,
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
            workspace_root = repo_root.resolve()
            abs_path = str((workspace_root / raw_path).resolve())
            
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
        import shlex
        import subprocess
        from pathlib import Path

        workspace_root = repo_root.resolve()

        if tool_name in ["file.read", "file.list", "file.write"]:
            path_str = tool_args.get("path", ".")
            target_path = (workspace_root / path_str).resolve()
            
            # P0.4 Containment Check: Ensure path does not escape workspace root
            try:
                target_path.relative_to(workspace_root)
            except ValueError:
                raise PermissionError(f"PATH_ESCAPE_DENIED: Target path '{path_str}' escapes workspace boundary '{workspace_root}'")

            if tool_name == "file.read":
                if not target_path.exists():
                    raise FileNotFoundError(f"File not found: {path_str}")
                if target_path.is_dir():
                    files = os.listdir(target_path)
                    return {"path": str(target_path), "is_directory": True, "files": files}
                content = target_path.read_text(encoding="utf-8", errors="replace")
                return {"path": str(target_path), "content": content[:10000], "size_bytes": len(content)}

            elif tool_name == "file.list":
                if not target_path.exists():
                    raise FileNotFoundError(f"Directory not found: {path_str}")
                entries = os.listdir(target_path)
                return {"path": str(target_path), "entries": entries, "count": len(entries)}

            elif tool_name == "file.write":
                content = tool_args.get("content", "")
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(content, encoding="utf-8")
                return {"path": str(target_path), "bytes_written": len(content.encode("utf-8")), "written": True}

        elif tool_name == "process.execute":
            # P0.1 Fix: Safe process execution without shell=True
            cmd_raw = tool_args.get("command", "echo hello")
            if isinstance(cmd_raw, str):
                cmd_args = shlex.split(cmd_raw, posix=(sys.platform != "win32"))
            elif isinstance(cmd_raw, list):
                cmd_args = [str(a) for a in cmd_raw]
            else:
                raise ValueError(f"Invalid command format: {type(cmd_raw)}")

            if not cmd_args:
                raise ValueError("Command cannot be empty")

            executable = cmd_args[0].lower()
            allowed_executables = {"python", "python.exe", "pytest", "git", "echo", "dir", "ls"}
            
            # Allow executables inside workspace or virtual environment
            is_allowed = (
                executable in allowed_executables
                or Path(executable).name.lower() in allowed_executables
                or executable.startswith(str(workspace_root))
            )
            
            if not is_allowed:
                raise PermissionError(f"UNAUTHORIZED_EXECUTABLE: Process command '{executable}' is not in allowlist: {allowed_executables}")

            res = subprocess.run(
                cmd_args,
                shell=False,  # P0.1 NO shell=True
                capture_output=True,
                text=True,
                timeout=15,
                cwd=str(workspace_root),  # P0.4 Bound execution to workspace
            )
            return {
                "command": cmd_raw,
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
            # P0.6 Fix: Return CAPABILITY_UNAVAILABLE when no real network search provider exists
            raise NotImplementedError("CAPABILITY_UNAVAILABLE: Real network search provider is not configured.")

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