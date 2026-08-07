import re
from pathlib import Path

files = [
    "JAYA_CORE/tests/test_real_action_loop_unit.py",
    "JAYA_CORE/tests/test_acceptance_real_action_loop.py"
]

for file in files:
    content = Path(file).read_text(encoding="utf-8")
    
    # execute_cognitive_plan(..., user_id="test_user") -> user_id="test_user", session_id="test_session"
    content = re.sub(
        r'user_id="test_user"\s*\)',
        'user_id="test_user", session_id="test_session")',
        content
    )
    
    content = re.sub(
        r'user_id="acceptance_user"\s*\)',
        'user_id="acceptance_user", session_id="acceptance_session")',
        content
    )
    
    # Fix the file path assertion in test_structured_plan_execution
    content = content.replace('assert test_file.read_text() == test_content', 'assert Path("temp_test_acceptance/plan_test.txt").read_text() == test_content')

    Path(file).write_text(content, encoding="utf-8")
print("Tests fixed again!")
