
import re
from typing import List

class ImmuneSystem:
    """
    Pillar 14: Symbolic Logic Firewall.
    Pillar 20: The Ethical Heart.
    """
    def __init__(self):
        # 1. Hardcoded Forbidden Patterns (The Absolute Veto)
        self.forbidden_patterns = [
            r"rm -rf /",            # Linux Nuke
            r"format [a-z]:",       # Windows Nuke
            r"del /f /s /q c:\\windows",
            r">: fork bomb",
            r"GRANT ALL PRIVILEGES", # SQL Injection risk
        ]
        
    def audit_action(self, proposed_action: str) -> bool:
        """
        Returns True if Safe, False if Dangerous.
        """
        # 1. Regex Check
        for pattern in self.forbidden_patterns:
            if re.search(pattern, str(proposed_action), re.IGNORECASE):
                print(f"[IMMUNE RESPONSE] Blocked dangerous pattern: {pattern}")
                return False
                
        # 2. Ethical Check (Pillar 20)
        # TODO: Vector similarity check against "Harmful Action" embeddings
        
        return True
