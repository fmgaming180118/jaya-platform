"""
intent.py — Domain-neutral Intent Engine for JAYA Core.
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List

from .contracts import Intent, IntentType


class IntentEngine:
    """Domain-neutral Intent Engine extracting Intent & entities from prompts."""

    def detect_intent(self, prompt: str, context: Dict[str, Any] | None = None) -> Intent:
        p_lower = prompt.lower().strip()
        context_dict = dict(context or {})

        # Compute hash for intent_id
        suffix = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:8]
        intent_id = f"int-{suffix}"

        entities: Dict[str, Any] = {}
        missing: List[str] = []

        if "casing" in p_lower or "3d" in p_lower or "cad" in p_lower:
            intent_type = IntentType.CREATE_3D_DESIGN
            domain = "cad.parametric_modeling"
            entities["object_type"] = "mini_pc_case" if "pc" in p_lower else "3d_object"
            if "airflow" in p_lower:
                entities["airflow"] = "front_to_back" if "depan ke belakang" in p_lower else "general"

            if "motherboard_size" not in context_dict and "dimensi" not in p_lower:
                missing.append("motherboard_size")
            if "gpu_dimension" not in context_dict and "gpu" not in p_lower:
                missing.append("gpu_dimension")

        elif "eksekusi kode" in p_lower or "jalankan kode" in p_lower or "run code" in p_lower:
            intent_type = IntentType.WRITE_CODE
            domain = "software_engineering"
            entities["language"] = "python" if "python" in p_lower else "general"

        elif "buat rencana" in p_lower or "buatkan rencana" in p_lower or "rapikan" in p_lower or "susun" in p_lower:
            intent_type = IntentType.CREATE_PLAN
            domain = "planning"
            # Extract topic and duration from input
            import re
            # Look for "belajar X" or "rencana X" or "buat rencana X"
            match = re.search(r'(?:belajar|rencana|buat rencana|buatkan rencana)\s+(\w+(?:\s+\w+)*)', p_lower)
            if match:
                entities["topic"] = match.group(1)
            
            # Extract duration
            duration_match = re.search(r'(\d+\s*(?:hari|minggu|bulan|tahun))', p_lower)
            if duration_match:
                entities["duration"] = duration_match.group(1)

        elif "program" in p_lower or "kode" in p_lower or "script" in p_lower or "python" in p_lower:
            intent_type = IntentType.WRITE_CODE
            domain = "software_engineering"
            entities["language"] = "python" if "python" in p_lower else "general"

        elif "lampu" in p_lower or "saklar" in p_lower or "perangkat" in p_lower or "suhu" in p_lower:
            intent_type = IntentType.CONTROL_DEVICE
            domain = "home_automation"

        elif "ingat" in p_lower or "simpan" in p_lower or "catat" in p_lower:
            intent_type = IntentType.MANAGE_MEMORY
            domain = "memory"

        elif "siapa" in p_lower or "apa" in p_lower or "bagaimana" in p_lower or "jelaskan" in p_lower or "cari tahu" in p_lower:
            intent_type = IntentType.ASK_INFORMATION
            domain = "general"

        else:
            intent_type = IntentType.EXECUTE_TASK
            domain = "general"
            # Low confidence for unrecognized input
            confidence = 0.3

        clarification = len(missing) > 0 and intent_type == IntentType.CREATE_3D_DESIGN

        return Intent(
            intent_id=intent_id,
            intent_type=intent_type,
            domain=domain,
            confidence=confidence if 'confidence' in locals() else (0.9 if intent_type != IntentType.UNKNOWN else 0.4),
            extracted_entities=entities,
            missing_context=missing,
            clarification_required=clarification,
        )
