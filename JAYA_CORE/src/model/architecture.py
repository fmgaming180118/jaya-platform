"""
JAYA Librarian Core V0 Architecture
Separates Parametric Intelligence from Non-Parametric Knowledge.
Wraps a HuggingFace base model and implements structured JSON output parsing for the Librarian Loop.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
import os

try:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    HAS_TRANSFORMERS = True
except ImportError:
    HAS_TRANSFORMERS = False

logger = logging.getLogger("JayaLibrarianCore")

class BootstrapLibrarianModel:
    def __init__(self, model_name_or_path: str = "HuggingFaceTB/SmolLM-135M", device: str = "cpu"):
        self.model_name_or_path = model_name_or_path
        self.device = device
        self.model = None
        self.tokenizer = None
        self._is_loaded = False

    def load(self, local_artifact_path: Optional[str] = None):
        """Loads the model and tokenizer from HF Hub or a local artifact path."""
        if not HAS_TRANSFORMERS:
            raise ImportError("HuggingFace 'transformers' and 'torch' are required to run the Librarian Core.")
            
        load_path = local_artifact_path if local_artifact_path and os.path.exists(local_artifact_path) else self.model_name_or_path
        logger.info(f"Loading JAYA Librarian Core from {load_path} to {self.device}...")
        
        self.tokenizer = AutoTokenizer.from_pretrained(load_path)
        # Handle padding token if missing
        if self.tokenizer.pad_token is None:
            if self.tokenizer.eos_token:
                self.tokenizer.pad_token = self.tokenizer.eos_token
            else:
                self.tokenizer.add_special_tokens({'pad_token': '[PAD]'})
                
        self.model = AutoModelForCausalLM.from_pretrained(load_path)
        
        # If we added a pad token, we might need to resize embeddings, but usually SmolLM has eos
        if len(self.tokenizer) > self.model.config.vocab_size:
            self.model.resize_token_embeddings(len(self.tokenizer))
            
        self.model.to(self.device)
        self.model.eval()
        self._is_loaded = True
        logger.info("Bootstrap Librarian Model loaded successfully.")

    def _generate_text(self, prompt: str, max_new_tokens: int = 512, temperature: float = 0.3) -> str:
        """Raw generation wrapper."""
        if not self._is_loaded:
            raise RuntimeError("Model is not loaded. Call .load() first.")
            
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
        
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                temperature=temperature,
                do_sample=True if temperature > 0 else False,
                pad_token_id=self.tokenizer.pad_token_id,
                eos_token_id=self.tokenizer.eos_token_id
            )
            
        generated_ids = outputs[0][inputs.input_ids.shape[1]:]
        return self.tokenizer.decode(generated_ids, skip_special_tokens=True)
        
    def reason_and_respond(self, query: str, context_blocks: List[str] = None) -> Dict[str, Any]:
        """
        The core generation function. It produces structured output.
        The prompt forces the model to respond in JSON containing:
        - information_needs: list of strings
        - retrieval_required: bool
        - retrieval_queries: list of strings
        - answer: string
        - evidence_refs: list of strings
        - confidence: float
        """
        context_str = ""
        if context_blocks:
            context_str = "EVIDENCE LIBRARY:\n" + "\n---\n".join(context_blocks) + "\n\n"
            
        prompt = f"""You are JAYA Librarian Core, an expert assistant that reasons step-by-step and strictly outputs JSON.
You do NOT hallucinate facts. If the information is not in the EVIDENCE LIBRARY and you don't know it, you set retrieval_required to true.
If there are no context blocks, you must request retrieval by generating retrieval_queries.

{context_str}
USER QUERY: {query}

Respond in the following JSON format ONLY:
{{
  "information_needs": ["..."],
  "retrieval_required": true/false,
  "retrieval_queries": ["..."],
  "answer": "...",
  "evidence_refs": ["..."],
  "confidence": 0.0-1.0
}}
"""
        raw_output = self._generate_text(prompt, max_new_tokens=512, temperature=0.1)
        
        # Try to parse JSON
        try:
            # Extract JSON block if surrounded by markdown or other text
            start_idx = raw_output.find("{")
            end_idx = raw_output.rfind("}")
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_str = raw_output[start_idx:end_idx+1]
                return json.loads(json_str)
            else:
                return json.loads(raw_output)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse model output as JSON. Raw output: {raw_output}")
            return {
                "information_needs": ["Failed to parse model response"],
                "retrieval_required": False,
                "retrieval_queries": [],
                "answer": "Error: Model produced invalid format.",
                "evidence_refs": [],
                "confidence": 0.0
            }
