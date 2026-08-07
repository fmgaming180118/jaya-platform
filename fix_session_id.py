import re

TEST_FILES = [
    "JAYA_CORE/tests/test_real_action_loop_unit.py",
    "JAYA_CORE/tests/test_acceptance_real_action_loop.py"
]

for file_path in TEST_FILES:
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # We want to add session_id="test_session" to the bridge method calls.
    # Typically they look like:
    #         user_id="test_user",
    #     )
    
    content = content.replace('user_id="test_user",\n    )', 'user_id="test_user",\n        session_id="test_session",\n    )')
    content = content.replace('user_id="test_user"\n    )', 'user_id="test_user",\n        session_id="test_session"\n    )')
    
    content = content.replace('user_id="acceptance_user",\n        )', 'user_id="acceptance_user",\n            session_id="acceptance_session",\n        )')
    content = content.replace('user_id="acceptance_user"\n        )', 'user_id="acceptance_user",\n            session_id="acceptance_session"\n        )')

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
        
print("Safe session_id patched correctly!")
