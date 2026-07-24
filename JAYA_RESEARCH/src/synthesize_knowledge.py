from config import config
import os
import sys
import glob
from pathlib import Path
from dotenv import load_dotenv
import requests

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from src.research.video_processor import VideoProcessor # Import purely for potentially needed utils, or skip

def generate_knowledge_synthesis(all_reports_content):
    """
    Synthesize multiple video reports into a single Knowledge Artifact using Llama 3.1 Nemotron.
    """
    print("\n[SYNTHESIS] Generating Consolidated Knowledge Artifact...")
    
    api_key = os.getenv("NVIDIA_API_KEY")
    model = os.getenv("NVIDIA_LLAMA31_MODEL") or os.getenv("NVIDIA_LLAMA3.1_MODEL") or config.NVIDIA_REASONING_MODEL
    invoke_url = (os.getenv("NVIDIA_LLAMA31_BASE_URL") or os.getenv("NVIDIA_LLAMA3.1_BASE_URL") or config.NVIDIA_BASE_URL) + "/chat/completions"
    
    prompt = f"""
    You are JAYA_RESEARCH, an advanced AI Researcher.
    
    TASK:
    Analyze the following raw observational reports from video analysis sessions. 
    Some reports might be incomplete due to processing limits; focus on the completed ones.
    
    Synthesize them into a single structured "KNOWLEDGE ARTIFACT" (Markdown).
    
    The goal is NOT just a summary, but to extract KNOWLEDGE:
    1. Identify the core topics discussed across the videos.
    2. Extract specific facts, rules, or procedures mentioned (e.g. database schemas, admin rules).
    3. Connect the dots between the visual observations and the audio transcripts.
    4. Format as a professional research document with "Key Insights", "Technical Details", and "Actionable Knowledge".
    
    RAW REPORTS:
    {all_reports_content}
    """
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": int(os.getenv("NVIDIA_LLAMA31_MAX_TOKENS", 1000000)),
        "temperature": 0.5,
        "top_p": 0.95
    }
    
    try:
        response = requests.post(invoke_url, headers=headers, json=payload)
        response.raise_for_status()
        content = response.json()['choices'][0]['message']['content']
        return content
    except Exception as e:
        error_details = str(e)
        if 'response' in locals():
            error_details += f"\nResponse Body: {response.text}"
        print(f"[SYNTHESIS FAILED] {error_details}")
        return f"Failed to synthesize knowledge. Error: {error_details}"

def main():
    reports_dir = PROJECT_ROOT / "reports" / "video_analysis"
    report_files = list(reports_dir.glob("*_report.md"))
    
    print(f"Found {len(report_files)} report files.")
    
    aggregated_content = ""
    for report_file in report_files:
        print(f"Reading: {report_file.name}")
        with open(report_file, "r", encoding="utf-8") as f:
            content = f.read()
            # Filter out known failure reports if they are mostly empty/failed
            if "Analysis failed" in content and len(content) < 2000:
                print(f"Skipping incomplete report: {report_file.name}")
                continue
                
            aggregated_content += f"\n\n=== SOURCE REPORT: {report_file.name} ===\n"
            aggregated_content += content

    if aggregated_content:
        knowledge = generate_knowledge_synthesis(aggregated_content)
        
        knowledge_path = reports_dir / "CONSOLIDATED_KNOWLEDGE.md"
        with open(knowledge_path, "w", encoding="utf-8") as f:
            f.write(knowledge)
            
        print(f"\n✅✅ KNOWLEDGE SYNTHESIS COMPLETE!")
        print(f"File: {knowledge_path}")
    else:
        print("No valid content to synthesize.")

if __name__ == "__main__":
    main()
