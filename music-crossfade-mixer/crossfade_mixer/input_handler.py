"""Resolve a YouTube URL or local media file into a local WAV file."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


def is_url(spec: str) -> bool:
    return bool(_URL_RE.match(spec.strip()))


def resolve_input(spec: str, index: int, work_dir: Path) -> Path:
    """Resolve a YouTube URL or local file path to a WAV file inside work_dir."""
    work_dir.mkdir(parents=True, exist_ok=True)
    out_path = work_dir / f"track_{index:02d}.wav"

    if is_url(spec):
        _download_youtube_audio(spec, out_path)
    else:
        src = Path(spec).expanduser()
        if not src.is_file():
            raise FileNotFoundError(f"入力ファイルが見つかりません: {spec}")
        _extract_audio(src, out_path)

    return out_path


def encode_output(wav_path: Path, out_path: Path) -> None:
    """Encode a WAV file to the format implied by out_path's suffix (e.g. .mp3)."""
    cmd = ["ffmpeg", "-y", "-i", str(wav_path), "-loglevel", "error", str(out_path)]
    _run(cmd, "出力ファイルのエンコード")


def _download_youtube_audio(url: str, out_path: Path) -> None:
    out_tmpl = str(out_path.with_suffix(""))
    cmd = [
        "yt-dlp",
        "-x",
        "--audio-format", "wav",
        "--audio-quality", "0",
        "-o", f"{out_tmpl}.%(ext)s",
        url,
    ]
    _run(cmd, f"YouTube音声のダウンロード ({url})")
    if not out_path.exists():
        raise RuntimeError(f"ダウンロードした音声が見つかりません: {out_path}")


def _extract_audio(src: Path, out_path: Path) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-i", str(src),
        "-vn",
        "-ac", "2",
        "-ar", "44100",
        "-loglevel", "error",
        str(out_path),
    ]
    _run(cmd, f"音声の抽出/変換 ({src.name})")


def _run(cmd: list[str], step: str) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"{step}に失敗しました:\n{result.stderr[-2000:]}")
