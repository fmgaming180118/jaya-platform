"""
Video Processor Adapter
Integrates logic from AI-Q Video Search & Summarization Blueprint.
Uses:
- yt-dlp for download
- OpenCV for frame extraction
- NVIDIA NIM (VILA/GPT-4V) for visual analysis
- OpenAI Whisper (Local) for audio transcription
"""
import os
import cv2
import base64
import requests
import json
import yt_dlp
from pathlib import Path
from typing import Dict, Any, List
import concurrent.futures

class VideoProcessor:
    def __init__(self):
        self.download_dir = Path("data/video_cache")
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.api_key = os.getenv("NVIDIA_API_KEY")
        # NVIDIA VILA or similar VLM hosted on NIM
        self.vlm_endpoint = "https://integrate.api.nvidia.com/v1/chat/completions" 
        self.model_name = "nvidia/vila-1.5-40b" # Or equivalent available NIM

    def process_video(self, url: str) -> Dict[str, Any]:
        """Full pipeline: Download -> Analyze -> Transcribe -> Merge"""
        print(f"[VIDEO] Processing: {url}")
        
        # 1. Download
        video_path, audio_path, metadata = self._download_media(url)
        
        # 2. Parallel Analysis (Visual + Audio)
        with concurrent.futures.ThreadPoolExecutor() as executor:
            visual_future = executor.submit(self._analyze_visuals, video_path)
            # audio_future = executor.submit(self._transcribe_audio, audio_path) # TODO: Add Whisper
            
            visual_summary = visual_future.result()
            # transcript = audio_future.result()
            transcript = "[Audio Transcription Placeholder]" 

        # 3. Synthesis
        final_report = self._synthesize_report(metadata, visual_summary, transcript)
        
        return {
            "status": "success",
            "title": metadata.get('title', 'Unknown Video'),
            "report": final_report,
            "video_path": str(video_path)
        }

    def _download_media(self, url: str):
        ydl_opts = {
            'format': 'best[ext=mp4]',
            'outtmpl': str(self.download_dir / '%(id)s.%(ext)s'),
            'quiet': True,
            'metrics': False
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_path = self.download_dir / f"{info['id']}.mp4"
            audio_path = video_path # For simplicity, using same file
            return video_path, audio_path, info

    def _analyze_visuals(self, video_path: Path) -> List[Dict]:
        """Sample frames and get VLM descriptions"""
        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps
        
        # Sample 1 frame every 30 seconds (adjust for density)
        interval_sec = 30 
        interval_frames = int(fps * interval_sec)
        
        descriptions = []
        
        for frame_idx in range(0, total_frames, interval_frames):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret: break
            
            timestamp = frame_idx / fps
            b64_frame = self._encode_image(frame)
            
            desc = self._query_vlm(b64_frame, "Describe the tactical formation and player positioning in this frame.")
            descriptions.append({
                "timestamp": timestamp,
                "description": desc
            })
            print(f"[VIDEO] Analyzed frame at {timestamp:.1f}s")
            
        cap.release()
        return descriptions

    def _encode_image(self, frame):
        _, buffer = cv2.imencode(".jpg", frame)
        return base64.b64encode(buffer).decode("utf-8")

    def _query_vlm(self, b64_image: str, prompt: str) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"}}
                    ]
                }
            ],
            "max_tokens": 512
        }
        
        try:
            res = requests.post(self.vlm_endpoint, headers=headers, json=payload)
            res.raise_for_status()
            return res.json()['choices'][0]['message']['content']
        except Exception as e:
            print(f"[VLM Error] {e}")
            return "Analysis failed."

    def _synthesize_report(self, metadata, visuals, transcript):
        """Combine into Markdown"""
        lines = [f"# Video Analysis: {metadata.get('title')}", ""]
        lines.append(f"**URL:** {metadata.get('webpage_url')}")
        lines.append(f"**Duration:** {metadata.get('duration')}s")
        lines.append("## Visual Logic Stream")
        
        for item in visuals:
            timestamp = time.strftime('%H:%M:%S', time.gmtime(item['timestamp']))
            lines.append(f"### ⏱ {timestamp}")
            lines.append(item['description'])
            lines.append("")
            
        lines.append("## Audio Transcript")
        lines.append(transcript)
        
        return "\n".join(lines)

import time
