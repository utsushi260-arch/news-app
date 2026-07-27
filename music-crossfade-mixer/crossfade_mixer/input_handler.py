"""Resolve a YouTube/SoundCloud URL or local media file into a local WAV file."""
from __future__ import annotations

import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "music.youtube.com"}


def is_url(spec: str) -> bool:
    return bool(_URL_RE.match(spec.strip()))


def is_youtube_url(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return host.lower() in _YOUTUBE_HOSTS


def resolve_input(spec: str, index: int, work_dir: Path) -> Path:
    """Resolve a URL (YouTube, SoundCloud, or anything else yt-dlp supports) or a local file path to a WAV file inside work_dir."""
    work_dir.mkdir(parents=True, exist_ok=True)
    out_path = work_dir / f"track_{index:02d}.wav"

    if is_url(spec):
        if is_youtube_url(spec):
            _download_youtube_audio(spec, out_path)
        else:
            _download_generic_audio(spec, out_path)
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

# Some clients reject cookies outright, so don't attach them there even when
# a cookies file is configured.
_CLIENTS_WITHOUT_COOKIE_SUPPORT = {"ios"}

# If a cookies.txt (Netscape format, exported from a logged-in browser) is
# mounted here, yt-dlp uses it to authenticate as that account instead of
# an anonymous request - this is what actually fixes bot/rate-limit blocks
# on shared hosting IPs. Render mounts "Secret Files" under /etc/secrets/,
# which is read-only, so it's copied to a writable path before use (yt-dlp
# rewrites the cookie jar back to disk after every run).
_COOKIES_SECRET_PATH = Path("/etc/secrets/cookies.txt")
_COOKIES_WRITABLE_PATH = Path("/tmp/yt_cookies.txt")


# Once YouTube 429s this server's IP, immediately retrying (or letting the
# next user's request try) only extends the block. Remember it for a while
# and fail fast instead of hammering YouTube again during the cooldown.
_RATE_LIMIT_COOLDOWN_SECONDS = 15 * 60
_last_rate_limited_at = 0.0

# yt-dlp can occasionally hang indefinitely on a stalled connection instead of
# erroring out. Without a timeout, that leaves the web UI's progress bar
# stuck with no feedback. Fail with a clear message after this long instead.
_DOWNLOAD_TIMEOUT_SECONDS = 300

# Tracks now download concurrently (see app.py's ThreadPoolExecutor), but
# YouTube fetches still need to be spaced out to avoid tripping rate limits.
# That spacing is enforced here - across whichever threads call in - rather
# than by the caller looping sequentially, so non-YouTube downloads (e.g.
# SoundCloud) aren't held up waiting behind it.
_YOUTUBE_FETCH_SPACING_SECONDS = 6
_youtube_fetch_lock = threading.Lock()
_last_youtube_fetch_at = 0.0


def _raise_if_cooling_down() -> None:
    remaining = _RATE_LIMIT_COOLDOWN_SECONDS - (time.time() - _last_rate_limited_at)
    if remaining > 0:
        minutes = int(remaining // 60) + 1
        raise RuntimeError(
            "直近でYouTube側のレート制限(429)が発生したため、悪化を避けるためこのサーバーは"
            f"あと約{minutes}分ほどYouTubeへのアクセスを控えます。"
            "少し待つか、ローカルファイルとしてアップロードしてください。"
        )


def _mark_rate_limited() -> None:
    global _last_rate_limited_at
    _last_rate_limited_at = time.time()


def _cookies_path() -> str | None:
    if not _COOKIES_SECRET_PATH.is_file():
        return None
    if (
        not _COOKIES_WRITABLE_PATH.is_file()
        or _COOKIES_SECRET_PATH.stat().st_mtime > _COOKIES_WRITABLE_PATH.stat().st_mtime
    ):
        shutil.copyfile(_COOKIES_SECRET_PATH, _COOKIES_WRITABLE_PATH)
    return str(_COOKIES_WRITABLE_PATH)


def _download_youtube_audio(url: str, out_path: Path) -> None:
    _raise_if_cooling_down()

    global _last_youtube_fetch_at
    with _youtube_fetch_lock:
        wait = _YOUTUBE_FETCH_SPACING_SECONDS - (time.time() - _last_youtube_fetch_at)
        if wait > 0:
            time.sleep(wait)
        _last_youtube_fetch_at = time.time()
        _download_youtube_audio_locked(url, out_path)


def _download_youtube_audio_locked(url: str, out_path: Path) -> None:
    out_tmpl = str(out_path.with_suffix(""))
    cookies = _cookies_path()

    # Always work through the full client fallback chain - even if the
    # cookies file is present but stale/rejected, later attempts (a
    # different client, or no cookies at all) may still succeed.
    last_error = ""
    for player_client in _PLAYER_CLIENT_FALLBACKS:
        cmd = [
            "yt-dlp",
            *_YT_DLP_BASE_ARGS,
            "-o", f"{out_tmpl}.%(ext)s",
        ]
        if cookies and player_client not in _CLIENTS_WITHOUT_COOKIE_SUPPORT:
            cmd += ["--cookies", cookies]
        if player_client:
            cmd += ["--extractor-args", f"youtube:player_client={player_client}"]
        cmd.append(url)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=_DOWNLOAD_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            last_error = f"{_DOWNLOAD_TIMEOUT_SECONDS}秒待っても応答がありませんでした(タイムアウト)"
            continue
        if result.returncode == 0 and out_path.exists():
            return
        last_error = result.stderr[-2000:]

        # A 429 means "back off", not "try a different client" - hammering it
        # with more attempts right away only makes the rate limit worse.
        if "429" in last_error or "Too Many Requests" in last_error:
            _mark_rate_limited()
            break

    hint = ""
    if "no longer valid" in last_error or "have likely been rotated" in last_error:
        hint = (
            "\n(登録したCookieが失効しています。ブラウザから新しくcookies.txtを"
            "書き出し直して、Renderの Secret Files のcookies.txtを差し替えてください)"
        )
    elif "429" in last_error or "Too Many Requests" in last_error:
        hint = (
            "\n(YouTube側のレート制限です。このサーバーのIPからのアクセスが集中した可能性があります。"
            "少し時間を置いてから再度試すか、ローカルファイルとしてアップロードしてください)"
        )
    elif "Sign in to confirm" in last_error or "bot" in last_error.lower():
        hint = (
            "\n(YouTube側がこのサーバーからのアクセスをbot判定してブロックしています。"
            "同じ動画をローカルファイルとしてアップロードする方法もお試しください)"
        )
    raise RuntimeError(f"YouTube音声のダウンロード({url})に失敗しました:\n{last_error}{hint}")


def _download_generic_audio(url: str, out_path: Path) -> None:
    """Download from any yt-dlp-supported site other than YouTube (e.g. SoundCloud).

    These sites generally don't need YouTube's bot-check/rate-limit workarounds,
    so this is just a plain yt-dlp call.
    """
    out_tmpl = str(out_path.with_suffix(""))
    cmd = ["yt-dlp", *_YT_DLP_BASE_ARGS, "-o", f"{out_tmpl}.%(ext)s", url]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=_DOWNLOAD_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"音声のダウンロード({url})が{_DOWNLOAD_TIMEOUT_SECONDS}秒待っても終わらなかったため中断しました。"
            "ネットワークが不安定か、サイト側の応答が遅い可能性があります。"
        )
    if result.returncode != 0 or not out_path.exists():
        raise RuntimeError(f"音声のダウンロード({url})に失敗しました:\n{result.stderr[-2000:]}")


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
