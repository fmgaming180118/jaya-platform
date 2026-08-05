import sys
sys.path.insert(0, '.')

from JAYA_CORE.src.ai_connectors.cognitive_agent_bridge import enhance_iron_engine_with_agent_bridge
from JAYA_CORE.src.brain_v2.engine.runtime import IronEngine
import tempfile
from pathlib import Path

def test_enhance_iron_engine_with_agent_bridge():
    with tempfile.TemporaryDirectory() as tmpdir:
        model_path = Path(tmpdir) / 'test_model.jay'
        model_path.write_text('JAYA_TEST_MODEL')
        
        engine = IronEngine(
            model_path=str(model_path),
            password='test_password',
            enable_twin=False,
            enable_voice=False,
        )
        engine.ignite()
        
        # Enhance with agent bridge
        enhance_iron_engine_with_agent_bridge(engine)
        
        # Test cognitive_reason_and_act
        result = engine.cognitive_reason_and_act('Halo, apa kabar?', {'user_name': 'test'})
        assert "ok" in result
        if result["ok"]:
            assert "combined_response" in result
            assert "agent_execution" in result
        else:
            assert "error" in result