import sys
sys.path.insert(0, '.')

from jaya_core.brain_v2.engine.runtime import IronEngine
import tempfile
from pathlib import Path

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
    
    # Test cognitive_reason with real LLM
    result = engine.cognitive_reason('Halo, apa kabar?', {'user_name': 'test'})
    print(f'OK: {result["ok"]}')
    print(f'Source: {result["source"]}')
    print(f'Model: {result["model_used"]}')
    print(f'Confidence: {result["confidence"]}')
    print(f'Text: {result["text"][:200]}')
    
    # Test cognitive_status
    status = engine.get_cognitive_status()
    print(f'Cognitive status: {status}')