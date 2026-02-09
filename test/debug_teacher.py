
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))
from teacher import Teacher
try:
    t = Teacher()
    print(f"Base URL: {t.client.base_url}")
    print(f"Model: {t.model}")
    print("Sending request...")
    # Access client directly to see full response
    completion = t.client.chat.completions.create(
        model=t.model,
        messages=[{"role": "user", "content": "Write a python function to add two numbers."}],
        max_tokens=1024,
        extra_body={"data": {"thinking": True}} # Try specific NVIDIA format? Or just "thinking": True
        # User said NVIDIA_LLAMA3.1_THINKING_MODE=true
        # Let's try passing it as a top level param in extra_body first?
    )
    # Actually, let's try just 'temperature' etc first? No, those are standard.
    # Let's try strict openai param compatibility.
    # If content is None, maybe it's streaming? No, stream=False default.
    
    # Retying with simple setup first, but checking if we can pass "thinking_mode" in extra_body.
    # Some NVIDIA endpoints use "thinking_mode"
    completion = t.client.chat.completions.create(
        model=t.model,
        messages=[{"role": "user", "content": "Write one sentence about AI."}],
        max_tokens=100,
        extra_body={"thinking_mode": True} 
    )
    print(f"Full Completion: {completion}")
    print(f"Content: {completion.choices[0].message.content}")
except Exception as e:
    print(f"Error: {e}")
