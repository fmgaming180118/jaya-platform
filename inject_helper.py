import re

TEST_FILES = [
    "JAYA_CORE/tests/test_real_action_loop_unit.py",
    "JAYA_CORE/tests/test_acceptance_real_action_loop.py"
]

helper = '''
def create_approval_receipt(
    user_id: str,
    session_id: str,
    action: str,
    resource: str,
    request_digest: str,
    **kwargs
) -> ApprovalReceipt:
    authority = ApprovalAuthority()
    return authority.issue_receipt(
        user_id=user_id,
        session_id=session_id,
        action=action,
        resource=resource,
        request_digest=request_digest,
        ttl_seconds=300.0,
    )
'''

for file_path in TEST_FILES:
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    if "def create_approval_receipt(" not in content:
        content = content.replace("import pytest\n", f"import pytest\n{helper}")
        
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
        
print("Helper injected!")
