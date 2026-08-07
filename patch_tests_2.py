import re

TEST_FILES = [
    "JAYA_CORE/tests/test_real_action_loop_unit.py",
    "JAYA_CORE/tests/test_acceptance_real_action_loop.py"
]

for file_path in TEST_FILES:
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # We need to replace calls to execute_cognitive_intent(..., user_id="...") to include session_id="test_session" or "acceptance_session"
    # Same for execute_cognitive_plan
    
    content = content.replace('user_id="test_user",', 'user_id="test_user", session_id="test_session",')
    content = content.replace('user_id="test_user"\n', 'user_id="test_user", session_id="test_session"\n')
    
    content = content.replace('user_id="acceptance_user",', 'user_id="acceptance_user", session_id="acceptance_session",')
    content = content.replace('user_id="acceptance_user"\n', 'user_id="acceptance_user", session_id="acceptance_session"\n')

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
        
print("session_id patched!")
