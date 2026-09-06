"""
Video Processor Adapter
Integrates logic from AI-Q Video Search & Summarization Blueprint.
Uses:
- yt-dlp for download
- OpenCV for frame extraction
- NVIDIA NIM (VILA/GPT-4V) for visual analysis
- OpenAI Whisper (Local) for audio transcription
"""

from __future__ import annotations

import base64
import concurrent.futures
import os
import re
import subprocess
import time
from functools import wraps
from pathlib import Path
from typing import Any, Dict, List

import cv2
import requests
import static_ffmpeg
import yt_dlp

from jaya_research.config import config  # noqa: E402
from jaya_research.provider_errors import (
    ProviderAuthError,
    ProviderError,
    ProviderInvalidResponseError,
    ProviderPolicy,
    ensure_http_success,
    execute_with_retry,
    select_primary_error,
)

static_ffmpeg.add_paths()

MAX_SAMPLED_VIDEO_FRAMES = 120


class SmartAudioProcessor:
    def split_by_silence(
        self,
        video_path: Path,
        output_dir: Path,
        min_duration: int = 240,
        max_duration: int = 300,
    ) -> List[Path]:
        """
        Split audio into chunks based on silence detection.
        Goal: Chunks between min_duration (4m) and max_duration (5m), cut at silence.
        """
        # 1. Detect silence
        silence_points = self._detect_silences(video_path)

        # 2. Determine split points
        total_duration = self._get_duration(video_path)
        split_points = [0.0]
        current_time = 0.0

        while current_time < total_duration:
            target_time = current_time + max_duration
            if target_time >= total_duration:
                break

            # Find best silence point nearest to target_time (within window)
            # Window: [target_time - 60s, target_time + 60s]
            best_split = None

            # Prefer silence slightly BEFORE max_duration to keep chunks under limit
            search_start = max(current_time + min_duration, 0)
            search_end = min(target_time + 30, total_duration)

            candidates = [s for s in silence_points if search_start <= s <= search_end]

            if candidates:
                # Pick nearest to target (5 mins)
                best_split = min(candidates, key=lambda x: abs(x - target_time))
            else:
                # Hard fallback if no silence found
                best_split = target_time

            split_points.append(best_split)
            current_time = best_split

        split_points.append(total_duration)

        # 3. Create chunks
        chunks = []
        for i in range(len(split_points) - 1):
            start = split_points[i]
            end = split_points[i + 1]
            duration = end - start

            output_path = output_dir / f"smart_chunk_{i:03d}.mp4"
            self._extract_segment(video_path, output_path, start, duration)
            chunks.append(output_path)

        return chunks

    def _detect_silences(
        self, video_path: Path, db_threshold: int = -30, duration: float = 0.5
    ) -> List[float]:
        """Use ffmpeg silencedetect filter to find silence timestamps"""
        cmd = [
            "ffmpeg",
            "-i",
            str(video_path),
            "-af",
            f"silencedetect=noise={db_threshold}dB:d={duration}",
            "-f",
            "null",
            "-",
        ]
        try:
            result = subprocess.run(cmd, stderr=subprocess.PIPE, text=True, check=False)
            output = result.stderr

            # Parse silence_end lines
            # [silencedetect @ 0000...] silence_end: 12.3456 | silence_duration: 1.23
            silence_ends = []
            for line in output.split("\n"):
                if "silence_end" in line:
                    match = re.search(r"silence_end: ([\d\.]+)", line)
                    if match:
                        silence_ends.append(float(match.group(1)))
            return silence_ends
        except Exception as e:
            print(f"[SMART AUDIO] Silence detection failed: {e}")
            return []

    def _get_duration(self, video_path: Path) -> float:
        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=True)
            return float(result.stdout.strip())
        except (OSError, subprocess.SubprocessError, ValueError):
            return 0.0

    def _extract_segment(
        self, input_path: Path, output_path: Path, start: float, duration: float
    ):
        # Precise extraction
        cmd = [
            "ffmpeg",
            "-ss",
            str(start),
            "-i",
            str(input_path),
            "-t",
            str(duration),
            "-c",
            "copy",
            "-y",  # Copy codec is fast/lossless
            str(output_path),
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class AdaptiveVisualSampler:
    def sample_frames(
        self,
        video_path: Path,
        diff_threshold: float = 30.0,
        min_interval: float = 1.0,
        max_interval: float = 60.0,
        max_frames: int = MAX_SAMPLED_VIDEO_FRAMES,
    ) -> List[Any]:
        """
        Sample frames based on visual change detection (Scene Change).
        - diff_threshold: Pixel difference average to trigger capture
        - min_interval: Minimum time between frames (to avoid burst)
        - max_interval: Maximum time without frame (force capture)
        - max_frames: Hard upper bound to prevent unbounded in-memory output.
        """
        if not isinstance(max_frames, int) or isinstance(max_frames, bool):
            raise ValueError("max_frames must be an integer")
        if not 1 <= max_frames <= MAX_SAMPLED_VIDEO_FRAMES:
            raise ValueError(
                f"max_frames must be between 1 and {MAX_SAMPLED_VIDEO_FRAMES}"
            )

        cap = cv2.VideoCapture(str(video_path))

        last_frame = None
        last_timestamp = -999.0
        encoded_frames = []

        try:
            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                current_timestamp = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0

                # Grayscale for diff calculation
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                gray = cv2.GaussianBlur(gray, (21, 21), 0)

                should_capture = False

                if last_frame is None:
                    should_capture = True
                else:
                    # Calculate time delta
                    time_delta = current_timestamp - last_timestamp

                    if time_delta < min_interval:
                        continue

                    if time_delta > max_interval:
                        should_capture = True
                    else:
                        # Calculate visual diff
                        diff = cv2.absdiff(last_frame, gray)
                        mean_diff = diff.mean()
                        if mean_diff > diff_threshold:
                            should_capture = True

                if should_capture:
                    # Resize and encode
                    encoded = self._encode_image(frame)
                    encoded_frames.append({"timestamp": current_timestamp, "b64": encoded})
                    last_frame = gray
                    last_timestamp = current_timestamp
                    if len(encoded_frames) >= max_frames:
                        break
        finally:
            cap.release()

        return encoded_frames

    def _encode_image(self, frame):
        # Reuse existing logic or duplicate for independence
        height, width = frame.shape[:2]
        if width > 640:
            scale = 640 / width
            new_height = int(height * scale)
            frame = cv2.resize(frame, (640, new_height))
        _, buffer = cv2.imencode(".jpg", frame)
        return base64.b64encode(buffer).decode("utf-8")


def retry_api(function):
    """Retry only typed transient provider failures within the shared bounds."""

    @wraps(function)
    def wrapper(self, *args, **kwargs):
        return execute_with_retry(
            "nvidia_vlm",
            lambda: function(self, *args, **kwargs),
            self.provider_policy,
        )

    return wrapper


class VideoProcessor:
    def __init__(self):
        self.download_dir = Path(os.getenv("VIDEO_CACHE_DIR", config.VIDEO_CACHE_DIR))
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.api_key = os.getenv("NVIDIA_API_KEY")
        if not self.api_key:
            raise ProviderAuthError(
                "nvidia_vlm",
                "NVIDIA_API_KEY is not configured",
            )

        # NVIDIA VILA or similar VLM hosted on NIM
        self.vlm_endpoint = os.getenv("NVIDIA_VLM_ENDPOINT", config.NVIDIA_VLM_ENDPOINT)
        if not self.vlm_endpoint.startswith("https://"):
            raise ValueError("NVIDIA_VLM_ENDPOINT must use HTTPS")
        self.provider_policy = ProviderPolicy.from_env("NVIDIA_VLM_PROVIDER")

        # STRICT NO-HARDCODING
        self.model_name = os.getenv("VIDEO_VLM_MODEL")
        if not self.model_name:
            raise ValueError("VIDEO_VLM_MODEL not found in .env")

    def process_video(self, url: str) -> Dict[str, Any]:
        """Full pipeline: Download -> Analyze -> Transcribe -> Merge"""
        print(f"[VIDEO] Processing: {url}")

        # 1. Download
        video_path, audio_path, metadata = self._download_media(url)

        # 2. Parallel Analysis (Visual + Audio)
        with concurrent.futures.ThreadPoolExecutor() as executor:
            visual_future = executor.submit(self._analyze_visuals, video_path)
            audio_future = executor.submit(self._transcribe_audio, audio_path)

            visual_summary = visual_future.result()
            transcript = audio_future.result()

        # 3. Synthesis
        final_report = self._synthesize_report(metadata, visual_summary, transcript)

        return {
            "status": "success",
            "title": metadata.get("title", "Unknown Video"),
            "report": final_report,
            "video_path": str(video_path),
        }

    def process_video_chunked(self, url: str) -> Dict[str, Any]:
        """
        Smart Chunked Processing Strategy:
        1. Split Audio smartly (Silence Detection).
        2. Adaptive Visual Sampling (Scene Changes).
        3. Merge Results.
        """
        print(f"[VIDEO] Processing (Smart Strategy): {url}")

        # 1. Download/Locate Source
        video_path, _, metadata = self._download_media(url)

        # 2. Smart Splitting
        cache_dir = self.download_dir / f"chunks_{video_path.stem}"
        cache_dir.mkdir(parents=True, exist_ok=True)

        smart_audio = SmartAudioProcessor()
        chunk_files = smart_audio.split_by_silence(video_path, cache_dir)
        print(f"[VIDEO] Split into {len(chunk_files)} smart chunks (Silence Aware)")

        full_visuals = []
        full_transcript = []

        base_timestamp = 0.0

        # 3. Process Chunks
        for i, chunk_path in enumerate(chunk_files):
            progress = f"{i + 1}/{len(chunk_files)}"
            print(
                f"  > Processing Smart Chunk {progress}: "
                f"{chunk_path.name}"
            )

            # --- Audio (Whisper) ---
            audio_transcript = self._transcribe_audio(chunk_path)
            full_transcript.append(audio_transcript)

            # --- Visual (Adaptive Sampling) ---
            adaptive_sampler = AdaptiveVisualSampler()
            # Sample frames from this chunk only
            visual_frames = adaptive_sampler.sample_frames(
                chunk_path, diff_threshold=30.0, min_interval=1.0, max_interval=60.0
            )

            chunk_visual_desc = "No visual changes detected."
            if visual_frames:
                # Batch process visual frames (max 5 per request to be safe)
                if len(visual_frames) > 5:
                    indices = [int(j * len(visual_frames) / 5) for j in range(5)]
                    selected_frames = [visual_frames[j] for j in indices]
                else:
                    selected_frames = visual_frames

                # Convert relative timestamps into the chunk's absolute timeline.
                # But for final report we want absolute.
                # _synthesize_report expects absolute timestamps in 'timestamp' field.
                # Here we get description for the *chunk*.
                # We should append meaningful visual events with ABSOLUTE timestamps.

                # Query a chunk summary; granular events can be added separately.
                # For now, let's get a summary of the chunk's visuals.
                chunk_visual_desc = self._query_vlm(
                    selected_frames,
                    "Analyze these frames representing visual changes. "
                    "Describe the key visual information, text, or interactions.",
                )

            # Add to full visuals (mapped to chunk start time approx)
            full_visuals.append(
                {"timestamp": base_timestamp, "description": chunk_visual_desc}
            )

            # Calculate actual chunk duration to update base_timestamp
            chunk_duration_actual = smart_audio._get_duration(chunk_path)
            base_timestamp += chunk_duration_actual

            # Cleanup immediately
            try:
                os.remove(chunk_path)
                print(f"  > Deleted chunk: {chunk_path.name}")
            except Exception as e:
                print(f"  > Warning: Failed to delete chunk {chunk_path.name}: {e}")

        # Final Cleanup
        try:
            os.rmdir(cache_dir)
        except OSError:
            pass

        # 4. Synthesis
        final_transcript = "\n".join(full_transcript)
        final_report = self._synthesize_report(metadata, full_visuals, final_transcript)

        return {
            "status": "success",
            "title": metadata.get("title", "Unknown Video"),
            "report": final_report,
            "video_path": str(video_path),
        }

    def _download_media(self, url: str):
        # Handle local files directly
        if os.path.exists(url):
            path = Path(url)
            return (
                path,
                path,
                {
                    "title": path.stem,
                    "duration": "Unknown",
                    "webpage_url": "Local File",
                },
            )

        ydl_opts = {
            "format": "best[ext=mp4]",
            "outtmpl": str(self.download_dir / "%(id)s.%(ext)s"),
            "quiet": True,
            "metrics": False,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_path = self.download_dir / f"{info['id']}.mp4"
            audio_path = video_path  # For simplicity, using same file
            return video_path, audio_path, info

    def _split_video_into_chunks(
        self, video_path: Path, output_dir: Path, chunk_duration: int
    ) -> List[Path]:
        """Split video into chunks using ffmpeg"""
        import subprocess

        output_pattern = str(output_dir / "chunk_%03d.mp4")

        # ffmpeg segments the input using stream copy for speed and fidelity.
        cmd = [
            "ffmpeg",
            "-i",
            str(video_path),
            "-c",
            "copy",
            "-map",
            "0",
            "-f",
            "segment",
            "-segment_time",
            str(chunk_duration),
            "-reset_timestamps",
            "1",
            output_pattern,
        ]

        try:
            subprocess.run(
                cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            # Return list of created files
            return sorted(list(output_dir.glob("chunk_*.mp4")))
        except Exception as e:
            print(f"[VIDEO] Split failed: {e}")
            return []

    def _analyze_chunk_visuals(self, chunk_path: Path, chunk_index: int) -> str:
        """Sample 5 frames from chunk and query VLM once"""
        cap = cv2.VideoCapture(str(chunk_path))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # Sample 5 frames evenly spread
        frames_to_encode = []
        if total_frames > 0:
            step = total_frames // 5
            for i in range(0, total_frames, step):
                if len(frames_to_encode) >= 5:
                    break
                cap.set(cv2.CAP_PROP_POS_FRAMES, i)
                ret, frame = cap.read()
                if ret:
                    frames_to_encode.append(self._encode_image(frame))
        cap.release()

        if not frames_to_encode:
            return "No visual data extracted."

        prompt = (
            "Analyze these 5 frames from a video segment "
            f"(Minute {chunk_index * 5} to {(chunk_index + 1) * 5}). "
            "Describe the key events, people, and details shown."
        )
        return self._query_vlm(frames_to_encode, prompt)

    def _analyze_visuals(self, video_path: Path) -> List[Dict]:
        """
        Analyze video visuals with parallel VLM requests.
        Strategy for Large Files (>100MB): Process frame-by-frame (<1MB payload).
        Concurrency: VLM calls are I/O bound.
        """
        frames_to_process = []
        cap = cv2.VideoCapture(str(video_path))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # Sample 1 frame every 30 seconds (adjust for density)
        interval_sec = 30
        interval_frames = int(fps * interval_sec)

        # Safety check for empty video
        if total_frames == 0 or interval_frames == 0:
            cap.release()
            return []

        for frame_idx in range(0, total_frames, interval_frames):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                break

            timestamp = frame_idx / fps
            b64_frame = self._encode_image(frame)
            frames_to_process.append((timestamp, b64_frame))

        cap.release()

        print(f"[VIDEO] Analyzing {len(frames_to_process)} frames in parallel...")

        descriptions = []
        provider_errors: List[ProviderError] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            future_to_timestamp = {
                executor.submit(
                    self._query_vlm,
                    b64,
                    "Describe the scene, people, and any text visible in this frame.",
                ): ts
                for ts, b64 in frames_to_process
            }

            for future in concurrent.futures.as_completed(future_to_timestamp):
                ts = future_to_timestamp[future]
                try:
                    desc = future.result()
                    descriptions.append({"timestamp": ts, "description": desc})
                    print(f"[VIDEO] Analyzed frame at {ts:.1f}s")
                except ProviderError as error:
                    provider_errors.append(error)
                    print(f"[VIDEO] Frame at {ts:.1f}s failed: {error.code}")

        if provider_errors:
            raise select_primary_error(provider_errors)

        # Sort by timestamp
        descriptions.sort(key=lambda x: x["timestamp"])
        return descriptions

    def _transcribe_audio(self, audio_path: Path) -> str:
        """Transcribe using OpenAI Whisper (Local)"""
        print(f"[VIDEO] Transcribing audio: {audio_path}")
        try:
            import whisper

            model = whisper.load_model(
                "base"
            )  # Use 'base' or 'small' for speed, 'medium' for accuracy
            result = model.transcribe(str(audio_path))
            return result["text"]
        except Exception as e:
            raise ProviderInvalidResponseError(
                "local_whisper",
                "Local transcription failed",
                cause_type=type(e).__name__,
            ) from e

    def _encode_image(self, frame):
        # Resize to max width 640px to speed up VLM processing
        height, width = frame.shape[:2]
        if width > 640:
            scale = 640 / width
            new_height = int(height * scale)
            frame = cv2.resize(frame, (640, new_height))

        _, buffer = cv2.imencode(".jpg", frame)
        return base64.b64encode(buffer).decode("utf-8")

    @retry_api
    def _query_vlm(self, base64_frames: Any, prompt: str) -> str:
        # Re-use existing VLM logic but suited for batch frames
        if not base64_frames:
            return "No visual data."

        # Use instance variables initialized from .env
        api_key = self.api_key
        model = self.model_name
        invoke_url = self.vlm_endpoint

        # Qwen VLM Payload Structure
        messages = [{"role": "user", "content": []}]

        if isinstance(base64_frames, str):
            normalized_frames = [{"b64": base64_frames, "timestamp": 0.0}]
        elif isinstance(base64_frames, list):
            normalized_frames = [
                (
                    frame
                    if isinstance(frame, dict)
                    else {"b64": str(frame), "timestamp": 0.0}
                )
                for frame in base64_frames
            ]
        else:
            raise ValueError("base64_frames must be a string or list")

        # Add frames
        for frame in normalized_frames:
            if not frame.get("b64"):
                raise ValueError("Each frame must contain non-empty base64 data")
            # Note: Qwen VL supports multiple images in one turn
            messages[0]["content"].append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{frame['b64']}"},
                }
            )

        # Add prompt (maybe with timestamps in text)
        timestamps = ", ".join(
            f"{float(frame.get('timestamp', 0.0)):.1f}s" for frame in normalized_frames
        )
        full_prompt = f"{prompt}\n[Timestamps: {timestamps}]"

        messages[0]["content"].append({"type": "text", "text": full_prompt})

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": int(os.getenv("VIDEO_VLM_MAX_TOKENS", "1024")),
            "temperature": float(os.getenv("VIDEO_VLM_TEMPERATURE", "0.2")),
            "top_p": float(os.getenv("VIDEO_VLM_TOP_P", "0.7")),
            "stream": False,
        }

        response = requests.post(
            invoke_url,
            headers=headers,
            json=payload,
            timeout=self.provider_policy.requests_timeout,
        )
        ensure_http_success("nvidia_vlm", response)
        try:
            response_payload = response.json()
            content = response_payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise ProviderInvalidResponseError(
                "nvidia_vlm",
                "Provider returned a malformed vision response",
                cause_type=type(error).__name__,
            ) from error
        if not isinstance(content, str) or not content.strip():
            raise ProviderInvalidResponseError(
                "nvidia_vlm",
                "Provider returned empty vision content",
            )
        return content

    def _synthesize_report(self, metadata, visuals, transcript):
        """Combine into Markdown"""
        lines = [f"# Video Analysis: {metadata.get('title')}", ""]
        lines.append(f"**URL:** {metadata.get('webpage_url')}")
        lines.append(f"**Duration:** {metadata.get('duration')}s")
        lines.append("## Visual Logic Stream")

        for item in visuals:
            timestamp = time.strftime("%H:%M:%S", time.gmtime(item["timestamp"]))
            lines.append(f"### ⏱ {timestamp}")
            lines.append(item["description"])
            lines.append("")

        lines.append("## Audio Transcript")
        lines.append(transcript)

        return "\n".join(lines)
