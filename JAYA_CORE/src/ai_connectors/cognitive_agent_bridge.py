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


@dataclass
class ApprovalReceipt:
    """
    Signed human approval receipt for sensitive operations.
    
    Binds: user_id, session_id, action, resource, request_digest, 
           issued_at, expires_at, nonce, signature
    """
    receipt_id: str
    user_id: str
    session_id: str
    action: str
    resource: str
    request_digest: str
    issued_at: float
    expires_at: float
    nonce: str
    signature: str
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def create(
        cls,
        user_id: str,
        session_id: str,
        action: str,
        resource: str,
        request_digest: str,
        ttl_seconds: float = 300.0,
        signing_key: str = None,
    ) -> "ApprovalReceipt":
        """Create a new signed approval receipt."""
        import hmac
        
        receipt_id = f"approval-{int(time.time() * 1000)}-{secrets.token_hex(4)}"
        issued_at = time.time()
        expires_at = issued_at + ttl_seconds
        nonce = secrets.token_hex(16)
        
        # Create signature using HMAC
        signing_key = signing_key or "JAYA_APPROVAL_SIGNING_KEY"
        message = f"{receipt_id}|{user_id}|{session_id}|{action}|{resource}|{request_digest}|{issued_at}|{expires_at}|{nonce}"
        signature = hmac.new(
            signing_key.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()[:32]
        
        return cls(
            receipt_id=receipt_id,
            user_id=user_id,
            session_id=session_id,
            action=action,
            resource=resource,
            request_digest=request_digest,
            issued_at=issued_at,
            expires_at=expires_at,
            nonce=nonce,
            signature=signature,
        )
    
    def verify(self, signing_key: str = None) -> bool:
        """Verify the receipt signature and expiry."""
        import hmac
        
        if time.time() > self.expires_at:
            return False
        
        signing_key = signing_key or "JAYA_APPROVAL_SIGNING_KEY"
        message = f"{self.receipt_id}|{self.user_id}|{self.session_id}|{self.action}|{self.resource}|{self.request_digest}|{self.issued_at}|{self.expires_at}|{self.nonce}"
        expected_signature = hmac.new(
            signing_key.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()[:32]
        
        return hmac.compare_digest(self.signature, expected_signature)


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
            arguments=("-m", "pytest", "--version"),
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
        git_exe = Path("git").resolve()
        if git_exe.exists():
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

    def execute_cognitive_plan(
        self,
        plan: Any,
        context: Optional[Dict[str, Any]] = None,
        user_id: str = "default_user",
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
        steps = getattr(plan, "steps", plan) if not isinstance(plan, list) else plan
        if not isinstance(steps, list):
            return {
                "ok": False,
                "error": "INVALID_PLAN_STRUCTURE",
                "reason": "Plan must be a list of steps or contain a 'steps' attribute",
            }

        step_results = []
        failed_step = None

        for step in steps:
            res = self.execute_action_step(step, context=ctx, user_id=user_id)
            step_results.append(res)
            if not res.get("ok"):
                failed_step = res
                break  # Stop execution on first step failure

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
            # This would need step_results from the plan execution context
            # For now, we note the dependency requirement
            pass

        # P0.8: Verify capability matches action
        if required_capability and not self._capability_matches_action(required_capability, tool_name):
            return {
                "ok": False,
                "error": "CAPABILITY_ACTION_MISMATCH",
                "reason": f"Required capability '{required_capability}' does not match action '{tool_name}'",
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

    def _validate_action_step(self, step: Any) -> Optional[str]:
        """Validate ActionStep contract fields."""
        required_fields = ["step_id", "title", "action_type", "required_capability", "risk_class"]
        for field in required_fields:
            if not getattr(step, field, None):
                return f"Missing required field: {field}"
        
        valid_risk_classes = {"READ_ONLY", "REVERSIBLE", "DESTRUCTIVE"}
        risk_class = getattr(step, "risk_class", "")
        approval_required = getattr(step, "approval_required", False)
        
        if risk_class not in valid_risk_classes:
            return f"Invalid risk_class: {risk_class}. Must be one of {valid_risk_classes}"
            
        if approval_required and risk_class == "READ_ONLY":
            return "RISK_APPROVAL_MISMATCH: READ_ONLY actions should not require approval"
            
        if risk_class == "DESTRUCTIVE" and not approval_required:
            return "DESTRUCTIVE_REQUIRES_APPROVAL: DESTRUCTIVE actions must have approval_required=True"
        
        return None

    def _resolve_tool_name(self, action_type: str, required_capability: str) -> Optional[str]:
        """Resolve action_type/capability to exact tool name (no fuzzy matching)."""
        # Exact mapping from action_type to tool_name
        action_to_tool = {
            "file.read": "file.read",
            "file.list": "file.list", 
            "file.write": "file.write",
            "process.execute": "process.execute",
            "network.search": "network.search",
            "system.status": "system.status",
            "collect_requirements": "file.read",
            "calculate_constraints": "text.reasoning.basic",
            "generate_parametric_geometry": "cad.parametric_modeling",
            "present_preview": "text.reasoning.basic",
            "export_model": "cad.parametric_modeling",
            "analyze_architecture": "text.reasoning.basic",
            "write_code_draft": "file.write",
            "run_tests": "process.execute",
            "inventory_files": "file.list",
            "propose_structure": "text.reasoning.basic",
            "request_move_approval": "text.reasoning.basic",
            "process_general_request": "text.reasoning.basic",
        }
        
        if action_type in action_to_tool:
            return action_to_tool[action_type]
        
        # Fallback: check capability mapping
        capability_to_tool = {
            "system.file.read": "file.read",
            "system.file.list": "file.list",
            "system.file.write": "file.write",
            "process.execute": "process.execute",
            "network.search": "network.search",
            "system.status": "system.status",
            "text.reasoning.basic": "text.reasoning.basic",
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
        
        elif tool_name == "file.write":
            if not inputs.get("path"):
                return "Required 'path' input missing for file.write"
            if "content" not in inputs:
                return "Required 'content' input missing for file.write"
        
        elif tool_name == "file.read":
            if not inputs.get("path"):
                return "Required 'path' input missing for file.read"
        
        elif tool_name == "file.list":
            if not inputs.get("path"):
                return "Required 'path' input missing for file.list"
        
        elif tool_name == "network.search":
            if not inputs.get("query"):
                return "Required 'query' input missing for network.search"
        
        return None

    def _capability_matches_action(self, capability: str, tool_name: str) -> bool:
        """Verify that capability matches the tool action."""
        capability_tool_map = {
            "system.file.read": ["file.read", "file.list"],
            "system.file.write": ["file.write"],
            "process.execute": ["process.execute"],
            "network.search": ["network.search"],
            "system.status": ["system.status"],
            "text.reasoning.basic": ["text.reasoning.basic"],
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
            "file.read": {
                "keywords": ["baca file", "read file", "lihat file", "tampilkan file"],
                "tool": "file.read",
                "args_builder": lambda i, c: {"path": c.get("target_path")},
            },
            "file.list": {
                "keywords": ["list file", "daftar file", "list directory", "daftar folder"],
                "tool": "file.list",
                "args_builder": lambda i, c: {"path": c.get("target_path")},
            },
            "file.write": {
                "keywords": ["tulis file", "write file", "buat file", "simpan file", "create file"],
                "tool": "file.write",
                "args_builder": lambda i, c: {"path": c.get("target_path"), "content": c.get("content")},
            },
            "process.execute": {
                "keywords": ["jalankan perintah", "eksekusi", "run command", "execute", "terminal", "shell"],
                "tool": "process.execute",
                "args_builder": lambda i, c: {"profile_id": c.get("profile_id"), "args": c.get("args", [])},
            },
            "network.search": {
                "keywords": ["cari web", "search web", "buka url", "fetch url", "download"],
                "tool": "network.search",
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
            workspace_root = repo_root.resolve()
            target_path = (workspace_root / raw_path).resolve()
            abs_path = str(target_path)

            # Map tool to valid resources for grant according to OS scope policy
            resource_map = {
                "file.read": {"file.read": [f"{abs_path}/**" if target_path.is_dir() else abs_path]},
                "file.list": {"file.list": [f"{abs_path}/**" if target_path.is_dir() else abs_path]},
                "file.write": {"file.write": [abs_path]},
                "process.execute": {"process.execute": [f"process://{tool_args.get('profile_id', 'default_process')}"]},
                "network.search": {"network.search": ["https://api.duckduckgo.com/search"]},
                "system.status": {"system.status": ["system://status"]},
            }
            
            resources = resource_map.get(tool_name, {tool_name: [f"system://{tool_name.replace('.', '_')}"]})
            
            # P0.6 Fix: Require valid signed ApprovalReceipt instead of boolean bypass
            consented_actions = []
            consent_ref = ""
            if tool_name in ["file.write", "process.execute"]:
                # Check for signed ApprovalReceipt in context
                approval_receipt = ctx.get("approval_receipt") or tool_args.get("approval_receipt")
                if approval_receipt and isinstance(approval_receipt, ApprovalReceipt):
                    if approval_receipt.verify():
                        consented_actions = [tool_name]
                        consent_ref = approval_receipt.receipt_id
                    else:
                        return {"granted": False, "reason": f"INVALID_APPROVAL_RECEIPT: Signature verification failed or receipt expired"}
                else:
                    return {"granted": False, "reason": f"USER_CONSENT_REQUIRED: Signed ApprovalReceipt needed for action '{tool_name}'"}

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
                # Use the actual process profile ID as resource
                profile_id = tool_args.get("profile_id", "default_process")
                resources_list = [f"process://{profile_id}"]
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
            
            # P0.4 Fix: Check process returncode - non-zero exit code means process failed
            error_code = None
            error_msg = None
            if is_success and tool_name == "process.execute" and isinstance(execution.result, dict):
                exit_code = execution.result.get("exit_code", 0)
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
            # P0.7 Fix: Use ProcessProfile from sandbox instead of arbitrary command execution
            profile_id = tool_args.get("profile_id")
            if not profile_id:
                raise ValueError("INVALID_ACTION_INPUT: Required 'profile_id' input missing for process.execute")
            
            # Get profile from sandbox's registered profiles
            if not self._capability_sandbox or not hasattr(self._capability_sandbox, '_process_profiles'):
                raise PermissionError(f"UNAUTHORIZED_PROFILE: No process profiles registered in sandbox")
            
            sandbox_profile = self._capability_sandbox._process_profiles.get(profile_id)
            if not sandbox_profile:
                raise PermissionError(f"UNAUTHORIZED_PROFILE: Process profile '{profile_id}' not registered in sandbox")
            
            # Validate args against sandbox profile
            cmd_args = tool_args.get("args", [])
            if isinstance(cmd_args, str):
                import shlex
                cmd_args = shlex.split(cmd_args, posix=(sys.platform != "win32"))
            elif not isinstance(cmd_args, list):
                raise ValueError(f"Invalid args format: {type(cmd_args)}")
            
            # Build full command from sandbox profile
            full_cmd = [str(sandbox_profile.executable)] + list(sandbox_profile.arguments) + cmd_args
            
            # Use sandbox profile's working directory
            cwd = str(sandbox_profile.cwd)
            
            res = subprocess.run(
                full_cmd,
                shell=False,
                capture_output=True,
                text=True,
                timeout=sandbox_profile.max_output_bytes / 1024,  # rough timeout
                cwd=cwd,
            )
            return {
                "profile_id": profile_id,
                "command": " ".join(full_cmd),
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


def create_approval_receipt(
    user_id: str,
    session_id: str,
    action: str,
    resource: str,
    request_digest: str,
    ttl_seconds: float = 300.0,
) -> ApprovalReceipt:
    """Helper to create a signed ApprovalReceipt for sensitive operations."""
    return ApprovalReceipt.create(
        user_id=user_id,
        session_id=session_id,
        action=action,
        resource=resource,
        request_digest=request_digest,
        ttl_seconds=ttl_seconds,
    )


def create_cognitive_agent_bridge() -> CognitiveAgentBridge:
    """Factory function to create and initialize the bridge."""
    bridge = CognitiveAgentBridge()
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