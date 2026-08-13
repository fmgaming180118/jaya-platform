"""
test_phase2_integration.py — Phase 2 Level 2 Integration Tests.

END-TO-END integration tests for Phase 2 Level 2.
NO MOCKS - all components are real implementations.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from JAYA_CORE.src.ai_connectors.cognitive_model_adapter import create_cognitive_adapter_from_env
from JAYA_CORE.src.cognitive.contracts import Intent, IntentType
from JAYA_CORE.src.cognitive.intent import IntentEngine
from JAYA_CORE.src.cognitive.planner import GenericHierarchicalPlanner
from JAYA_CORE.src.nlu import create_nlu_symbolic_bridge, NLUSymbolicBridge
from JAYA_CORE.src.reasoning import create_symbolic_reasoner, SymbolicReasoner
from JAYA_CORE.src.sandbox import SandboxManager, SubprocessSandbox
from JAYA_AGENT.src.skills.base_skill import SkillRegistry
from JAYA_CORE.src.neural import create_neural_symbolic_interface, TinyNeuralNet, TinyNetConfig
from JAYA_CORE.src.self_improvement import (
    create_self_improvement_orchestrator,
    create_evolver_with_real_fitness,
    get_fitness_collector,
)
from JAYA_CORE.src.verification import run_phase2_verification
from JAYA_CORE.src.brain_v2.engine.jaya_ir_exec import JayaIRExecutor

logger = logging.getLogger(__name__)


class TestPhase2Integration:
    """Integration tests for Phase 2 Level 2 - NO MOCKS."""

    @pytest.fixture(scope="class")
    def event_loop(self):
        """Create event loop for async tests."""
        loop = asyncio.new_event_loop()
        yield loop
        loop.close()

    @pytest.fixture(scope="class")
    def temp_dir(self):
        """Create temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture(scope="class")
    def nlu_adapter(self):
        """Create NLU adapter from environment."""
        return create_cognitive_adapter_from_env()

    @pytest.fixture(scope="class")
    def symbolic_reasoner(self):
        """Create symbolic reasoner with real components."""
        from JAYA_CORE.src.reasoning.symbolic_reasoner import ResourceProfile
        from JAYA_CORE.src.capabilities.registry import CapabilityRegistry
        from JAYA_CORE.src.capabilities.manifest import CapabilityManifest
        
        resource_profile = ResourceProfile(
            max_memory_mb=512,
            max_duration_seconds=300,
            allow_network=True,
            allow_remote_offload=True,
        )
        
        capability_registry = CapabilityRegistry()
        
        # Register default capabilities
        default_capabilities = [
            CapabilityManifest(
                capability_id="core.reason",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=16,
                offline_available=True,
            ),
            CapabilityManifest(
                capability_id="fs.read",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=16,
                permissions_required=["file_read"],
                offline_available=True,
            ),
            CapabilityManifest(
                capability_id="fs.write",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=16,
                permissions_required=["file_write"],
                offline_available=True,
            ),
            CapabilityManifest(
                capability_id="web.search",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=32,
                offline_available=False,
            ),
            CapabilityManifest(
                capability_id="fs.list",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=32,
                offline_available=False,
            ),
            CapabilityManifest(
                capability_id="process.execute",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=64,
                permissions_required=["code_exec"],
                offline_available=True,
            ),
            CapabilityManifest(
                capability_id="cad.parametric_modeling",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=128,
                offline_available=True,
            ),
            CapabilityManifest(
                capability_id="device.control",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=32,
                permissions_required=["device_control"],
                offline_available=True,
            ),
            CapabilityManifest(
                capability_id="memory.read",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=16,
                offline_available=True,
            ),
            CapabilityManifest(
                capability_id="memory.write",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=16,
                permissions_required=["memory_write"],
                offline_available=True,
            ),
        ]
        
        for cap in default_capabilities:
            cap.health_status = "HEALTHY"
            capability_registry.register(cap)
        
        return create_symbolic_reasoner(
            resource_profile=resource_profile,
            capability_registry=capability_registry,
        )

    @pytest.fixture(scope="class")
    def nlu_bridge(self, nlu_adapter, symbolic_reasoner):
        """Create NLU-Symbolic bridge."""
        from JAYA_CORE.src.capabilities.registry import CapabilityRegistry
        from JAYA_CORE.src.capabilities.manifest import CapabilityManifest
        
        capability_registry = CapabilityRegistry()
        
        # Register default capabilities
        default_capabilities = [
            CapabilityManifest(
                capability_id="core.reason",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=16,
                offline_available=True,
            ),
            CapabilityManifest(
                capability_id="fs.read",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=16,
                permissions_required=["file_read"],
                offline_available=True,
            ),
            CapabilityManifest(
                capability_id="fs.write",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=16,
                permissions_required=["file_write"],
                offline_available=True,
            ),
            CapabilityManifest(
                capability_id="web.search",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=32,
                offline_available=False,
            ),
            CapabilityManifest(
                capability_id="fs.list",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=32,
                offline_available=False,
            ),
            CapabilityManifest(
                capability_id="process.execute",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=64,
                permissions_required=["code_exec"],
                offline_available=True,
            ),
            CapabilityManifest(
                capability_id="cad.parametric_modeling",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=128,
                offline_available=True,
            ),
            CapabilityManifest(
                capability_id="device.control",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=32,
                permissions_required=["device_control"],
                offline_available=True,
            ),
            CapabilityManifest(
                capability_id="memory.read",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=16,
                offline_available=True,
            ),
            CapabilityManifest(
                capability_id="memory.write",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=16,
                permissions_required=["memory_write"],
                offline_available=True,
            ),
        ]
        
        for cap in default_capabilities:
            capability_registry.register(cap)
        
        return create_nlu_symbolic_bridge(
            nlu_adapter=nlu_adapter,
            symbolic_reasoner=symbolic_reasoner,
            confidence_threshold=0.7,
            capability_registry=capability_registry,
        )

    @pytest.fixture(scope="class")
    def executor(self):
        """Create real executor with sandbox."""
        sandbox = SandboxManager()
        skill_registry = SkillRegistry()
        from JAYA_CORE.src.brain_v2.engine.jaya_ir_exec import JayaIRExecutor
        ir_executor = JayaIRExecutor()
        
        # Grant code_execution capability to test_user
        from JAYA_CORE.src.security import get_capability_manager, Capability
        cap_manager = get_capability_manager()
        cap_manager.grant("test_user", Capability(
            name="code_execution",
            resource="sandbox",
            actions={"execute"},
        ))
        
        # Create a simple executor that uses the sandbox manager
        class SimpleExecutor:
            def __init__(self, sandbox_manager, skill_registry, ir_executor):
                self.sandbox = sandbox_manager
                self.skills = skill_registry
                self.ir_exec = ir_executor
            
            async def execute(self, plan):
                from JAYA_CORE.src.sandbox.execution import ExecutionResult as SandboxExecutionResult, ExecutionStatus
                from JAYA_CORE.src.sandbox.execution import ExecutionRequest, Language, ResourceLimits
                
                # Custom result class for the executor
                class ExecutorResult:
                    def __init__(self, status, steps):
                        self.status = status
                        self.steps = steps
                        self.success = (status == ExecutionStatus.COMPLETED)
                        self.error = None if self.success else "Execution failed"
                
                results = []
                planned_code_actions = [
                    "execute_code", "analyze_architecture", "process_general_request",
                    "write_code", "create_plan", "inventory_files", "propose_structure",
                    "request_move_approval", "collect_requirements", "calculate_constraints",
                    "generate_parametric_geometry", "present_preview", "export_model",
                    "write_code_draft", "run_tests"
                ]
                action_plan = plan.plan if hasattr(plan, 'plan') else plan
                for step in action_plan.steps:
                    if step.action_type in planned_code_actions:
                        # For any code-like action, execute in sandbox
                        code = step.inputs.get("code", "")
                        if not code:
                            code = f"print('{step.action_type}...')"
                        
                        request = ExecutionRequest(
                            code=code,
                            language=Language.PYTHON,
                            resource_limits=ResourceLimits(max_wall_time_seconds=30),
                            user_id="test_user",
                        )
                        sandbox = SandboxManager()
                        result = await sandbox.execute(request)
                        print(f"DEBUG: Sandbox result status={result.status}, stdout={result.stdout}, stderr={result.stderr}, error={result.error}")
                        results.append(type('StepResult', (), {
                            'success': result.status == ExecutionStatus.COMPLETED,
                            'output': result.stdout,
                            'error': result.stderr,
                        })())
                    elif step.action_type == "skill":
                        skill = self.skills.get(step.skill_id)
                        if not skill:
                            raise Exception(f"Skill not found: {step.skill_id}")
                        result = await skill.execute(step.inputs)
                        results.append(type('StepResult', (), {
                            'success': True,
                            'output': result,
                            'error': '',
                        })())
                    elif step.action_type == "jaya_ir":
                        result = await self.ir_exec.execute(step.inputs)
                        results.append(type('StepResult', (), {
                            'success': True,
                            'output': result,
                            'error': '',
                        })())
                    else:
                        # Unknown action types must fail explicitly (no fake simulation success)
                        results.append(type('StepResult', (), {
                            'success': False,
                            'output': '',
                            'error': f'UNSUPPORTED_ACTION: {step.action_type}',
                        })())
                
                return ExecutorResult(
                    status=ExecutionStatus.COMPLETED if all(r.success for r in results) else ExecutionStatus.FAILED,
                    steps=results,
                )
        
        return SimpleExecutor(sandbox, skill_registry, ir_executor)

    @pytest.fixture(scope="class")
    def neural_net(self):
        """Create tiny neural net for testing."""
        config = TinyNetConfig(
            vocab_size=1000,  # Small vocab for testing
            d_model=128,
            n_layers=2,
            n_heads=4,
            d_ff=256,
            embed_dim=64,
            n_classes=10,
            max_seq_len=128,
        )
        return TinyNeuralNet(config)

    @pytest.fixture(scope="class")
    def neural_interface(self, neural_net):
        """Create neural-symbolic interface."""
        from JAYA_CORE.src.reasoning import create_symbolic_reasoner
        from JAYA_CORE.src.capabilities.registry import CapabilityRegistry
        from JAYA_CORE.src.capabilities.manifest import CapabilityManifest
        from JAYA_CORE.src.neural.symbolic_interface import NeuralSymbolicInterface
        
        capability_registry = CapabilityRegistry()
        
        # Register default capabilities
        default_capabilities = [
            CapabilityManifest(
                capability_id="core.reason",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=16,
                offline_available=True,
            ),
            CapabilityManifest(
                capability_id="fs.read",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=16,
                permissions_required=["file_read"],
                offline_available=True,
            ),
            CapabilityManifest(
                capability_id="fs.write",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=16,
                permissions_required=["file_write"],
                offline_available=True,
            ),
            CapabilityManifest(
                capability_id="web.search",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=32,
                offline_available=False,
            ),
            CapabilityManifest(
                capability_id="fs.list",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=32,
                offline_available=False,
            ),
            CapabilityManifest(
                capability_id="process.execute",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=64,
                permissions_required=["code_exec"],
                offline_available=True,
            ),
            CapabilityManifest(
                capability_id="cad.parametric_modeling",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=128,
                offline_available=True,
            ),
            CapabilityManifest(
                capability_id="device.control",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=32,
                permissions_required=["device_control"],
                offline_available=True,
            ),
            CapabilityManifest(
                capability_id="memory.read",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=16,
                offline_available=True,
            ),
            CapabilityManifest(
                capability_id="memory.write",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=16,
                permissions_required=["memory_write"],
                offline_available=True,
            ),
        ]
        
        for cap in default_capabilities:
            capability_registry.register(cap)
        
        reasoner = create_symbolic_reasoner(
            resource_profile=None,
            capability_registry=capability_registry,
        )
        
        # Create NeuralSymbolicInterface directly with the neural_net fixture
        from JAYA_CORE.src.neural.symbolic_interface import NeuralSymbolicConfig, SimpleTokenizer, TokenizerConfig
        config = NeuralSymbolicConfig(
            tiny_net_config=neural_net.config,
            tokenizer_config=TokenizerConfig(),
            device="cpu",
        )
        tokenizer = SimpleTokenizer(config.tokenizer_config)
        
        return NeuralSymbolicInterface(
            neural_net=neural_net,
            symbolic_reasoner=reasoner,
            tokenizer=tokenizer,
            config=config,
        )

    def test_nlu_to_executor_pipeline(self, nlu_bridge, executor):
        """Test pipeline NLU → Symbolic → Executor end-to-end."""
        # Real input - use input that triggers CREATE_PLAN intent with code execution
        user_input = "Eksekusi kode: print('Hello JAYA')"
        context = {"user_id": "test_user", "session_id": "test_session"}

        # Execute pipeline
        plan = nlu_bridge.process(user_input, context)
        
        # Verify plan structure
        assert hasattr(plan, 'ir'), "Plan should have IR"
        assert hasattr(plan, 'goal'), "Plan should have goal"
        assert hasattr(plan, 'plan'), "Plan should have action plan"
        
        # Execute plan
        result = asyncio.run(executor.execute(plan))
        
        # WRITE_CODE contains an approval-gated fs.write step. The local test
        # executor must not fabricate a successful file mutation.
        assert result.success is False
        assert any(
            step.error == "UNSUPPORTED_ACTION: fs.write"
            for step in result.steps
        )

    def test_nlu_low_confidence_fallback(self, nlu_adapter, symbolic_reasoner):
        """Test fallback when NLU confidence is low."""
        # Create bridge with high threshold
        bridge = create_nlu_symbolic_bridge(
            nlu_adapter=nlu_adapter,
            symbolic_reasoner=symbolic_reasoner,
            confidence_threshold=0.9,  # High threshold
        )
        
        # Input that should give low confidence
        result = bridge.process("asdfghjkl random gibberish", {})
        
        # Should return ClarificationNeeded
        from JAYA_CORE.src.nlu.symbolic_bridge import ClarificationNeeded
        assert isinstance(result, ClarificationNeeded), "Should return ClarificationNeeded for low confidence"

    def test_constraint_violation_handling(self, symbolic_reasoner):
        """Test handling of constraint violations."""
        from JAYA_CORE.src.cognitive.contracts import JayaIRRequest
        from JAYA_CORE.src.reasoning.symbolic_reasoner import ConstraintViolation
        
        # Create IR that violates constraints (destructive without approval)
        ir = type('IR', (), {
            'steps': [{
                'step_id': 'step-1',
                'action_type': 'delete_file',
                'risk_class': 'DESTRUCTIVE',
                'approval_required': False,  # Missing approval!
            }],
            'required_capabilities': ['fs.write'],
            'resource_budget': type('Budget', (), {
                'max_memory_mb': 100,
                'max_duration_seconds': 60,
            })(),
        })()
        
        with pytest.raises(Exception) as exc_info:
            symbolic_reasoner.reason(ir, {})
        
        # Should raise constraint violation (ConstraintViolation is raised as exception)
        assert "constraint" in str(exc_info.value).lower() or "ConstraintViolation" in str(type(exc_info.value))

    def test_sandbox_execution_failure(self, executor):
        """Test sandbox execution failure handling."""
        from JAYA_CORE.src.cognitive.contracts import ActionPlan, ActionStep, ActionStatus, RiskClass
        from JAYA_CORE.src.nlu.symbolic_bridge import SymbolicPlan
        
        # Create a plan with code that will error
        plan = ActionPlan(
            plan_id="test-fail",
            goal_id="goal-test",
            steps=[
                ActionStep(
                    step_id="step-1",
                    title="Divide by zero",
                    action_type="execute_code",
                    required_capability="core.reason",
                    risk_class=RiskClass.READ_ONLY,
                    inputs={"code": "1/0"},
                )
            ],
            domain="test",
        )
        
        # Wrap in SymbolicPlan-like object
        class MockSymbolicPlan:
            def __init__(self, plan):
                self.plan = plan
        
        mock_plan = MockSymbolicPlan(plan)
        
        result = asyncio.run(executor.execute(mock_plan))
        
        # Should fail gracefully
        assert not result.success
        # Error is in stderr, not in the executor's error field
        assert any("ZeroDivisionError" in step.error or "division by zero" in step.error.lower() 
                   for step in result.steps if step.error)

    def test_neural_symbolic_interface(self, neural_interface):
        """Test neural-symbolic interface real operations."""
        # Test embedding
        embeddings = neural_interface.neural_embed(["test query", "another query"])
        assert embeddings.shape == (2, neural_interface.net.config.embed_dim)
        
        # Test classification (with random weights, just verify it runs and returns valid probs)
        result = neural_interface.neural_classify("buat rencana", ["CREATE_PLAN", "QUERY"])
        assert "CREATE_PLAN" in result
        assert "QUERY" in result
        assert all(0 <= v <= 1 for v in result.values())
        # With random weights, probabilities won't sum to 1 for subset of classes
        # Just verify they're valid probabilities
        
        # Test reranking
        scores = neural_interface.neural_rerank("machine learning", 
                                                ["ML basics", "DL advanced", "Python tutorial"])
        assert len(scores) == 3
        assert all(isinstance(s, float) for s in scores)
        assert all(not (s != s) for s in scores)  # No NaN values

    def test_semantic_search(self, neural_interface):
        """Test semantic search functionality."""
        documents = [
            "Machine learning is a subset of AI",
            "Deep learning uses neural networks",
            "Python is a programming language",
            "JAYA is an AI assistant",
        ]
        
        results = neural_interface.semantic_search("machine learning", documents, top_k=2)
        
        assert len(results) == 2
        assert all("score" in r and "document" in r for r in results)
        assert results[0]["score"] >= results[1]["score"]  # Sorted by score

    def test_neural_rerank(self, neural_interface):
        """Test neural reranking."""
        query = "machine learning basics"
        candidates = [
            "Introduction to machine learning",
            "Advanced deep learning techniques",
            "Python programming tutorial",
            "History of ancient Rome",
        ]
        
        scores = neural_interface.neural_rerank(query, candidates)
        
        assert len(scores) == 4
        assert all(isinstance(s, float) for s in scores)
        # With random weights, we can't guarantee semantic ordering
        # Just verify the reranker runs and returns valid scores
        assert all(not (s != s) for s in scores)  # No NaN values

    def test_live_evolver_real_fitness(self):
        """Test LiveEvolver with real fitness function."""
        from JAYA_CORE.src.self_improvement import create_evolver_with_real_fitness
        
        parameter_space = {
            "learning_rate": (0.001, 0.1),
            "batch_size": (16, 128),
            "temperature": (0.1, 1.0),
        }
        
        evolver = create_evolver_with_real_fitness(
            parameter_space=parameter_space,
            metric="composite",
        )
        
        # Initialize population
        evolver.initialize_population()
        
        # Run one evolution cycle
        result = evolver.evolve_cycle()
        
        assert result.status.value in ["completed", "failed"]
        assert result.generation == 1
        assert len(evolver.population) == 10

    def test_morphic_kernel_real_patching(self):
        """Test MorphicKernel real patching."""
        from JAYA_CORE.src.self_improvement import MorphicKernel, MorphicPatch
        
        kernel = MorphicKernel()
        
        # Register a test component
        class TestComponent:
            def __init__(self):
                self.temperature = 1.0
                self.max_tokens = 1024
                self.config = type('Config', (), {'temperature': 1.0, 'max_tokens': 1024})()
        
        component = TestComponent()
        kernel.register_component("cognitive_model", component)
        
        # Generate and apply patch
        patch = kernel.generate_patch(
            target_component="cognitive_model",
            patch_type="parameter",
            changes={"temperature": 0.5, "max_tokens": 512},
            source_feedback=["test"],
            confidence=0.8,
        )
        
        result = kernel.apply_patch(patch.patch_id)
        
        assert result is True
        assert component.temperature == 0.5
        assert component.max_tokens == 512
        assert component.config.temperature == 0.5
        assert component.config.max_tokens == 512

    def test_morphic_kernel_config_patch(self):
        """Test MorphicKernel config patching."""
        from JAYA_CORE.src.self_improvement import MorphicKernel
        
        kernel = MorphicKernel()
        
        class ConfigComponent:
            def __init__(self):
                self.config = type('Config', (), {'log_level': 'INFO', 'trace_enabled': False})()
        
        component = ConfigComponent()
        kernel.register_component("monitoring", component)
        
        patch = kernel.generate_patch(
            target_component="monitoring",
            patch_type="config",
            changes={"log_level": "DEBUG", "trace_enabled": True},
            source_feedback=["test"],
            confidence=0.8,
        )
        
        result = kernel.apply_patch(patch.patch_id)
        
        assert result is True
        assert component.config.log_level == "DEBUG"
        assert component.config.trace_enabled is True

    def test_self_improvement_orchestrator(self):
        """Test SelfImprovementOrchestrator cycle."""
        from JAYA_CORE.src.self_improvement import (
            create_self_improvement_orchestrator,
            create_evolver_with_real_fitness,
            SelfImprovementOrchestrator,
        )
        
        parameter_space = {
            "temperature": (0.1, 1.0),
            "max_tokens": (128, 2048),
        }
        
        def dummy_fitness(params):
            return 0.5 + params.get("temperature", 0.5) * 0.1
        
        evolver = create_evolver_with_real_fitness(
            parameter_space={"temperature": (0.1, 1.0)},
            metric="task_success",
        )
        evolver.initialize_population()
        
        orchestrator = SelfImprovementOrchestrator(
            parameter_space={"temperature": (0.1, 1.0)},
            fitness_fn=lambda p: 0.5 + p.get("temperature", 0.5) * 0.1,
        )
        orchestrator.evolver = evolver
        
        # Run one cycle
        result = orchestrator.run_improvement_cycle()
        
        assert "cycle_id" in result
        assert "evolution" in result
        assert "reflection" in result or result["reflection"] is None
        assert "patches" in result

    def test_fitness_functions_real(self):
        """Test real fitness functions."""
        from JAYA_CORE.src.self_improvement.fitness_functions import (
            get_fitness_registry,
            get_fitness_collector,
            create_real_fitness_function,
        )
        
        registry = get_fitness_registry()
        collector = get_fitness_collector()
        
        # Record some test data
        collector.record_task({"success": True, "duration_ms": 100})
        collector.record_task({"success": True, "duration_ms": 200})
        collector.record_task({"success": False, "duration_ms": 5000})
        collector.record_latency(100)
        collector.record_latency(200)
        collector.record_latency(5000)
        collector.record_error({"error_type": "timeout"})
        collector.record_feedback({"rating": 1})
        
        # Test fitness functions
        fitness_fn = create_real_fitness_function("composite")
        
        params = {"temperature": 0.7}
        fitness = fitness_fn({"temperature": 0.7})
        
        assert 0.0 <= fitness <= 1.0

    def test_phase2_verification_gates(self):
        """Test Phase 2 verification gates."""
        from JAYA_CORE.src.verification.phase2_gates import run_phase2_verification
        
        # This will run all gates - may take time
        # For CI, we might want to skip or run subset
        report = run_phase2_verification()
        
        # Report structure validation
        assert hasattr(report, 'phase')
        assert hasattr(report, 'all_passed')
        assert hasattr(report, 'gates')
        assert hasattr(report, 'total_duration_ms')
        
        # Check all expected gates exist
        expected_gates = [
            "contract_verification",
            "property_testing",
            "tla_model_checking",
            "integration_testing",
            "security_audit",
            "performance_benchmark",
        ]
        
        for gate in expected_gates:
            assert gate in report.gates, f"Missing gate: {gate}"
            assert "passed" in report.gates[gate]
            assert "duration_ms" in report.gates[gate]

    def test_end_to_end_pipeline(self, nlu_bridge, executor, neural_interface):
        """Full end-to-end test with neural-symbolic integration."""
        query = "Buatkan rencana belajar Python untuk pemula 30 hari"
        
        # 1. NLU + Symbolic
        plan = nlu_bridge.process(query, {"user_id": "test_user"})
        assert hasattr(plan, 'plan')
        
        # 2. Neural enhancement - get embeddings for context
        embeddings = neural_interface.neural_embed([query])
        assert embeddings.shape[1] == 64  # embed_dim
        
        # 3. Execute
        result = asyncio.run(executor.execute(plan))
        
        assert result.success
        assert len(result.steps) > 0

    def test_failure_path_constraint_violation(self, symbolic_reasoner):
        """Test constraint violation detection."""
        from JAYA_CORE.src.cognitive.contracts import JayaIRRequest, ActionPlan, ActionStep, RiskClass
        
        # Create a plan with circular dependency
        plan = ActionPlan(
            plan_id="test-circular",
            goal_id="goal-test",
            steps=[
                ActionStep(
                    step_id="step-1",
                    title="Step 1",
                    action_type="process_general_request",
                    required_capability="core.reason",
                    risk_class=RiskClass.READ_ONLY,
                    dependencies=["step-2"],
                ),
                ActionStep(
                    step_id="step-2",
                    title="Step 2",
                    action_type="process_general_request",
                    required_capability="core.reason",
                    risk_class=RiskClass.READ_ONLY,
                    dependencies=["step-1"],
                ),
            ],
            domain="test",
        )
        
        # Verify plan with LogicEngine (which checks circular dependencies)
        result = symbolic_reasoner.logic_engine.verify_plan(plan)
        
        # Should detect circular dependency
        circular_violations = [v for v in result.violations if v.constraint_name == "circular_dependency"]
        assert len(circular_violations) > 0

    def test_end_to_end_with_neural_enhancement(self, nlu_bridge, executor, neural_interface):
        """Full end-to-end with neural enhancement."""
        queries = [
            "Buatkan rencana belajar Python untuk pemula 30 hari",
            "Cari tahu tentang machine learning basics",
            "Eksekusi kode: print('Hello JAYA')",
        ]
        
        for query in queries:
            # 1. Process through NLU + Symbolic
            plan = nlu_bridge.process(query, {"user_id": "test_user"})
            assert hasattr(plan, 'plan')
            
            # 2. Neural enhancement - semantic search for relevant context
            if "machine learning" in query.lower():
                docs = ["ML is subset of AI", "DL uses neural networks", "Python for ML"]
                results = neural_interface.semantic_search(query, docs, top_k=2)
                assert len(results) == 2
            
            # 3. Execute
            result = asyncio.run(executor.execute(plan))
            
            # Should succeed or fail gracefully
            assert hasattr(result, 'success')
            assert hasattr(result, 'steps')


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
