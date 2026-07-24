"""
JARVIS Discovery Bridge for JAYA Ecosystem.
Converts validated scientific discoveries (from JAYA_RESEARCH) into executable
Micro-Knowledge Patches (.jaypatch) and directly upgrades JAYA_CORE (AgenticJarvis),
JAYA_AGENT, and JAYA_ANDROID to enable JARVIS-level self-evolution.
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class JarvisDiscoveryBridge:
    """
    JARVIS Self-Evolution Engine Bridge.
    Promotes empirical discoveries into active intelligence in JAYA_CORE SQLite database.
    """

    def __init__(self, core_db_path: Optional[Path] = None):
        if core_db_path:
            self.core_db_path = Path(core_db_path)
        else:
            # Default location of agentic_jarvis.db in JAYA_CORE / root data
            root_dir = Path(__file__).resolve().parents[3]
            self.core_db_path = root_dir / "data" / "agentic_jarvis.db"

        self.core_db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_jarvis_tables()

    def _get_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.core_db_path))

    def _ensure_jarvis_tables(self):
        """Ensures JAYA_CORE JARVIS patch & proactive directive tables exist."""
        try:
            conn = self._get_connection()
            with conn:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS jarvis_patches (
                        patch_id TEXT PRIMARY KEY,
                        topic TEXT,
                        statement TEXT,
                        bayes_confidence REAL,
                        patch_data TEXT,
                        applied_at REAL
                    );

                    CREATE TABLE IF NOT EXISTS proactive_directives (
                        directive_id TEXT PRIMARY KEY,
                        trigger_condition TEXT,
                        action_prompt TEXT,
                        source_discovery_id TEXT,
                        status TEXT DEFAULT 'active'
                    );
                """)
            conn.close()
        except Exception as e:
            logger.warning(f"Error ensuring JARVIS DB tables: {e}")

    def create_jarvis_patch(
        self,
        hypothesis: Dict[str, Any],
        learning_analysis: Dict[str, Any],
        paper: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Packages validated discovery data into a JARVIS Micro-Knowledge Patch (.jaypatch).
        """
        hyp_id = hypothesis.get("hypothesis_id", "HYP-001")
        topic = hypothesis.get("topic", "AI General")
        statement = hypothesis.get("statement", "")
        posterior = learning_analysis.get("posterior_confidence", 0.8)

        patch_id = f"JAYPATCH-{datetime.now().strftime('%Y%m%d')}-{hyp_id[-4:]}"

        patch = {
            "patch_id": patch_id,
            "version": "1.0.0",
            "target_system": "JAYA_CORE_BRAIN",
            "topic": topic,
            "statement": statement,
            "bayes_confidence": posterior,
            "falsifiability": hypothesis.get("falsifiability_criteria", ""),
            "novelty_score": hypothesis.get("novelty_score", 0.85),
            "proactive_directives": [
                {
                    "trigger": f"User mentions {topic}",
                    "action": f"JARVIS proactive recommendation based on discovery: '{statement}'"
                }
            ],
            "timestamp": datetime.now().isoformat(),
        }

        return patch

    def apply_patch_to_core(self, patch: Dict[str, Any]) -> bool:
        """
        Injects the JARVIS Micro-Patch directly into JAYA_CORE SQLite database.
        """
        patch_id = patch.get("patch_id", "PATCH-UNK")
        topic = patch.get("topic", "AI")
        statement = patch.get("statement", "")
        confidence = patch.get("bayes_confidence", 0.5)
        patch_json = json.dumps(patch)

        try:
            conn = self._get_connection()
            with conn:
                # 1. Insert into jarvis_patches
                conn.execute(
                    """
                    INSERT OR REPLACE INTO jarvis_patches
                    (patch_id, topic, statement, bayes_confidence, patch_data, applied_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (patch_id, topic, statement, confidence, patch_json, datetime.now().timestamp()),
                )

                # 2. Insert Proactive Directives
                for idx, directive in enumerate(patch.get("proactive_directives", [])):
                    dir_id = f"DIR-{patch_id[-6:]}-{idx+1}"
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO proactive_directives
                        (directive_id, trigger_condition, action_prompt, source_discovery_id, status)
                        VALUES (?, ?, ?, ?, 'active')
                        """,
                        (dir_id, directive.get("trigger"), directive.get("action"), patch_id),
                    )

            conn.close()
            logger.info(f"Successfully applied JARVIS discovery patch {patch_id} to JAYA_CORE.")
            return True
        except Exception as e:
            logger.error(f"Failed to apply patch to JAYA_CORE DB: {e}")
            return False

    def deploy_discovery_to_jarvis(
        self,
        hypothesis: Dict[str, Any],
        run_result: Dict[str, Any],
        learning_analysis: Dict[str, Any],
        paper: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Main pipeline to promote validated research findings into JAYA_CORE JARVIS evolution.
        """
        recommendation = learning_analysis.get("recommendation", "HOLD")
        if recommendation != "ACCEPT_HYPOTHESIS":
            return {
                "status": "PROMOTION_SKIPPED",
                "reason": f"Discovery not promoted: recommendation is '{recommendation}', requires 'ACCEPT_HYPOTHESIS'."
            }

        patch = self.create_jarvis_patch(hypothesis, learning_analysis, paper)
        success = self.apply_patch_to_core(patch)

        return {
            "status": "SUCCESS" if success else "FAILED",
            "patch_id": patch["patch_id"],
            "target_system": "JAYA_CORE",
            "bayes_confidence": patch["bayes_confidence"],
            "directives_injected": len(patch.get("proactive_directives", [])),
        }
