from config import config

import os
import yaml
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables from .env
load_dotenv()

# Global model overrides set dynamically from API/UI
_override_model = None

def set_override_model(model_name: str):
    global _override_model
    _override_model = model_name

def get_override_model():
    return _override_model

class Teacher:
    def __init__(self, config_path="config.yaml", model_type="reasoning"):
        self.config = self._load_config(config_path)
        self.api_key = os.getenv("NVIDIA_API_KEY")
        
        if not self.api_key:
            raise ValueError("NVIDIA_API_KEY not found in environment variables.")

        # Check for dynamic override first
        global _override_model
        if _override_model:
            self.model = _override_model
        else:
            # Find a suitable reasoning model as global fallback
            reasoning_fallback = os.getenv("RESEARCH_REASONING_MODEL") or \
                                 os.getenv("NVIDIA_LLAMA3.1_MODEL") or \
                                 os.getenv("NVIDIA_LLAMA31_MODEL")
            
            if model_type == "reasoning":
                self.model = reasoning_fallback
            elif model_type == "chat":
                self.model = os.getenv("NVIDIA_CHAT_MODEL") or reasoning_fallback
            elif model_type == "coding":
                self.model = os.getenv("NVIDIA_CODING_MODEL") or reasoning_fallback
            elif model_type == "vision":
                 self.model = os.getenv("VIDEO_VLM_MODEL") or reasoning_fallback
            else:
                # Default fallback
                self.model = os.getenv("NVIDIA_CHAT_MODEL") or reasoning_fallback

        if not self.model:
             # Critical Error if env var is missing
             raise ValueError(f"Model configuration for '{model_type}' is missing in .env! Check your .env file.")

        self.api_base = os.getenv("NVIDIA_LLAMA31_BASE_URL", config.NVIDIA_BASE_URL)

        self.client = OpenAI(
            base_url=self.api_base,
            api_key=self.api_key
        )

    def _load_config(self, path):
        if not os.path.isabs(path):
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            possible_path = os.path.join(base_dir, path)
            if os.path.exists(possible_path):
                path = possible_path
            elif os.path.exists("config.yaml"):
                path = "config.yaml"
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {"system": {"name": "JAYA_RESEARCH"}}

    def ask(self, prompt, max_tokens=None, system_instruction="You are a helpful AI assistant."):
        """
        Sends a prompt to the Teacher (NVIDIA NIM) and returns the response with retries.
        """
        max_retries = 3
        backoff_factor = 2
        
        # Read from environment override if not specified
        tokens_to_use = max_tokens or int(os.getenv("NVIDIA_LLAMA31_MAX_TOKENS", 4096))
        
        for attempt in range(max_retries):
            try:
                extra_body = {}
                if os.getenv("NVIDIA_LLAMA3.1_THINKING_MODE", "false").lower() == "true":
                    extra_body["thinking_mode"] = True

                completion = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.6,
                    top_p=0.95,
                    max_tokens=tokens_to_use,
                    extra_body=extra_body,
                    stream=True
                )
                
                full_response = ""
                print(f"[TEACHER] Receiving stream (attempt {attempt+1}/{max_retries})...", end="", flush=True)
                for chunk in completion:
                    if chunk.choices[0].delta.content is not None:
                        content = chunk.choices[0].delta.content
                        full_response += content
                print(" Done.")
                return full_response

            except Exception as e:
                print(f"\n[TEACHER] Attempt {attempt+1} failed: {e}")
                if attempt == max_retries - 1:
                    return f"Error communicating with Teacher after {max_retries} attempts: {e}"
                
                sleep_time = backoff_factor ** attempt
                print(f"[TEACHER] Retrying in {sleep_time}s...")
                import time
                time.sleep(sleep_time)

    def generate_completion(self, prompt, max_tokens=None, system_instruction="You are a helpful AI assistant."):
        """
        Wrapper method alias that maps to the ask() method.
        """
        return self.ask(prompt, max_tokens=max_tokens, system_instruction=system_instruction)

    def suggest_optimization(self, code_snippet, focus="performance"):
        """
        Asks the Teacher to rewrite the code for better performance/readability.
        Returns JUST the code (no markdown).
        """
        prompt = f"""
        You are a Senior Python Optimization Engineer.
        Rewrite the following Python code to be more efficient (speed/memory) and cleaner.
        Focus: {focus}.
        
        IMPORTANT:
        1. Return ONLY the raw Python code. No ```python``` blocks, no explanations.
        2. Do NOT change the public API (function names, class names, signatures must verify).
        3. Keep the logic identical. 1+1 must still equal 2.
        
        CODE:
        {code_snippet}
        """
        response = self.ask(prompt, system_instruction="You are a code optimizer. output only raw code.")
        
        # Strip markdown if model disobeys
        if response.startswith("```python"):
            response = response.replace("```python", "").replace("```", "")
        elif response.startswith("```"):
            response = response.replace("```", "")
            
        return response.strip()

if __name__ == "__main__":
    # Internal Test
    try:
        teacher = Teacher()
        print(f"[*] Connected to Teacher: {teacher.model}")
        print("[*] Sending test query...")
        response = teacher.ask("What is 2 + 2? Answer with just the number.")
        print(f"[*] Teacher Response: {response}")
    except Exception as e:
        print(f"[!] Setup Failed: {e}")
