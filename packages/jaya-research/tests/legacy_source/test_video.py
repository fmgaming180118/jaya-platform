"""Manual batch smoke test for the video research pipeline."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

import pytest
from dotenv import load_dotenv

pytestmark = [pytest.mark.hardware, pytest.mark.manual, pytest.mark.network]
pytest.importorskip(
    "cv2",
    reason="manual video smoke requires the optional OpenCV runtime",
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from jaya_research.provider_errors import ProviderError  # noqa: E402
from jaya_research.research.video_processor import VideoProcessor  # noqa: E402
from jaya_research.synthesize_knowledge import generate_knowledge_synthesis  # noqa: E402


def test_batch_process() -> None:
    """Process configured local videos and synthesize only successful reports."""
    input_dir_env = os.getenv("VIDEO_INPUT_DIR")
    input_dir = (
        Path(input_dir_env)
        if input_dir_env
        else PROJECT_ROOT / "file-uji-coba"
    )
    if not input_dir.exists():
        pytest.skip(f"manual video input directory is unavailable: {input_dir}")

    processor = VideoProcessor()
    all_videos = list(input_dir.glob("*.mp4"))
    video_files = [
        video for video in all_videos if "10-23-26" in video.name
    ] or all_videos
    print(f"Found {len(video_files)} videos to process")

    results_dir = PROJECT_ROOT / "reports" / "video_analysis"
    results_dir.mkdir(parents=True, exist_ok=True)
    report_sections: list[str] = []

    for index, video_file in enumerate(video_files, start=1):
        print(f"\n[{index}/{len(video_files)}] Processing: {video_file.name}...")
        try:
            result = processor.process_video_chunked(str(video_file))
            report = result["report"]
            report_path = results_dir / f"{video_file.stem}_report.md"
            report_path.write_text(report, encoding="utf-8")
            report_sections.append(
                f"\n\n=== SOURCE VIDEO: {video_file.name} ===\n{report}"
            )
            print(f"Report saved: {report_path.name}")
        except ProviderError as error:
            print(
                f"Provider failed for {video_file.name}: "
                f"{error.code} ({error.provider})"
            )
        except Exception as error:
            print(
                f"Failed to process {video_file.name}: "
                f"{type(error).__name__}"
            )
            traceback.print_exc()

    if not report_sections:
        return

    try:
        knowledge = generate_knowledge_synthesis("".join(report_sections))
    except ProviderError as error:
        print(f"Synthesis failed: {error.code} ({error.provider})")
        return

    knowledge_path = results_dir / "CONSOLIDATED_KNOWLEDGE.md"
    knowledge_path.write_text(knowledge, encoding="utf-8")
    print(f"Knowledge synthesis complete: {knowledge_path}")


if __name__ == "__main__":
    test_batch_process()
