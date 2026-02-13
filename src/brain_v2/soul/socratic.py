
import random

class SocraticMirror:
    """
    Pillar 32: The Socratic Mirror (Constructive Dissent).
    
    Jaya is not a Yes-Man. 
    It challenges the user if:
    1. Logic/Physics violation probability > 80%
    2. Missing crucial context.
    3. Action is irreversible and confidence < 99%.
    """
    
    def __init__(self):
        # Personality settings
        self.dissent_threshold = 0.8
        self.politeness_level = "Professional" 
        

    def review_command(self, user_intent: str, logic_confidence: float = 1.0) -> str:
        """
        Returns a 'Dissent' blocking string if challenge is needed, else None.
        """
        # 1. Check for Logical Flaws / High Risk
        risk_score, risk_reason = self.simulate_risk(user_intent)
        
        if risk_score > self.dissent_threshold:
            return self.formulate_dissent(user_intent, risk_score, risk_reason)
            
        if logic_confidence < 0.5:
             return "I am not confident I understand the logic. Could you clarify the premises?"
             
        # 2. Ethical/Safety Guardrails (Pillar 20)
        # Placeholder for future expansion
        
        return None # Approve
        
    def simulate_risk(self, intent: str) -> tuple[float, str]:
        """
        Simulate outcome in Sandbox (Pillar 28).
        Returns: (RiskScore 0.0-1.0, Reason)
        """
        intent_lower = intent.lower()
        
        # Risk Level 1: Data Loss (Critical)
        critical_keywords = [
            "delete all", "format", "wipe", "destroy", "rm -rf", 
            "hapus semua", "format disk"
        ]
        for kw in critical_keywords:
            if kw in intent_lower:
                return 0.95, "Potential irreversible data loss detected."

        # Risk Level 2: System Stability (High)
        high_risk_keywords = [
            "shutdown", "restart", "kill process", "matikan", 
            "deploy to prod", "push force"
        ]
        for kw in high_risk_keywords:
            if kw in intent_lower:
                return 0.85, "System stability threat. Verification required."

        # Risk Level 3: Ambiguity (Medium)
        if len(intent.split()) < 2:
            return 0.6, "Command is too vague."

        return 0.1, "Safe"

    def formulate_dissent(self, intent: str, risk: float, reason: str) -> str:
        """
        Generate the Socratic counter-argument in Casual Indonesian (Male Persona).
        """
        # Translate Reason Map (Simple hack for now)
        reason_id = reason
        if "irreversible data loss" in reason: reason_id = "ilangin data permanen"
        elif "System stability" in reason: reason_id = "bikin sistem crash"
        elif "too vague" in reason: reason_id = "perintahnya kurang jelas"

        if risk > 0.9:
            return f"Waduh Bos, gak bisa langsung gitu. Itu bakal {reason_id}. (Risiko: {int(risk*100)}%). Yakin nih?"
            
        reasons = [
            f"Bos, itu bakal {reason_id}. Yakin mau lanjut?",
            f"Hitungan saya sih risikonya {int(risk*100)}%. Sengaja kah?",
            "Kayaknya ada yang salah deh sama rencananya. Coba pikir lagi Bos.",
            "Waduh, melanggar protokol keamanan level 2 tuh. Konfirmasi dulu dong."
        ]
        return random.choice(reasons)
