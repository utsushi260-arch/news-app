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


_YT_DLP_BASE_ARGS = ["-x", "--audio-format", "wav", "--audio-quality", "0"]

# YouTube sometimes blocks the default "web" client from datacenter IPs with a
# "Sign in to confirm you're not a bot" error. Retrying with alternate player
# clients (as the official mobile apps use) frequently avoids that check
# without needing cookies. Not guaranteed to always work since YouTube keeps
# changing this.
_PLAYER_CLIENT_FALLBACKS = [None, "android", "ios"]


def _download_youtube_audio(url: str, out_path: Path) -> None:
    out_tmpl = str(out_path.with_suffix(""))
    last_error = ""
    for player_client in _PLAYER_CLIENT_FALLBACKS:
        cmd = [
            "yt-dlp",
            *_YT_DLP_BASE_ARGS,
            "-o", f"{out_tmpl}.%(ext)s",
        ]
        if player_client:
            cmd += ["--extractor-args", f"youtube:player_client={player_client}"]
        cmd.append(url)

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 and out_path.exists():
            return
        last_error = result.stderr[-2000:]

    hint = ""
    if "Sign in to confirm" in last_error or "bot" in last_error.lower():
        hint = (
            "\n(YouTube側がこのサーバーからのアクセスをbot判定してブロックしています。"
            "同じ動画をローカルファイルとしてアップロードする方法もお試しください)"
        )
    raise RuntimeError(f"YouTube音声のダウンロード({url})に失敗しました:\n{last_error}{hint}")


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
