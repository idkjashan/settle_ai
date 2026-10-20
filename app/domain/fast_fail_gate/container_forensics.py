import json
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from app.core.config import settings
from app.domain.fast_fail_gate.schemas import ContainerGateReport, FastFailFailureCode
from app.core.logging import logger

class ContainerForensicsValidator:
    def __init__(self, ffprobe_bin: str = "ffprobe"):
        self.ffprobe_bin = ffprobe_bin
        self.settings = settings

    def validate(self, video_path: Path, sha256: str, file_size_bytes: int) -> ContainerGateReport:
        t0 = time.perf_counter()
        failure_codes: List[FastFailFailureCode] = []

        if not video_path.exists():
            return ContainerGateReport(
                passed=False,
                failure_codes=[FastFailFailureCode.CONTAINER_PARSE_FAILED],
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )

        cmd = [
            self.ffprobe_bin,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(video_path),
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode != 0 or not result.stdout.strip():
                return ContainerGateReport(
                    passed=False,
                    failure_codes=[FastFailFailureCode.CONTAINER_PARSE_FAILED],
                    duration_ms=(time.perf_counter() - t0) * 1000.0,
                )
            probe_data = json.loads(result.stdout)
        except Exception as e:
            logger.error(f"ffprobe execution failed on {video_path}: {e}")
            return ContainerGateReport(
                passed=False,
                failure_codes=[FastFailFailureCode.CONTAINER_PARSE_FAILED],
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )

        format_data = probe_data.get("format", {})
        streams = probe_data.get("streams", [])

        # 1. Identify video stream
        video_stream: Optional[Dict[str, Any]] = None
        for s in streams:
            if s.get("codec_type") == "video":
                video_stream = s
                break

        if not video_stream:
            failure_codes.append(FastFailFailureCode.NO_VIDEO_STREAM)
            return ContainerGateReport(
                passed=False,
                failure_codes=failure_codes,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            )

        # 2. Dimensions & Orientation
        # ponytail: guard against non-numeric dimensions like "N/A"
        try:
            width = int(video_stream.get("width") or 0)
            height = int(video_stream.get("height") or 0)
            if width <= 0 or height <= 0:
                failure_codes.append(FastFailFailureCode.CONTAINER_PARSE_FAILED)
        except (ValueError, TypeError):
            width, height = 0, 0
            failure_codes.append(FastFailFailureCode.CONTAINER_PARSE_FAILED)
        
        # Check rotation metadata if smartphone vertical video
        side_data = video_stream.get("side_data_list", []) or []
        rotation = 0
        for sd in side_data:
            if isinstance(sd, dict) and "rotation" in sd:
                try:
                    rotation = abs(int(sd["rotation"]))
                except (ValueError, TypeError):
                    pass
        tags = video_stream.get("tags") or {}
        if "rotate" in tags:
            try:
                rotation = abs(int(tags["rotate"]))
            except (ValueError, TypeError):
                pass

        if rotation in (90, 270):
            width, height = height, width

        # Orientation-agnostic 720p gate: longer edge >= 720 and shorter edge >= 480
        if max(width, height) < self.settings.MIN_RESOLUTION_WIDTH or min(width, height) < 480:
            failure_codes.append(FastFailFailureCode.RESOLUTION_TOO_LOW)

        # 3. Duration Gate
        duration_sec, duration_src = self._parse_duration(format_data, video_stream)
        if duration_sec < self.settings.MIN_DURATION_SECONDS:
            failure_codes.append(FastFailFailureCode.DURATION_TOO_SHORT)
        elif duration_sec > self.settings.MAX_DURATION_SECONDS:
            failure_codes.append(FastFailFailureCode.DURATION_TOO_LONG)

        # 4. Framerate Gate
        effective_fps = self._parse_fps(video_stream)
        if effective_fps < self.settings.MIN_FRAMERATE_FPS:
            failure_codes.append(FastFailFailureCode.FRAMERATE_TOO_LOW)

        # 5. Non-linear Editor Tag Blacklist
        detected_editor_tag = self._check_editor_tags(format_data.get("tags") or {}, video_stream.get("tags") or {})
        if detected_editor_tag:
            failure_codes.append(FastFailFailureCode.METADATA_EDITED_VIDEO)

        duration_ms = (time.perf_counter() - t0) * 1000.0
        passed = len(failure_codes) == 0

        logger.info(
            f"Container Forensics on {video_path.name}: passed={passed}, res={width}x{height}, "
            f"dur={duration_sec:.2f}s, fps={effective_fps:.1f}, editor={detected_editor_tag} ({duration_ms:.2f}ms)"
        )

        return ContainerGateReport(
            passed=passed,
            failure_codes=failure_codes,
            format_name=format_data.get("format_name", ""),
            width=width,
            height=height,
            duration_sec=duration_sec,
            effective_fps=effective_fps,
            codec_name=video_stream.get("codec_name", ""),
            detected_editor_tag=detected_editor_tag,
            duration_source=duration_src,
            duration_ms=duration_ms,
        )

    def _parse_duration(self, format_data: dict, stream_data: dict) -> Tuple[float, str]:
        # Try format duration first
        if "duration" in format_data:
            try:
                return float(format_data["duration"]), "format"
            except (ValueError, TypeError):
                pass
        # Fall back to stream duration
        if "duration" in stream_data:
            try:
                return float(stream_data["duration"]), "stream"
            except (ValueError, TypeError):
                pass
        return 0.0, "unknown"

    def _parse_fps(self, stream_data: dict) -> float:
        for key in ("avg_frame_rate", "r_frame_rate"):
            val = stream_data.get(key)
            if val and "/" in val:
                num, den = val.split("/", 1)
                try:
                    num_f, den_f = float(num), float(den)
                    if den_f > 0:
                        fps = num_f / den_f
                        if 1.0 <= fps <= 240.0:
                            return fps
                except (ValueError, ZeroDivisionError):
                    pass
        return 0.0

    def _check_editor_tags(self, format_tags: Optional[dict], stream_tags: Optional[dict]) -> Optional[str]:
        all_tags = {}
        # ponytail: guard against null tag dicts
        if format_tags:
            all_tags.update(format_tags)
        if stream_tags:
            all_tags.update(stream_tags)

        blacklist = [b.lower() for b in self.settings.EDITOR_TAG_BLACKLIST]
        whitelist = [w.lower() for w in self.settings.EDITOR_TAG_WHITELIST]

        for k, v in all_tags.items():
            if not isinstance(v, str):
                continue
            v_lower = v.lower()
            for b_tag in blacklist:
                if b_tag in v_lower:
                    # Check if it is a whitelisted string (e.g. lavf or libx264)
                    is_whitelisted = False
                    for w_tag in whitelist:
                        if w_tag in v_lower and b_tag not in ("capcut", "inshot", "premiere", "davinci", "filmora", "kinemaster", "ffmpeg-splice"):
                            is_whitelisted = True
                            break
                    if not is_whitelisted:
                        return f"{k}:{v}"
        return None

container_forensics_validator = ContainerForensicsValidator()

