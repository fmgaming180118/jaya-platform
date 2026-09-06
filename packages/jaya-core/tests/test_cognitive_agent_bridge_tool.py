import sys
import os
sys.path.insert(0, '.')

from jaya_core.ai_connectors.cognitive_agent_bridge import CognitiveAgentBridge

bridge = CognitiveAgentBridge()
bridge.initialize()

# Test with tool-requiring intent - use absolute path
test_file = os.path.abspath('test.txt')
result = bridge.execute_cognitive_intent(
    'baca file test.txt',
    {'target_path': test_file},
    'test_user'
)
print(f'OK: {result["ok"]}')
print(f'Tool executed: {result.get("tool_executed")}')
print(f'Tool result: {result.get("tool_result")}')
print(f'Audit receipt: {result.get("audit_receipt")}')