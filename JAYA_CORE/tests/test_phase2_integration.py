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
        return create_symbolic_reasoner()

    @pytest.fixture(scope="class")
    def nlu_bridge(self, nlu_adapter, symbolic_reasoner):
        """Create NLU-Symbolic bridge."""
        return create_nlu_symbolic_bridge(
            nlu_adapter=nlu_adapter,
            symbolic_reasoner=symbolic_reasoner,
            confidence_threshold=0.7,
        )

    @pytest.fixture(scope="class")
    def executor(self):
        """Create real executor with sandbox."""
        sandbox = SandboxManager()
        skill_registry = SkillRegistry()
        from JAYA_CORE.src.brain_v2.engine.jaya_ir_executor import JayaIRExecutor
        ir_executor = JayaIRExecutor()
        
        # Create a simple executor that uses the sandbox manager
        class SimpleExecutor:
            def __init__(self, sandbox_manager, skill_registry, ir_executor):
                self.sandbox = sandbox_manager
                self.skills = skill_registry
                self.ir_exec = ir_executor
            
            async def execute(self, plan):
                from JAYA_CORE.src.cognitive.contracts import ExecutionResult, ExecutionStatus
                results = []
                for step in plan.steps:
                    if step.action_type == "execute_code":
                        request = ExecutionRequest(
                            code=step.inputs.get("code", ""),
                            language=Language.PYTHON,
                            resource_limits=ResourceLimits(max_wall_time_seconds=30),
                            user_id="test_user",
                        )
                        sandbox = SandboxManager()
                        result = await sandbox.execute(request)
                        results.append(type('StepResult', (), {
                            'success': result.status == ExecutionStatus.COMPLETED,
                            'output': result.stdout,
                            'error': result.stderr,
                        })())
                    elif step.action_type == "skill":
                        skill = self.skills.get(step.skill_id)
                        if not skill:
                            raise SkillNotFound(step.skill_id)
                        result = await skill.execute(step.inputs)
                        results.append(type('StepResult', (), {
                            'success': True,
                            'output': result,
                        })())
                    elif step.action_type == "jaya_ir":
                        result = await self.ir_exec.execute(step.inputs)
                        results.append(type('StepResult', (), {
                            'success': True,
                            'output': result,
                        })())
                    else:
                        raise UnknownStepType(step.type)
                
                return ExecutionResult(
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
        reasoner = create_symbolic_reasoner()
        return create_neural_symbolic_interface(
            model_path=None,  # Use random weights
            symbolic_reasoner=create_symbolic_reasoner(),
        )

    def test_nlu_to_executor_pipeline(self, nlu_bridge, executor):
        """Test pipeline NLU → Symbolic → Executor end-to-end."""
        # Real input
        user_input = "Buatkan rencana belajar Python untuk pemula"
        context = {"user_id": "test_user", "session_id": "test_session"}

        # Execute pipeline
        plan = nlu_bridge.process(user_input, context)
        
        # Verify plan structure
        assert hasattr(plan, 'ir'), "Plan should have IR"
        assert hasattr(plan, 'goal'), "Plan should have goal"
        assert hasattr(plan, 'plan'), "Plan should have action plan"
        
        # Execute plan
        result = asyncio.run(executor.execute(plan))
        
        # Verify result
        assert result.success, f"Execution failed: {result.error}"
        assert len(result.steps) > 0, "Should have executed steps"

    def test_nlu_low_confidence_fallback(self, nlu_adapter, symbolic_reasoner):
        """Test fallback when NLU confidence is low."""
        # Create bridge with high threshold
        bridge = create_nlu_symbolic_bridge(
            nlu_adapter=nlu_adapter,
            symbolic_reasoner=symbolic_reasoner,
            confidence_threshold=0.9,  # High threshold
        )
        
        # Input that should give low confidence
        result = nlu_bridge.process("asdfghjkl random gibberish", {})
        
        # Should return ClarificationNeeded
        from JAYA_CORE.src.nlu.symbolic_bridge import ClarificationNeeded
        assert isinstance(result, ClarificationNeeded), "Should return ClarificationNeeded for low confidence"

    def test_constraint_violation_handling(self, symbolic_reasoner):
        """Test handling of constraint violations."""
        from JAYA_CORE.src.cognitive.contracts import JayaIRRequest
        from JAYA_CORE.src.reasoning.constraint_solver import ConstraintViolation
        
        # Create IR that violates constraints (destructive without approval)
        ir = type('IR', (), {
            'steps': [{
                'step_id': 'step-1',
                'action_type': 'delete_file',
                'risk_class': 'DESTRUCTIVE',
                'approval_required': False,  # Missing approval!
            }],
            'required_capabilities': ['system.file.write'],
            'resource_budget': type('Budget', (), {
                'max_memory_mb': 100,
                'max_duration_seconds': 60,
            })(),
        })()
        
        with pytest.raises(Exception) as exc_info:
            symbolic_reasoner.reason(ir, {})
        
        # Should raise constraint violation
        assert "ConstraintViolation" in str(type(exc_info.value)) or "constraint" in str(exc_info.value).lower()

    def test_sandbox_execution_failure(self):
        """Test sandbox execution failure handling."""
        sandbox = SandboxManager()
        from JAYA_CORE.src.brain_v2.engine.jaya_ir_executor import JayaIRExecutor
        from JAYA_CORE.src.cognitive.skills import SkillRegistry
        executor = RealExecutor(sandbox, SkillRegistry(), JayaIRExecutor())
        
        # Code that will error
        from JAYA_CORE.src.cognitive.contracts import ActionPlan, ActionStep, ActionStatus, RiskClass
        plan = ActionPlan(
            plan_id="test-fail",
            goal_id="goal-test",
            steps=[
                ActionStep(
                    step_id="step-1",
                    title="Divide by zero",
                    action_type="execute_code",
                    required_capability="text.reasoning.basic",
                    risk_class=RiskClass.READ_ONLY,
                    inputs={"code": "1/0"},
                )
            ],
            domain="test",
        )
        
        result = asyncio.run(executor.execute(plan))
        
        # Should fail gracefully
        assert not result.success
        assert "ZeroDivisionError" in result.error or "division by zero" in result.error.lower()

    def test_neural_symbolic_interface(self, neural_interface):
        """Test neural-symbolic interface real operations."""
        # Test embedding
        embeddings = neural_interface.neural_embed(["test query", "another query"])
        assert embeddings.shape == (2, neural_interface.net.config.embed_dim)
        
        # Test classification
        result = neural_interface.neural_classify("buat rencana", ["CREATE_PLAN", "QUERY"])
        assert "CREATE_PLAN" in result
        assert result["CREATE_PLAN"] > 0.5
        
        # Test reranking
        scores = neural_interface.neural_rerank("machine learning", 
                                                ["ML basics", "DL advanced", "Python tutorial"])
        assert len(scores) == 3
        assert all(isinstance(s, float) for s in scores)

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
        # ML-related should score higher
        assert scores[0] > scores[3]  # ML basics > Rome history

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
        from JAYA_CORE.src.cognitive.contracts import JayaIRRequest
        
        # IR with circular dependency
        ir = type('IR', (), {
            'steps': [
                {'step_id': 'step-1', 'dependencies': ['step-2']},
                {'step_id': 'step-2', 'dependencies': ['step-1']},
            ],
            'required_capabilities': [],
            'resource_budget': type('Budget', (), {
                'max_memory_mb': 100,
                'max_duration_seconds': 60,
            })(),
        })()
        
        violations = symbolic_reasoner.constraint_solver.check(ir, {})
        
        # Should detect circular dependency
        circular_violations = [v for v in violations if v.constraint_name == "circular_dependency"]
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