"""
Librarian Retrieval Loop
Implements iterative retrieval to ground model answers in Non-Parametric Knowledge.
"""

import logging
from typing import Dict, Any, List

from JAYA_CORE.src.model.native_architecture import NativeJayaLibrarianRuntime
from JAYA_CORE.src.library.library_manager import LibraryManager

logger = logging.getLogger("LibrarianLoop")

class LibrarianLoop:
    def __init__(self, model_path: str = "JAYA_CORE/models/jaya-core-v0", allow_bootstrap_fallback: bool = False):
        self.model = NativeJayaLibrarianRuntime(model_dir=model_path)
        self.library = LibraryManager()
        self.max_rounds = 3
        self.allow_bootstrap_fallback = allow_bootstrap_fallback
        
        try:
            self.model.load()
        except Exception as e:
            logger.error(f"Failed to load native model: {e}")
            if self.allow_bootstrap_fallback:
                logger.warning("Falling back to Bootstrap model.")
                from JAYA_CORE.src.model.architecture import BootstrapLibrarianModel
                self.model = BootstrapLibrarianModel(model_name_or_path=model_path)
                try:
                    self.model.load()
                except Exception as e_boot:
                    logger.error(f"Bootstrap model also failed: {e_boot}")
                    self.model._is_loaded = False
            else:
                logger.error("Native model unavailable and fallback not allowed.")
                self.model._is_loaded = False

    def run(self, query: str) -> Dict[str, Any]:
        """
        Executes the iterative retrieval loop.
        """
        if not self.model._is_loaded:
            return {
                "status": "NATIVE_MODEL_UNAVAILABLE",
                "message": "Dependency Error: transformers/torchvision is broken or missing, or native weights failed to load.",
                "answer": "Cannot run inference due to missing model dependencies."
            }

        context_blocks = []
        retrieved_refs = set()
        
        for round_idx in range(self.max_rounds):
            logger.info(f"Librarian Loop Round {round_idx + 1}")
            
            response = self.model.reason_and_respond(query, context_blocks)
            
            if not response.get("retrieval_required", False):
                model_refs = set(response.get("evidence_refs", []))
                invalid_refs = model_refs - retrieved_refs
                
                if invalid_refs:
                    return {
                        "status": "INVALID_EVIDENCE_REFERENCE",
                        "rounds": round_idx + 1,
                        "answer": "Model hallucinated evidence references.",
                        "evidence_refs": list(invalid_refs),
                        "confidence": 0.0
                    }
                    
                valid_refs = list(model_refs)
                
                # Check for invalid output
                if "Failed to parse model response" in response.get("information_needs", []):
                    return {
                        "status": "MODEL_OUTPUT_INVALID",
                        "rounds": round_idx + 1,
                        "answer": response.get("answer", ""),
                        "evidence_refs": [],
                        "confidence": 0.0
                    }
                    
                if not valid_refs:
                    return {
                        "status": "INVALID_EVIDENCE_REFERENCE",
                        "rounds": round_idx + 1,
                        "answer": "Answer provided with zero evidence refs.",
                        "evidence_refs": [],
                        "confidence": 0.0
                    }
                    
                # The model is confident it has the answer or knows it doesn't need more info
                logger.info("Model finalized answer.")
                return {
                    "status": "LIBRARY_GROUNDED",
                    "rounds": round_idx + 1,
                    "answer": response.get("answer", ""),
                    "evidence_refs": valid_refs,
                    "confidence": response.get("confidence", 0.0)
                }
                
            queries = response.get("retrieval_queries", [])
            if not queries:
                logger.warning("Model requested retrieval but provided no queries. Breaking loop.")
                break
                
            # Perform retrieval
            new_evidence_found = False
            for q in queries:
                results = self.library.retrieve_evidence(q, top_k=2)
                for res in results:
                    if res["ref_id"] not in retrieved_refs:
                        context_blocks.append(f"[Source: {res['ref_id']}]\n{res['content']}")
                        retrieved_refs.add(res["ref_id"])
                        new_evidence_found = True
                        
            if not new_evidence_found:
                logger.warning("Retrieval yielded no new evidence. Forcing model to answer.")
                # Force final answer by stripping retrieval_queries from prompt or just taking current answer
                return {
                    "status": "INSUFFICIENT_EVIDENCE",
                    "rounds": round_idx + 1,
                    "answer": "I do not have enough evidence to answer this query.",
                    "evidence_refs": list(retrieved_refs),
                    "confidence": 0.0
                }

        # Max rounds reached
        logger.warning(f"Reached max retrieval rounds ({self.max_rounds}). Forcing termination.")
        response = self.model.reason_and_respond(query, context_blocks)
        
        model_refs = set(response.get("evidence_refs", []))
        invalid_refs = model_refs - retrieved_refs
        if invalid_refs:
            return {
                "status": "INVALID_EVIDENCE_REFERENCE",
                "rounds": self.max_rounds,
                "answer": "Model hallucinated evidence references on forced termination.",
                "evidence_refs": list(invalid_refs),
                "confidence": 0.0
            }
            
        valid_refs = list(model_refs)
        if not valid_refs:
            return {
                "status": "INVALID_EVIDENCE_REFERENCE",
                "rounds": self.max_rounds,
                "answer": "Answer provided with zero evidence refs on forced termination.",
                "evidence_refs": [],
                "confidence": 0.0
            }
            
        return {
            "status": "RETRIEVAL_BUDGET_EXHAUSTED",
            "rounds": self.max_rounds,
            "answer": response.get("answer", "Terminated before definitive answer."),
            "evidence_refs": valid_refs,
            "confidence": response.get("confidence", 0.0)
        }
