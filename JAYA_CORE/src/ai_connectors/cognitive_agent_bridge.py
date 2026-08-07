"""
cognitive_agent_bridge.py — Bridge between JAYA Core Cognitive Model and JAYA Agent/OS.

Connects:
- IronEngine.cognitive_reason() → JAYA_AGENT AgentLoop → JAYA_OS CapabilitySandbox
- Enables real tool execution from cognitive reasoning
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import sys
import time
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add repo root to path for imports
repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))

logger = logging.getLogger(__name__)


@dataclass
class ProcessProfile:
    """
    Defines a safe, allowed process execution profile.
    
    Replaces arbitrary command execution with predefined, validated operations.
    """
    profile_id: str
    name: str
    description: str
    executable: str
    allowed_args: List[str]  # List of allowed argument patterns (regex or exact)
    max_args: int = 10
    timeout_seconds: float = 30.0
    working_dir: str = "workspace"  # "workspace", "temp", or absolute path
    requires_approval: bool = True
    risk_class: str = "REVERSIBLE"  # READ_ONLY, REVERSIBLE, DESTRUCTIVE
    
    def validate_args(self, args: List[str]) -> bool:
        """Validate that args match allowed patterns."""
        if len(args) > self.max_args:
            return False
        for arg in args:
            matched = False
            for pattern in self.allowed_args:
                import re
                if re.fullmatch(pattern, arg):
                    matched = True
                    break
            if not matched:
                return False
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Predefined safe process profiles
DEFAULT_PROCESS_PROFILES = {
    "pytest.workspace": ProcessProfile(
        profile_id="pytest.workspace",
        name="Run pytest in workspace",
        description="Execute pytest test suite within workspace boundary",
        executable="pytest",
        allowed_args=[
            r"^$",  # no args
            r"^-v$",
            r"^--tb=short$",
            r"^--version$",
            r"^tests/.*\.py$",
            r"^JAYA_CORE/tests/.*\.py$",
            r"^JAYA_RESEARCH/tests/.*\.py$",
            r"^JAYA_AGENT/tests/.*\.py$",
            r"^JAYA_OS/tests/.*\.py$",
        ],
        max_args=5,
        timeout_seconds=120.0,
        working_dir="workspace",
        requires_approval=True,
        risk_class="READ_ONLY",
    ),
    "python.compile": ProcessProfile(
        profile_id="python.compile",
        name="Python syntax check",
        description="Compile Python file to check syntax without execution",
        executable=sys.executable,
        allowed_args=[
            r"^-m$",
            r"^py_compile$",
            r"^.*\.py$",
        ],
        max_args=3,
        timeout_seconds=10.0,
        working_dir="workspace",
        requires_approval=False,
        risk_class="READ_ONLY",
    ),
    "git.status": ProcessProfile(
        profile_id="git.status",
        name="Git status",
        description="Show git repository status",
        executable="git",
        allowed_args=[
            r"^status$",
            r"^status\s+-s$",
            r"^status\s+--short$",
        ],
        max_args=3,
        timeout_seconds=10.0,
        working_dir="workspace",
        requires_approval=False,
        risk_class="READ_ONLY",
    ),
    "git.diff": ProcessProfile(
        profile_id="git.diff",
        name="Git diff",
        description="Show git diff for workspace changes",
        executable="git",
        allowed_args=[
            r"^diff$",
            r"^diff\s+--name-only$",
            r"^diff\s+HEAD$",
        ],
        max_args=3,
        timeout_seconds=10.0,
        working_dir="workspace",
        requires_approval=False,
        risk_class="READ_ONLY",
    ),
    "git.log": ProcessProfile(
        profile_id="git.log",
        name="Git log",
        description="Show recent git commit history",
        executable="git",
        allowed_args=[
            r"^log$",
            r"^log\s+--oneline$",
            r"^log\s+-\d+$",
        ],
        max_args=3,
        timeout_seconds=10.0,
        working_dir="workspace",
        requires_approval=False,
        risk_class="READ_ONLY",
    ),
}

from JAYA_CORE.src.security.approval_authority import ApprovalReceipt, ApprovalAuthority

# Initialize the persistent approval authority
_approval_authority = ApprovalAuthority()

# Helper for testing removed from production (use fixtures instead)
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

    def __init__(self, cognitive_executor: Optional[Any] = None):
        self.cognitive_executor = cognitive_executor
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
            from JAYA_OS.src.jaya_os.capability_sandbox import CapabilitySandbox, ActionPolicy, ProcessProfile as OSProcessProfile
            from pathlib import Path
            self._capability_sandbox = CapabilitySandbox()
            self._action_policy = ActionPolicy
            
            # Register process profiles with the sandbox
            workspace_root = Path.cwd().resolve()
            self._register_process_profiles(workspace_root)
            
            self._initialized = True
            logger.info("CognitiveAgentBridge initialized: AgentLoop + CapabilitySandbox")
            return True
        except ImportError as e:
            logger.warning(f"CognitiveAgentBridge initialization failed: {e}")
            return False
        except Exception as e:
            logger.error(f"CognitiveAgentBridge initialization error: {e}")
            return False

    def _register_process_profiles(self, workspace_root: Path) -> None:
        """Register predefined process profiles with the CapabilitySandbox."""
        from JAYA_OS.src.jaya_os.capability_sandbox import ProcessProfile as OSProcessProfile
        import sys
        
        # Register pytest profile - use python -m pytest
        python_exe = Path(sys.executable).resolve()
        pytest_profile = OSProcessProfile(
            executable=python_exe,
            arguments=("-m", "pytest"),
            cwd=workspace_root,
            cwd_root=workspace_root,
            max_output_bytes=64 * 1024,
        )
        self._capability_sandbox.register_process_profile("pytest.workspace", pytest_profile)
        
        # Register python compile profile
        python_profile = OSProcessProfile(
            executable=python_exe,
            arguments=("-m", "py_compile"),
            cwd=workspace_root,
            cwd_root=workspace_root,
            max_output_bytes=64 * 1024,
        )
        self._capability_sandbox.register_process_profile("python.compile", python_profile)
        
        # Register git profiles
        import shutil
        git_path = shutil.which("git")
        if git_path:
            git_exe = Path(git_path).resolve()
            git_status = OSProcessProfile(
                executable=git_exe,
                arguments=("status",),
                cwd=workspace_root,
                cwd_root=workspace_root,
                max_output_bytes=64 * 1024,
            )
            self._capability_sandbox.register_process_profile("git.status", git_status)
            
            git_diff = OSProcessProfile(
                executable=git_exe,
                arguments=("diff",),
                cwd=workspace_root,
                cwd_root=workspace_root,
                max_output_bytes=64 * 1024,
            )
            self._capability_sandbox.register_process_profile("git.diff", git_diff)
            
            git_log = OSProcessProfile(
                executable=git_exe,
                arguments=("log", "--oneline", "-10"),
                cwd=workspace_root,
                cwd_root=workspace_root,
                max_output_bytes=64 * 1024,
            )
            self._capability_sandbox.register_process_profile("git.log", git_log)

    def is_initialized(self) -> bool:
        return self._initialized

    def execute_cognitive_intent(
        self,
        intent: str,
        context: Optional[Dict[str, Any]] = None,
        user_id: str = "default_user",
        session_id: str = "default_session",
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
        if "session_id" not in ctx:
            ctx["session_id"] = session_id
        
        try:
            # Step 1: AgentLoop perceives and reasons
            agent_result = self._agent_loop.process_step(intent)
            
            # Step 2: Determine if tool execution is needed
            tool_needed, tool_name, tool_args = self._analyze_for_tool_execution(
                intent, agent_result, ctx
            )
            
            # Check if _analyze_for_tool_execution returned a validation error
            if isinstance(tool_args, dict) and "error" in tool_args:
                return {
                    "ok": False,
                    "error": "capability_denied",
                    "reason": tool_args["error"],
                    "agent_reasoning": agent_result.get("thought", ""),
                }
            
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
                    
                    # Step 5: Extract audit receipt from execution_result
                    audit_receipt = execution_result.get("audit_receipt")
                    
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

    def execute_cognitive_plan(
        self,
        plan: Any,
        context: Optional[Dict[str, Any]] = None,
        user_id: str = "default_user",
        session_id: str = "default_session",
    ) -> Dict[str, Any]:
        """
        Execute a structured plan (ActionPlan object or list of ActionStep objects).
        Stops on first failure and aggregates step execution results.
        """
        if not self._initialized:
            if not self.initialize():
                return {
                    "ok": False,
                    "error": "bridge_not_initialized",
                    "message": "Agent/OS bridge not available",
                }

        ctx = context or {}
        if "session_id" not in ctx:
            ctx["session_id"] = session_id
        
        execution_state = ctx.get("execution_state")
        if not execution_state:
            from JAYA_CORE.src.cognitive.execution_state import PlanExecutionState
            execution_state = PlanExecutionState(
                plan_id=getattr(plan, "plan_id", "unknown"),
                goal_id=getattr(plan, "goal_id", "unknown")
            )
            ctx["execution_state"] = execution_state

        steps = getattr(plan, "steps", plan) if not isinstance(plan, list) else plan
        if not isinstance(steps, list):
            return {
                "ok": False,
                "error": "INVALID_PLAN_STRUCTURE",
                "reason": "Plan must be a list of steps or contain a 'steps' attribute",
            }

        completed_steps = set()
        step_results = []
        failed_step = None

        for step in steps:
            step_id = getattr(step, "step_id", str(len(step_results)))
            ctx["completed_steps"] = completed_steps
            res = self.execute_action_step(step, context=ctx, user_id=user_id)
            step_results.append(res)
            
            if not res.get("ok"):
                execution_state.record_step_failure(step_id, res.get("error", "Unknown error"), res)
                failed_step = res
                break  # Stop execution on first step failure
                
            execution_state.record_step_success(step_id, res)
            completed_steps.add(step_id)

        all_success = (len(step_results) > 0) and (failed_step is None)
        return {
            "ok": all_success,
            "steps_executed": len(step_results),
            "total_steps": len(steps),
            "step_results": step_results,
            "failed_step": failed_step,
            "error": failed_step.get("error") if failed_step else None,
        }

    def execute_action_step(
        self,
        step: Any,
        context: Optional[Dict[str, Any]] = None,
        user_id: str = "default_user",
    ) -> Dict[str, Any]:
        """
        Execute a structured ActionStep directly without string keyword matching.
        
        P0.8: Validates ActionStep contracts (capability, risk, approval, dependencies)
        P0.9: No default fallbacks - requires explicit inputs
        """
        ctx = context or {}
        
        # P0.8: Validate ActionStep contract
        validation_error = self._validate_action_step(step)
        if validation_error:
            return {
                "ok": False,
                "error": "INVALID_ACTION_STEP",
                "reason": validation_error,
            }
        
        action_type = getattr(step, "action_type", "") or getattr(step, "required_capability", "")
        inputs = getattr(step, "inputs", {}) or {}
        
        # Resolve references if a PlanExecutionState is provided in context
        execution_state = ctx.get("execution_state")
        if execution_state:
            try:
                inputs = execution_state.resolve_references(inputs)
            except ValueError as e:
                return {
                    "ok": False,
                    "error": "UNRESOLVED_ACTION_INPUT",
                    "reason": str(e)
                }
                
        required_capability = getattr(step, "required_capability", "")
        risk_class = getattr(step, "risk_class", "")
        approval_required = getattr(step, "approval_required", False)
        dependencies = getattr(step, "dependencies", []) or []
        execution_target = getattr(step, "execution_target", "local")

        # Resolve action_type to tool_name (no fuzzy matching - exact mapping)
        tool_name = self._resolve_tool_name(action_type, required_capability)
        if not tool_name:
            return {
                "ok": False,
                "error": "UNSUPPORTED_ACTION",
                "action_type": action_type,
                "required_capability": required_capability,
            }

        # P0.9: Input Validation - No default fallbacks, require explicit inputs
        input_validation_error = self._validate_inputs_for_tool(tool_name, inputs)
        if input_validation_error:
            return {"ok": False, "error": "INVALID_ACTION_INPUT", "reason": input_validation_error}

        # P0.8: Check dependencies - ensure previous steps succeeded
        if dependencies:
            completed_steps = ctx.get("completed_steps", set())
            for dep in dependencies:
                if dep not in completed_steps:
                    return {
                        "ok": False,
                        "error": "UNMET_DEPENDENCY",
                        "reason": f"Required dependency '{dep}' has not completed successfully",
                    }

        # P0.8: Verify capability matches action
        if required_capability and not self._capability_matches_action(required_capability, tool_name):
            return {
                "ok": False,
                "error": "CAPABILITY_ACTION_MISMATCH",
                "reason": f"Required capability '{required_capability}' does not match action '{tool_name}'",
            }

        # P0.4 Fix: Bypass Agent/OS effect execution for internal cognitive steps
        if required_capability == "core.reason":
            if not self.cognitive_executor:
                return {
                    "ok": False,
                    "error": "COGNITIVE_PROVIDER_UNAVAILABLE",
                    "reason": "CognitiveActionExecutor not injected",
                }
            
            result = self.cognitive_executor.execute_reasoning(step, ctx)
            
            if execution_state:
                execution_state.artifacts.update(result.artifacts)
                execution_state.derived_inputs.update(result.derived_inputs)
            
            return {
                "ok": result.ok,
                "action_type": action_type,
                "tool_executed": "core.reason",
                "tool_result": {"status": "success" if result.ok else "error", "result": result.output_text},
                "cognitive_feedback": {"success": result.ok, "learned": True},
                "error": result.error,
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
        
        # P0.5 Fix: Use actual JAYA OS Audit Receipt
        audit_receipt = execution_result.get("receipt")

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

    def _validate_action_step(self, step: Any) -> Optional[str]:
        """Validate ActionStep contract fields."""
        required_fields = ["step_id", "title", "action_type", "required_capability", "risk_class"]
        for field in required_fields:
            if not getattr(step, field, None):
                return f"Missing required field: {field}"
        
        valid_risk_classes = {"READ_ONLY", "REVERSIBLE", "DESTRUCTIVE", "PHYSICAL_ACTION", "SECURITY_SENSITIVE", "COGNITIVE_UPDATE"}
        risk_class = getattr(step, "risk_class", "")
        risk_class_val = risk_class.value if hasattr(risk_class, "value") else str(risk_class)
        approval_required = getattr(step, "approval_required", False)
        
        if risk_class_val not in valid_risk_classes:
            return f"Invalid risk_class: {risk_class_val}. Must be one of {valid_risk_classes}"
            
        if approval_required and risk_class_val == "READ_ONLY":
            return "RISK_APPROVAL_MISMATCH: READ_ONLY actions should not require approval"
            
        if risk_class_val == "DESTRUCTIVE" and not approval_required:
            return "DESTRUCTIVE_REQUIRES_APPROVAL: DESTRUCTIVE actions must have approval_required=True"
        
        return None

    def _resolve_tool_name(self, action_type: str, required_capability: str) -> Optional[str]:
        """Resolve action_type/capability to exact tool name (no fuzzy matching)."""
        # Exact mapping from action_type to tool_name
        action_to_tool = {
            "fs.read": "fs.read",
            "fs.list": "fs.list", 
            "fs.write": "fs.write",
            "process.execute": "process.execute",
            "web.search": "web.search",
            "system.status": "system.status",
            "collect_requirements": "fs.read",
            "calculate_constraints": "core.reason",
            "generate_parametric_geometry": "cad.parametric_modeling",
            "present_preview": "core.reason",
            "export_model": "cad.parametric_modeling",
            "analyze_architecture": "core.reason",
            "write_code_draft": "core.reason",
            "run_tests": "process.execute",
            "inventory_files": "fs.list",
            "propose_structure": "core.reason",
            "request_move_approval": "core.reason",
            "process_general_request": "core.reason",
        }
        
        if action_type in action_to_tool:
            return action_to_tool[action_type]
        
        # Fallback: check capability mapping
        capability_to_tool = {
            "fs.read": "fs.read",
            "fs.list": "fs.list",
            "fs.write": "fs.write",
            "process.execute": "process.execute",
            "web.search": "web.search",
            "system.status": "system.status",
            "core.reason": "core.reason",
            "cad.parametric_modeling": "cad.parametric_modeling",
        }
        
        if required_capability in capability_to_tool:
            return capability_to_tool[required_capability]
        
        return None

    def _validate_inputs_for_tool(self, tool_name: str, inputs: Dict[str, Any]) -> Optional[str]:
        """Validate required inputs for each tool (no defaults)."""
        if tool_name == "process.execute":
            if not inputs.get("profile_id"):
                return "Required 'profile_id' input missing for process.execute"
            # Check against sandbox's registered profiles
            if self._capability_sandbox and hasattr(self._capability_sandbox, '_process_profiles'):
                if inputs.get("profile_id") not in self._capability_sandbox._process_profiles:
                    return f"Unknown process profile: {inputs.get('profile_id')}"
            elif inputs.get("profile_id") not in DEFAULT_PROCESS_PROFILES:
                return f"Unknown process profile: {inputs.get('profile_id')}"
        
        elif tool_name == "fs.write":
            if not inputs.get("path"):
                return "Required 'path' input missing for fs.write"
            if "content" not in inputs:
                return "Required 'content' input missing for fs.write"
        
        elif tool_name == "fs.read":
            if not inputs.get("path"):
                return "Required 'path' input missing for fs.read"
        
        elif tool_name == "fs.list":
            if not inputs.get("path"):
                return "Required 'path' input missing for fs.list"
        
        elif tool_name == "web.search":
            if not inputs.get("query"):
                return "Required 'query' input missing for web.search"
        
        return None

    def _capability_matches_action(self, capability: str, tool_name: str) -> bool:
        """Verify that capability matches the tool action."""
        capability_tool_map = {
            "fs.read": ["fs.read", "fs.list"],
            "fs.write": ["fs.write"],
            "fs.list": ["fs.list"],
            "process.execute": ["process.execute"],
            "web.search": ["web.search"],
            "system.status": ["system.status"],
            "core.reason": ["core.reason"],
            "cad.parametric_modeling": ["cad.parametric_modeling"],
        }
        
        allowed_tools = capability_tool_map.get(capability, [])
        return tool_name in allowed_tools

    def _analyze_for_tool_execution(
        self,
        intent: str,
        agent_result: Dict[str, Any],
        context: Dict[str, Any],
    ) -> tuple[bool, Optional[str], Dict[str, Any]]:
        """
        Analyze intent and agent reasoning to determine if tool execution is needed.
        
        P0.9: No default fallbacks - requires explicit inputs from context
        
        Returns:
            (tool_needed, tool_name, tool_args)
        """
        intent_lower = intent.lower()
        
        # Map intents to capabilities (matching CapabilitySandbox actions)
        tool_mapping = {
            "fs.read": {
                "keywords": ["baca file", "read file", "lihat file", "tampilkan file"],
                "tool": "fs.read",
                "args_builder": lambda i, c: {"path": c.get("target_path")},
            },
            "fs.list": {
                "keywords": ["list file", "daftar file", "list directory", "daftar folder"],
                "tool": "fs.list",
                "args_builder": lambda i, c: {"path": c.get("target_path")},
            },
            "fs.write": {
                "keywords": ["tulis file", "write file", "buat file", "simpan file", "create file"],
                "tool": "fs.write",
                "args_builder": lambda i, c: {"path": c.get("target_path"), "content": c.get("content")},
            },
            "process.execute": {
                "keywords": ["jalankan perintah", "eksekusi", "run command", "execute", "terminal", "shell"],
                "tool": "process.execute",
                "args_builder": lambda i, c: {"profile_id": c.get("profile_id"), "args": c.get("args", [])},
            },
            "web.search": {
                "keywords": ["cari web", "search web", "buka url", "fetch url", "download"],
                "tool": "web.search",
                "args_builder": lambda i, c: {"query": c.get("query")},
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
                    
                    # P0.9: Validate that required inputs are present (no defaults)
                    validation_error = self._validate_inputs_for_tool(tool_name, tool_args)
                    if validation_error:
                        return False, None, {"error": validation_error}
                    
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
            workspace_root = Path.cwd().resolve()
            target_path = (workspace_root / raw_path).resolve()
            abs_path = str(target_path)

            # Map tool to valid resources for grant according to OS scope policy
            resource_map = {
                "fs.read": {"fs.read": [f"{abs_path}/**" if target_path.is_dir() else abs_path]},
                "fs.list": {"fs.list": [f"{abs_path}/**" if target_path.is_dir() else abs_path]},
                "fs.write": {"fs.write": [abs_path]},
                "process.execute": {"process.execute": [f"process://{tool_args.get('profile_id', 'default_process')}"]},
                "web.search": {"web.search": ["https://api.duckduckgo.com/search"]},
                "system.status": {"system.status": ["system://status"]},
            }
            
            resources = resource_map.get(tool_name, {tool_name: [f"system://{tool_name.replace('.', '_')}"]})
            
            # P0.6, P0.7, P0.8 Fix: Require valid signed ApprovalReceipt with strict context validation
            consented_actions = []
            consent_ref = ""
            if tool_name in ["fs.write", "process.execute"]:
                # Check for signed ApprovalReceipt in context
                approval_receipt = ctx.get("approval_receipt") or tool_args.get("approval_receipt")
                if approval_receipt and isinstance(approval_receipt, ApprovalReceipt):
                    # Compute expected digest
                    import json
                    canonical_request = json.dumps({k: v for k, v in tool_args.items() if k != 'approval_receipt'}, sort_keys=True).encode()
                    expected_digest = hashlib.sha256(canonical_request).hexdigest()[:16]
                    
                    if tool_name == "process.execute":
                        expected_resource = f"process://{tool_args.get('profile_id', 'default_process')}"
                    else:
                        expected_resource = abs_path
                        
                    # P0.7, P0.8, P0.9: Verify via ApprovalAuthority with strict bindings
                    current_session_id = ctx.get("session_id")
                    if not current_session_id:
                        return {"granted": False, "reason": "SESSION_REQUIRED"}
                        
                    is_valid, reason = _approval_authority.verify_and_consume(
                        receipt=approval_receipt, 
                        current_session_id=current_session_id,
                        expected_user_id=user_id,
                        expected_action=tool_name,
                        expected_resource=expected_resource,
                        expected_request_digest=expected_digest
                    )
                    
                    if not is_valid:
                        return {"granted": False, "reason": reason}
                        
                    consented_actions = [tool_name]
                    consent_ref = approval_receipt.receipt_id
                else:
                    return {"granted": False, "reason": f"MISSING_APPROVAL_RECEIPT: Tool {tool_name} requires explicit consent"}

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
            workspace_root = Path.cwd().resolve()
            abs_path = str((workspace_root / raw_path).resolve())
            
            if tool_name in ["fs.read", "fs.write", "fs.list"]:
                resources_list = [abs_path]
            elif tool_name == "process.execute":
                # Use the actual process profile ID as resource
                profile_id = tool_args.get("profile_id", "default_process")
                resources_list = [f"process://{profile_id}"]
            elif tool_name == "system.status":
                resources_list = ["system://status"]
            elif tool_name == "web.search":
                resources_list = ["https://api.duckduckgo.com/search"]
            else:
                resources_list = [str(v) for v in tool_args.values()]

            # Execute via CapabilitySandbox (async)
            idempotency_hash = abs(hash(str(tool_args))) % 10000000
            idempotency_key = f"{tool_name.replace('.', '_')}_{idempotency_hash:012d}"
            
            if tool_name == "process.execute":
                profile_id = tool_args.get("profile_id", "default_process")
                execution = asyncio.run(
                    self._capability_sandbox.execute_process_profile(
                        grant_token=grant_token,
                        profile_name=profile_id,
                        idempotency_key=idempotency_key,
                        timeout_seconds=30.0,
                    )
                )
            else:
                execution = asyncio.run(
                    self._capability_sandbox.execute(
                        grant_token=grant_token,
                        action=tool_name,
                        resources=resources_list,
                        idempotency_key=idempotency_key,
                        request_payload=tool_args,
                        operation=operation,
                        timeout_seconds=30.0,
                    )
                )
            
            is_success = execution.receipt.status == "SUCCEEDED" if execution.receipt else False
            
            # P0.4 Fix: Check process returncode - non-zero exit code means process failed
            error_code = None
            error_msg = None
            if is_success and tool_name == "process.execute" and isinstance(execution.result, dict):
                exit_code = execution.result.get("returncode", 0)
                if exit_code != 0:
                    is_success = False
                    error_code = "PROCESS_FAILED"
                    error_msg = f"Process completed with non-zero exit code: {exit_code}"

            receipt_dict = execution.receipt.to_dict() if hasattr(execution.receipt, "to_dict") else (execution.receipt.__dict__ if execution.receipt else None)

            return {
                "status": "success" if is_success else "error",
                "result": execution.result,
                "tool": tool_name,
                "receipt": receipt_dict,
                "error": error_msg if not is_success else None,
                "error_code": error_code if not is_success else None,
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

        workspace_root = Path.cwd().resolve()

        if tool_name in ["fs.read", "fs.list", "fs.write"]:
            path_str = tool_args.get("path", ".")
            target_path = (workspace_root / path_str).resolve()
            
            # P0.4 Containment Check: Ensure path does not escape workspace root
            try:
                target_path.relative_to(workspace_root)
            except ValueError:
                raise PermissionError(f"PATH_ESCAPE_DENIED: Target path '{path_str}' escapes workspace boundary '{workspace_root}'")

            if tool_name == "fs.read":
                if not target_path.exists():
                    raise FileNotFoundError(f"File not found: {path_str}")
                if target_path.is_dir():
                    files = os.listdir(target_path)
                    return {"path": str(target_path), "is_directory": True, "files": files}
                content = target_path.read_text(encoding="utf-8", errors="replace")
                return {"path": str(target_path), "content": content[:10000], "size_bytes": len(content)}

            elif tool_name == "fs.list":
                if not target_path.exists():
                    raise FileNotFoundError(f"Directory not found: {path_str}")
                entries = os.listdir(target_path)
                return {"path": str(target_path), "entries": entries, "count": len(entries)}

            elif tool_name == "fs.write":
                content = tool_args.get("content", "")
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(content, encoding="utf-8")
                return {"path": str(target_path), "bytes_written": len(content.encode("utf-8")), "written": True}

        elif tool_name == "system.status":
            import platform
            return {
                "platform": platform.platform(),
                "python_version": platform.python_version(),
                "status": "HEALTHY",
            }

        elif tool_name == "web.search":
            # P0.6 Fix: Return CAPABILITY_UNAVAILABLE when no real network search provider exists
            raise NotImplementedError("CAPABILITY_UNAVAILABLE: Real network search provider is not configured.")

        else:
            raise NotImplementedError(f"Unsupported tool action: {tool_name}")




def create_cognitive_agent_bridge(cognitive_executor: Optional[Any] = None) -> CognitiveAgentBridge:
    """Factory function to create and initialize the bridge."""
    bridge = CognitiveAgentBridge(cognitive_executor=cognitive_executor)
    bridge.initialize()
    return bridge


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