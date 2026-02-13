
import os
import yaml
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables from .env
load_dotenv()

class Teacher:
    def __init__(self, config_path="config.yaml", model_type="reasoning"):
        self.config = self._load_config(config_path)
        self.api_key = os.getenv("NVIDIA_API_KEY")
        
        if not self.api_key:
            raise ValueError("NVIDIA_API_KEY not found in environment variables.")

        # Dynamic Model Selection based on Role
        # STRICT NO-HARDCODING POLICY
        if model_type == "reasoning":
            self.model = os.getenv("NVIDIA_LLAMA31_MODEL")
        elif model_type == "chat":
            self.model = os.getenv("NVIDIA_CHAT_MODEL")
        elif model_type == "coding":
            self.model = os.getenv("NVIDIA_CODING_MODEL")
        elif model_type == "vision":
             self.model = os.getenv("VIDEO_VLM_MODEL") # Fallback if used in Teacher
        else:
            # Default fallback to Chat if unknown
            self.model = os.getenv("NVIDIA_CHAT_MODEL")

        if not self.model:
             # Critical Error if env var is missing
             raise ValueError(f"Model configuration for '{model_type}' is missing in .env! Check your .env file.")

        self.api_base = os.getenv("NVIDIA_LLAMA31_BASE_URL", "https://integrate.api.nvidia.com/v1")

        self.client = OpenAI(
            base_url=self.api_base,
            api_key=self.api_key
        )

    def _load_config(self, path):
        with open(path, "r") as f:
            return yaml.safe_load(f)

    def ask(self, prompt, system_instruction="You are a helpful AI assistant."):
        """
        Sends a prompt to the Teacher (NVIDIA NIM) and returns the response.
        """
        try:
            extra_body = {}
            if os.getenv("NVIDIA_LLAMA3.1_THINKING_MODE", "false").lower() == "true":
                extra_body["thinking_mode"] = True

            # User suggested streaming for 253b, likely to avoid timeouts
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.6, # User indicated 0.6
                top_p=0.95,
                max_tokens=4096, # Increased from 1024
                extra_body=extra_body,
                stream=True
            )
            
            full_response = ""
            print("[TEACHER] Receiving stream...", end="", flush=True)
            for chunk in completion:
                if chunk.choices[0].delta.content is not None:
                    content = chunk.choices[0].delta.content
                    full_response += content
                    # Optional: print dots or content to show aliveness
                    # print(".", end="", flush=True) 
            print(" Done.")
            return full_response

        except Exception as e:
            return f"Error communicating with Teacher: {e}"

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
