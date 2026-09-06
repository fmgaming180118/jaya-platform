"""
Multi-Agent Orchestration for JAYA_CORE.

Provides:
- Agent registry and discovery
- Task delegation and coordination
- Inter-agent communication (A2A protocol)
- Workflow orchestration
- Agent lifecycle management
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Set, Union

from jaya_core.observability import get_structured_logger, record_error
from jaya_core.security import get_audit_logger, get_capability_manager, Capability

logger = get_structured_logger(__name__, component="agent_orchestration")
audit_logger = get_audit_logger()


# ============================================================================
# Data Classes
# ============================================================================

class AgentStatus(Enum):
    """Agent lifecycle status."""
    STARTING = "starting"
    READY = "ready"
    BUSY = "busy"
    ERROR = "error"
    STOPPING = "stopping"
    STOPPED = "stopped"


class TaskStatus(Enum):
    """Task execution status."""
    PENDING = "pending"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MessageType(Enum):
    """Inter-agent message types."""
    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"
    HEARTBEAT = "heartbeat"
    TASK_DELEGATE = "task_delegate"
    TASK_RESULT = "task_result"
    CAPABILITY_QUERY = "capability_query"
    CAPABILITY_RESPONSE = "capability_response"


@dataclass
class AgentCapability:
    """Agent capability definition."""
    name: str
    description: str
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    version: str = "1.0"


@dataclass
class AgentInfo:
    """Agent registration info."""
    agent_id: str
    name: str
    description: str
    capabilities: List[AgentCapability] = field(default_factory=list)
    endpoint: str = ""  # For remote agents
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: AgentStatus = AgentStatus.STARTING
    last_heartbeat: float = field(default_factory=time.time)
    load: float = 0.0  # 0.0 to 1.0


@dataclass
class Task:
    """Task for agent execution."""
    task_id: str
    name: str
    description: str
    required_capability: str
    input_data: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0  # Higher = more urgent
    timeout_seconds: float = 300.0
    created_at: float = field(default_factory=time.time)
    assigned_agent: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None


@dataclass
class AgentMessage:
    """Inter-agent message."""
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender_id: str = ""
    recipient_id: str = ""  # Empty for broadcast
    message_type: MessageType = MessageType.REQUEST
    payload: Dict[str, Any] = field(default_factory=dict)
    correlation_id: Optional[str] = None  # For request-response
    timestamp: float = field(default_factory=time.time)
    ttl: int = 3  # Time to live (hops)


# ============================================================================
# Agent Base Class
# ============================================================================

class BaseAgent(ABC):
    """Base class for all agents."""
    
    def __init__(
        self,
        agent_id: str,
        name: str,
        description: str = "",
        capabilities: List[AgentCapability] = None,
    ):
        self.agent_id = agent_id
        self.name = name
        self.description = description
        self.capabilities = capabilities or []
        self.status = AgentStatus.STARTING
        self._message_handlers: Dict[MessageType, Callable] = {}
        self._task_queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._tasks: Dict[str, Task] = {}
    
    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize agent resources."""
        pass
    
    @abstractmethod
    async def shutdown(self):
        """Shutdown agent gracefully."""
        pass
    
    @abstractmethod
    async def execute_task(self, task: Task) -> Dict[str, Any]:
        """Execute a task."""
        pass
    
    def register_handler(self, message_type: MessageType, handler: Callable):
        """Register message handler."""
        self._message_handlers[message_type] = handler
    
    async def handle_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        """Handle incoming message."""
        handler = self._message_handlers.get(message.message_type)
        if handler:
            return await handler(message)
        return None
    
    def get_info(self) -> AgentInfo:
        """Get agent info for registry."""
        return AgentInfo(
            agent_id=self.agent_id,
            name=self.name,
            description=self.description,
            capabilities=self.capabilities,
            status=self.status,
            last_heartbeat=time.time(),
        )
    
    async def run(self):
        """Main agent loop."""
        self._running = True
        self.status = AgentStatus.READY
        
        while self._running:
            try:
                # Process messages
                # Process tasks
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error("Agent loop error", agent_id=self.agent_id, error=str(e))
                self.status = AgentStatus.ERROR
                await asyncio.sleep(1)
    
    async def stop(self):
        """Stop agent."""
        self._running = False
        self.status = AgentStatus.STOPPING
        await self.shutdown()
        self.status = AgentStatus.STOPPED


# ============================================================================
# Local Agent Implementation
# ============================================================================

class LocalAgent(BaseAgent):
    """Local in-process agent."""
    
    def __init__(
        self,
        agent_id: str,
        name: str,
        description: str = "",
        capabilities: List[AgentCapability] = None,
        executor: Callable = None,
    ):
        super().__init__(agent_id, name, description, capabilities)
        self.executor = executor
        self._message_queue: asyncio.Queue = asyncio.Queue()
    
    async def initialize(self) -> bool:
        """Initialize local agent."""
        self.status = AgentStatus.READY
        return True
    
    async def shutdown(self):
        """Shutdown local agent."""
        pass
    
    async def execute_task(self, task: Task) -> Dict[str, Any]:
        """Execute task using executor."""
        if self.executor:
            if asyncio.iscoroutinefunction(self.executor):
                return await self.executor(task.input_data)
            else:
                return self.executor(task.input_data)
        return {"error": "No executor configured"}
    
    async def send_message(self, message: AgentMessage):
        """Send message to message queue."""
        await self._message_queue.put(message)
    
    async def receive_message(self) -> AgentMessage:
        """Receive message from queue."""
        return await self._message_queue.get()


# ============================================================================
# Agent Registry
# ============================================================================

class AgentRegistry:
    """Registry for agent discovery and management."""
    
    def __init__(self):
        self._agents: Dict[str, AgentInfo] = {}
        self._local_agents: Dict[str, LocalAgent] = {}
        self._capability_index: Dict[str, Set[str]] = defaultdict(set)  # capability -> agent_ids
        self._lock = asyncio.Lock()
    
    async def register(self, agent: BaseAgent) -> bool:
        """Register an agent."""
        async with self._lock:
            info = agent.get_info()
            self._agents[agent.agent_id] = info
            
            # Index capabilities
            for cap in info.capabilities:
                self._capability_index[cap.name].add(agent.agent_id)
            
            # Store local agent reference
            if isinstance(agent, LocalAgent):
                self._local_agents[agent.agent_id] = agent
            
            logger.info("Agent registered", agent_id=agent.agent_id, name=info.name)
            return True
    
    async def unregister(self, agent_id: str) -> bool:
        """Unregister an agent."""
        async with self._lock:
            if agent_id not in self._agents:
                return False
            
            info = self._agents[agent_id]
            
            # Remove from capability index
            for cap in info.capabilities:
                self._capability_index[cap.name].discard(agent_id)
            
            del self._agents[agent_id]
            self._local_agents.pop(agent_id, None)
            
            logger.info("Agent unregistered", agent_id=agent_id)
            return True
    
    async def get_agent(self, agent_id: str) -> Optional[AgentInfo]:
        """Get agent info."""
        return self._agents.get(agent_id)
    
    async def get_local_agent(self, agent_id: str) -> Optional[LocalAgent]:
        """Get local agent instance."""
        return self._local_agents.get(agent_id)
    
    async def find_agents_by_capability(
        self, 
        capability: str, 
        status: AgentStatus = AgentStatus.READY
    ) -> List[AgentInfo]:
        """Find agents with specific capability."""
        agent_ids = self._capability_index.get(capability, set())
        agents = [
            self._agents[aid] for aid in agent_ids
            if aid in self._agents and self._agents[aid].status == status
        ]
        # Sort by load (least loaded first)
        agents.sort(key=lambda a: a.load)
        return agents
    
    async def list_agents(self, status: Optional[AgentStatus] = None) -> List[AgentInfo]:
        """List all agents."""
        agents = list(self._agents.values())
        if status:
            agents = [a for a in agents if a.status == status]
        return agents
    
    async def update_heartbeat(self, agent_id: str, load: float = 0.0):
        """Update agent heartbeat and load."""
        if agent_id in self._agents:
            self._agents[agent_id].last_heartbeat = time.time()
            self._agents[agent_id].load = load
    
    async def cleanup_stale_agents(self, max_age_seconds: float = 60.0):
        """Remove agents that haven't sent heartbeat."""
        now = time.time()
        stale = [
            aid for aid, info in self._agents.items()
            if now - info.last_heartbeat > max_age_seconds
        ]
        for aid in stale:
            await self.unregister(aid)
            logger.warning("Removed stale agent", agent_id=aid)


# ============================================================================
# Task Orchestrator
# ============================================================================

class TaskOrchestrator:
    """Orchestrates task delegation and execution."""
    
    def __init__(self, registry: AgentRegistry):
        self.registry = registry
        self._tasks: Dict[str, Task] = {}
        self._task_queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._worker_tasks: List[asyncio.Task] = []
    
    async def submit_task(self, task: Task) -> str:
        """Submit task for execution."""
        self._tasks[task.task_id] = task
        await self._task_queue.put(task.task_id)
        logger.info("Task submitted", task_id=task.task_id, name=task.name)
        return task.task_id
    
    async def get_task_status(self, task_id: str) -> Optional[Task]:
        """Get task status."""
        return self._tasks.get(task_id)
    
    async def cancel_task(self, task_id: str) -> bool:
        """Cancel pending task."""
        if task_id in self._tasks:
            task = self._tasks[task_id]
            if task.status in (TaskStatus.PENDING, TaskStatus.ASSIGNED):
                task.status = TaskStatus.CANCELLED
                return True
        return False
    
    async def start(self, num_workers: int = 4):
        """Start orchestrator workers."""
        self._running = True
        for i in range(num_workers):
            worker = asyncio.create_task(self._worker_loop(f"worker-{i}"))
            self._worker_tasks.append(worker)
        logger.info("Task orchestrator started", workers=num_workers)
    
    async def stop(self):
        """Stop orchestrator."""
        self._running = False
        for worker in self._worker_tasks:
            worker.cancel()
        await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        logger.info("Task orchestrator stopped")
    
    async def _worker_loop(self, worker_name: str):
        """Worker loop for processing tasks."""
        while self._running:
            try:
                task_id = await asyncio.wait_for(
                    self._task_queue.get(),
                    timeout=1.0,
                )
                await self._execute_task(task_id)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("Worker error", worker=worker_name, error=str(e))
                await asyncio.sleep(1)
    
    async def _execute_task(self, task_id: str):
        """Execute a single task."""
        task = self._tasks.get(task_id)
        if not task:
            return
        
        # Find suitable agent
        agents = await self.registry.find_agents_by_capability(task.required_capability)
        if not agents:
            task.status = TaskStatus.FAILED
            task.error = f"No agent available for capability: {task.required_capability}"
            logger.error("No agent for task", task_id=task_id, capability=task.required_capability)
            return
        
        # Select least loaded agent
        agent = agents[0]
        task.assigned_agent = agent.agent_id
        task.status = TaskStatus.ASSIGNED
        task.started_at = time.time()
        
        # Update agent load
        await self.registry.update_heartbeat(agent.agent_id, agent.load + 0.1)
        
        try:
            task.status = TaskStatus.RUNNING
            
            # Get local agent and execute
            local_agent = await self.registry.get_local_agent(agent.agent_id)
            if local_agent:
                result = await local_agent.execute_task(task)
                task.result = result
                task.status = TaskStatus.COMPLETED
            else:
                # Remote agent - would send message
                task.status = TaskStatus.FAILED
                task.error = "Remote agent execution not implemented"
            
            task.completed_at = time.time()
            
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            logger.error("Task execution failed", task_id=task_id, error=str(e))
        
        finally:
            # Update agent load
            await self.registry.update_heartbeat(agent.agent_id, max(0, agent.load - 0.1))


# ============================================================================
# A2A (Agent-to-Agent) Protocol
# ============================================================================

class A2AProtocol:
    """Agent-to-Agent communication protocol."""
    
    def __init__(self, registry: AgentRegistry):
        self.registry = registry
        self._message_routes: Dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
        self._pending_requests: Dict[str, asyncio.Future] = {}
    
    async def send_message(self, message: AgentMessage) -> bool:
        """Send message to agent(s)."""
        if message.recipient_id:
            # Direct message
            queue = self._message_routes.get(message.recipient_id)
            if queue:
                await queue.put(message)
                return True
            return False
        else:
            # Broadcast
            for queue in self._message_routes.values():
                await queue.put(message)
            return True
    
    async def send_request(
        self,
        sender_id: str,
        recipient_id: str,
        payload: Dict[str, Any],
        timeout: float = 30.0,
    ) -> Optional[AgentMessage]:
        """Send request and wait for response."""
        correlation_id = str(uuid.uuid4())
        
        message = AgentMessage(
            sender_id=sender_id,
            recipient_id=recipient_id,
            message_type=MessageType.REQUEST,
            payload=payload,
            correlation_id=correlation_id,
        )
        
        # Create future for response
        future = asyncio.get_event_loop().create_future()
        self._pending_requests[correlation_id] = future
        
        # Send message
        await self.send_message(message)
        
        try:
            response = await asyncio.wait_for(future, timeout=timeout)
            return response
        except asyncio.TimeoutError:
            return None
        finally:
            self._pending_requests.pop(correlation_id, None)
    
    async def handle_response(self, message: AgentMessage):
        """Handle response message."""
        if message.correlation_id and message.correlation_id in self._pending_requests:
            future = self._pending_requests[message.correlation_id]
            if not future.done():
                future.set_result(message)
    
    def register_agent_queue(self, agent_id: str) -> asyncio.Queue:
        """Register message queue for agent."""
        return self._message_routes[agent_id]
    
    def unregister_agent_queue(self, agent_id: str):
        """Unregister agent queue."""
        self._message_routes.pop(agent_id, None)


# ============================================================================
# Workflow Orchestrator
# ============================================================================

@dataclass
class WorkflowStep:
    """Single step in workflow."""
    step_id: str
    name: str
    capability: str
    input_mapping: Dict[str, str] = field(default_factory=dict)  # workflow_var -> step_input
    output_mapping: Dict[str, str] = field(default_factory=dict)  # step_output -> workflow_var
    depends_on: List[str] = field(default_factory=list)
    condition: Optional[str] = None  # Python expression for conditional execution


@dataclass
class Workflow:
    """Multi-agent workflow definition."""
    workflow_id: str
    name: str
    description: str = ""
    steps: List[WorkflowStep] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


class WorkflowOrchestrator:
    """Orchestrates multi-step workflows across agents."""
    
    def __init__(self, task_orchestrator: TaskOrchestrator):
        self.task_orchestrator = task_orchestrator
        self._workflows: Dict[str, Workflow] = {}
        self._executions: Dict[str, Dict[str, Any]] = {}  # execution_id -> state
    
    def register_workflow(self, workflow: Workflow):
        """Register a workflow."""
        self._workflows[workflow.workflow_id] = workflow
        logger.info("Workflow registered", workflow_id=workflow.workflow_id, name=workflow.name)
    
    async def execute_workflow(
        self,
        workflow_id: str,
        initial_variables: Dict[str, Any] = None,
    ) -> str:
        """Execute a workflow."""
        workflow = self._workflows.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow not found: {workflow_id}")
        
        execution_id = str(uuid.uuid4())
        variables = {**workflow.variables, **(initial_variables or {})}
        
        self._executions[execution_id] = {
            "workflow_id": workflow_id,
            "status": "running",
            "variables": variables,
            "completed_steps": set(),
            "step_results": {},
            "started_at": time.time(),
        }
        
        # Start execution
        asyncio.create_task(self._execute_workflow(execution_id, workflow))
        
        return execution_id
    
    async def _execute_workflow(self, execution_id: str, workflow: Workflow):
        """Execute workflow steps."""
        execution = self._executions[execution_id]
        variables = execution["variables"]
        completed = execution["completed_steps"]
        step_results = execution["step_results"]
        
        # Build dependency graph
        step_map = {s.step_id: s for s in workflow.steps}
        pending = set(step_map.keys())
        
        while pending:
            # Find ready steps
            ready = [
                sid for sid in pending
                if all(dep in completed for dep in step_map[sid].depends_on)
            ]
            
            if not ready:
                # Check for circular dependency or failed condition
                for sid in pending:
                    step = step_map[sid]
                    if step.condition:
                        try:
                            if not eval(step.condition, {"__builtins__": {}}, variables):
                                completed.add(sid)
                                pending.remove(sid)
                                break
                        except Exception:
                            pass
                if not ready:
                    execution["status"] = "failed"
                    execution["error"] = "Circular dependency or no ready steps"
                    return
            
            # Execute ready steps in parallel
            tasks = []
            for sid in ready:
                step = step_map[sid]
                task = asyncio.create_task(self._execute_step(execution_id, step, variables))
                tasks.append((sid, task))
            
            # Wait for completion
            for sid, task in tasks:
                try:
                    result = await task
                    step_results[sid] = result
                    
                    # Map outputs to variables
                    step = step_map[sid]
                    for out_var, step_out in step.output_mapping.items():
                        if step_out in result:
                            variables[out_var] = result[step_out]
                    
                    completed.add(sid)
                    pending.remove(sid)
                    
                except Exception as e:
                    logger.error("Workflow step failed", execution_id=execution_id, step=sid, error=str(e))
                    execution["status"] = "failed"
                    execution["error"] = f"Step {sid} failed: {str(e)}"
                    return
        
        execution["status"] = "completed"
        execution["completed_at"] = time.time()
        logger.info("Workflow completed", execution_id=execution_id)
    
    async def _execute_step(
        self,
        execution_id: str,
        step: WorkflowStep,
        variables: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute a single workflow step."""
        # Prepare input from variables
        input_data = {}
        for var_name, step_input in step.input_mapping.items():
            if var_name in variables:
                input_data[step_input] = variables[var_name]
        
        # Create task
        task = Task(
            task_id=f"{execution_id}-{step.step_id}",
            name=step.name,
            description=f"Workflow step: {step.name}",
            required_capability=step.capability,
            input_data=input_data,
        )
        
        # Submit and wait
        await self.task_orchestrator.submit_task(task)
        
        # Poll for completion
        while True:
            task_status = await self.task_orchestrator.get_task_status(task.task_id)
            if task_status and task_status.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                if task_status.status == TaskStatus.FAILED:
                    raise Exception(task_status.error or "Task failed")
                return task_status.result or {}
            await asyncio.sleep(0.5)
    
    def get_execution_status(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """Get workflow execution status."""
        return self._executions.get(execution_id)


# ============================================================================
# Default Instances
# ============================================================================

_agent_registry: Optional[AgentRegistry] = None
_task_orchestrator: Optional[TaskOrchestrator] = None
_a2a_protocol: Optional[A2AProtocol] = None
_workflow_orchestrator: Optional[WorkflowOrchestrator] = None


def get_agent_registry() -> AgentRegistry:
    """Get global agent registry."""
    global _agent_registry
    if _agent_registry is None:
        _agent_registry = AgentRegistry()
    return _agent_registry


def get_task_orchestrator() -> TaskOrchestrator:
    """Get global task orchestrator."""
    global _task_orchestrator
    if _task_orchestrator is None:
        _task_orchestrator = TaskOrchestrator(get_agent_registry())
    return _task_orchestrator


def get_a2a_protocol() -> A2AProtocol:
    """Get global A2A protocol."""
    global _a2a_protocol
    if _a2a_protocol is None:
        _a2a_protocol = A2AProtocol(get_agent_registry())
    return _a2a_protocol


def get_workflow_orchestrator() -> WorkflowOrchestrator:
    """Get global workflow orchestrator."""
    global _workflow_orchestrator
    if _workflow_orchestrator is None:
        _workflow_orchestrator = WorkflowOrchestrator(get_task_orchestrator())
    return _workflow_orchestrator


# ============================================================================
# Convenience Functions
# ============================================================================

async def create_local_agent(
    agent_id: str,
    name: str,
    capability: str,
    executor: Callable,
    description: str = "",
) -> LocalAgent:
    """Create and register a local agent."""
    cap = AgentCapability(
        name=capability,
        description=f"Capability: {capability}",
    )
    
    agent = LocalAgent(
        agent_id=agent_id,
        name=name,
        description=description,
        capabilities=[cap],
        executor=executor,
    )
    
    registry = get_agent_registry()
    await registry.register(agent)
    
    return agent


async def delegate_task(
    capability: str,
    input_data: Dict[str, Any],
    priority: int = 0,
    timeout: float = 300.0,
) -> Dict[str, Any]:
    """Delegate task to available agent."""
    task = Task(
        task_id=str(uuid.uuid4()),
        name=f"Delegated: {capability}",
        description=f"Execute {capability}",
        required_capability=capability,
        input_data=input_data,
        priority=priority,
        timeout_seconds=timeout,
    )
    
    orchestrator = get_task_orchestrator()
    await orchestrator.submit_task(task)
    
    # Wait for completion
    while True:
        task_status = await orchestrator.get_task_status(task.task_id)
        if task_status and task_status.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
            if task_status.status == TaskStatus.FAILED:
                raise Exception(task_status.error or "Task failed")
            return task_status.result or {}
        await asyncio.sleep(0.5)
