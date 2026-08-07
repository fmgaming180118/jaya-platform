import os
import re

TEST_FILES = [
    "JAYA_CORE/tests/test_real_action_loop_unit.py",
    "JAYA_CORE/tests/test_acceptance_real_action_loop.py"
]

for file_path in TEST_FILES:
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Update the helper function to accept **kwargs to ignore ttl_seconds etc
    # and update the signature
    old_helper_sig = '''def create_approval_receipt(
    user_id: str,
    session_id: str,
    action: str,
    resource: str,
    request_digest: str,
) -> ApprovalReceipt:'''
    new_helper_sig = '''def create_approval_receipt(
    user_id: str,
    session_id: str,
    action: str,
    resource: str,
    request_digest: str,
    **kwargs
) -> ApprovalReceipt:'''
    content = content.replace(old_helper_sig, new_helper_sig)
    
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
        
print("Tests patched!")
