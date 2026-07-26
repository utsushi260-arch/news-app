"""Gradio web app for the music crossfade mixer (deployable to Hugging Face Spaces / Render / etc)."""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import gradio as gr
import soundfile as sf

from crossfade_mixer.beat_analysis import analyze
from crossfade_mixer.input_handler import encode_output, is_youtube_url, resolve_input
from crossfade_mixer.mixer import mix_tracks
from crossfade_mixer.ordering import order_for_smooth_mix
from crossfade_mixer.workout_fx import apply_workout_master

MAX_SPEED = 1.5

PWA_HEAD = """
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Crossfade Mixer">
"""


def _parse_speeds(speeds_text: str, count: int) -> list[float]:
    raw = [s.strip() for s in (speeds_text or "").replace("\n", ",").split(",") if s.strip()]
    if len(raw) > count:
        raise gr.Error(f"曲ごとの再生速度の指定が多すぎます(曲は{count}個です)")
    try:
        speeds = [float(s) for s in raw]
    except ValueError:
        raise gr.Error("曲ごとの再生速度はカンマ区切りの数値で指定してください(例: 1.0, 1.2, 1.15)")
    speeds += [1.0] * (count - len(speeds))
    for s in speeds:
        if not (0 < s <= MAX_SPEED):
            raise gr.Error(f"曲ごとの再生速度は0より大きく{MAX_SPEED}以下で指定してください")
    return speeds


def run_mix(youtube_urls_text, uploaded_files, speeds_text, workout_mode, progress=gr.Progress()):
    urls = [line.strip() for line in (youtube_urls_text or "").splitlines() if line.strip()]
    file_paths = [f.name if hasattr(f, "name") else f for f in (uploaded_files or [])]
    file_labels = [
        getattr(f, "orig_name", None) or Path(path).name
        for f, path in zip(uploaded_files or [], file_paths)
    ]
    specs = urls + file_paths
    labels = urls + file_labels

    if len(specs) < 2:
        raise gr.Error("リンクとファイルを合わせて2つ以上指定してください。")

    speeds = _parse_speeds(speeds_text, len(specs))

    work_dir = Path(tempfile.mkdtemp(prefix="crossfade_web_"))

    progress(0.0, desc="入力を解決中...")
    wav_paths = []
    prior_youtube = False
    for i, spec in enumerate(specs):
        this_youtube = is_youtube_url(spec)
        if this_youtube and prior_youtube:
            time.sleep(6)  # space out consecutive YouTube fetches to avoid tripping rate limits
        prior_youtube = this_youtube
        try:
            wav_paths.append(resolve_input(spec, i, work_dir))
        except Exception as e:
            raise gr.Error(f"「{labels[i]}」の取得に失敗しました: {e}")
        progress(0.05 + 0.3 * (i + 1) / len(specs), desc=f"入力を解決中... ({i + 1}/{len(specs)})")

    analyzed = []
    for i, (p, speed) in enumerate(zip(wav_paths, speeds)):
        analyzed.append(analyze(p, speed=speed))
        progress(0.35 + 0.25 * (i + 1) / len(wav_paths), desc=f"BPM/ビートを解析中... ({i + 1}/{len(wav_paths)})")

    progress(0.62, desc="テンポが近い曲同士が繋がるよう順番を決定中...")
    order = order_for_smooth_mix(analyzed)
    analyzed = [analyzed[i] for i in order]
    labels = [labels[i] for i in order]
    order_lines = [f"{n}. {label} ({info.tempo:.1f} BPM)" for n, (label, info) in enumerate(zip(labels, analyzed), start=1)]
    order_summary = "決定した曲順:\n" + "\n".join(order_lines)

    progress(0.7, desc="クロスフェードでミックス中...")
    mixed_y, sr = mix_tracks(analyzed)

    if workout_mode:
        progress(0.9, desc="ワークアウト向けにマスタリング中...")
        mixed_y = apply_workout_master(mixed_y, sr)

    tmp_wav = work_dir / "_mixed_output.wav"
    sf.write(str(tmp_wav), mixed_y.T, sr)

    out_path = work_dir / "mix.mp3"
    encode_output(tmp_wav, out_path)

    progress(1.0, desc="完了")
    return str(out_path), order_summary


with gr.Blocks(title="Music Crossfade Mixer") as demo:
    gr.Markdown(
        "# 🎧 Music Crossfade Mixer\n"
        "複数の曲(YouTube/SoundCloudリンク or ローカルファイル)をBPM同期クロスフェードで1本のミックスにします。\n\n"
        "曲を繋げる順番はテンポ(BPM)が近い曲同士が隣り合うように自動で決めるので、"
        "入力欄に並べる順番は気にしなくて大丈夫です。"
    )
    with gr.Row():
        with gr.Column():
            urls = gr.Textbox(
                lines=6,
                label="YouTube / SoundCloud のリンク(1行に1つ)",
                placeholder="https://www.youtube.com/watch?v=...\nhttps://soundcloud.com/...",
            )
            files = gr.File(
                label="ローカルの音声/動画ファイル(複数選択可)",
                file_count="multiple",
            )
            speeds_text = gr.Textbox(
                label=f"曲ごとの再生速度(カンマ区切り。順番はリンク→アップロードファイルの順(繋げる順ではなく入力欄の順)。"
                      f"省略した曲は1.0倍。範囲は0より大きく{MAX_SPEED}以下)",
                placeholder="1.0, 1.2, 1.15",
            )
            workout_mode = gr.Checkbox(
                label="🏋️ ワークアウト向けに強調する(ベース/ビートを大きめに)",
                value=True,
            )
            run_btn = gr.Button("ミックスする", variant="primary")
        with gr.Column():
            output_audio = gr.Audio(label="結果", type="filepath")
            order_output = gr.Textbox(label="決定した曲順", lines=6, interactive=False)

    run_btn.click(
        fn=run_mix,
        inputs=[urls, files, speeds_text, workout_mode],
        outputs=[output_audio, order_output],
    )

demo.queue()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    demo.launch(server_name="0.0.0.0", server_port=port, head=PWA_HEAD)
