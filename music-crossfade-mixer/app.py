"""Gradio web app for the music crossfade mixer (deployable to Hugging Face Spaces)."""
from __future__ import annotations

import tempfile
from pathlib import Path

import gradio as gr
import soundfile as sf

from crossfade_mixer.beat_analysis import analyze
from crossfade_mixer.input_handler import encode_output, resolve_input
from crossfade_mixer.mixer import mix_tracks, time_stretch_stereo

MAX_SPEED = 1.5

PWA_HEAD = """
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Crossfade Mixer">
"""


def run_mix(youtube_urls_text, uploaded_files, crossfade_beats, max_stretch, speed, progress=gr.Progress()):
    if not (0 < speed <= MAX_SPEED):
        raise gr.Error(f"再生速度は0より大きく{MAX_SPEED}以下で指定してください")

    urls = [line.strip() for line in (youtube_urls_text or "").splitlines() if line.strip()]
    file_paths = [f.name if hasattr(f, "name") else f for f in (uploaded_files or [])]
    specs = urls + file_paths

    if len(specs) < 2:
        raise gr.Error("YouTubeリンクとファイルを合わせて2つ以上指定してください。")

    work_dir = Path(tempfile.mkdtemp(prefix="crossfade_web_"))

    progress(0.0, desc="入力を解決中...")
    wav_paths = []
    for i, spec in enumerate(specs):
        wav_paths.append(resolve_input(spec, i, work_dir))
        progress(0.05 + 0.3 * (i + 1) / len(specs), desc=f"入力を解決中... ({i + 1}/{len(specs)})")

    analyzed = []
    for i, p in enumerate(wav_paths):
        analyzed.append(analyze(p))
        progress(0.35 + 0.3 * (i + 1) / len(wav_paths), desc=f"BPM/ビートを解析中... ({i + 1}/{len(wav_paths)})")

    progress(0.7, desc="クロスフェードでミックス中...")
    mixed_y, sr = mix_tracks(analyzed, crossfade_beats=int(crossfade_beats), max_stretch=max_stretch)

    if speed != 1.0:
        progress(0.9, desc=f"再生速度を{speed}倍に変換中...")
        mixed_y = time_stretch_stereo(mixed_y, speed)

    tmp_wav = work_dir / "_mixed_output.wav"
    sf.write(str(tmp_wav), mixed_y.T, sr)

    out_path = work_dir / "mix.mp3"
    encode_output(tmp_wav, out_path)

    progress(1.0, desc="完了")
    return str(out_path)


with gr.Blocks(title="Music Crossfade Mixer") as demo:
    gr.Markdown(
        "# 🎧 Music Crossfade Mixer\n"
        "複数の曲(YouTubeリンク or ローカルファイル)をBPM同期クロスフェードで1本のミックスにします。\n\n"
        "YouTubeリンクとアップロードファイルは、この画面に並んでいる順番で繋がります。"
    )
    with gr.Row():
        with gr.Column():
            urls = gr.Textbox(
                lines=6,
                label="YouTubeリンク(1行に1つ、繋げたい順)",
                placeholder="https://www.youtube.com/watch?v=...\nhttps://www.youtube.com/watch?v=...",
            )
            files = gr.File(
                label="ローカルの音声/動画ファイル(複数選択可。上のリンクの後ろに追加されます)",
                file_count="multiple",
            )
            crossfade_beats = gr.Slider(4, 32, value=16, step=1, label="クロスフェードのビート数")
            max_stretch = gr.Slider(0.0, 0.2, value=0.08, step=0.01, label="テンポ合わせの最大伸縮率")
            speed = gr.Slider(1.0, MAX_SPEED, value=1.0, step=0.05, label="再生速度(倍速)")
            run_btn = gr.Button("ミックスする", variant="primary")
        with gr.Column():
            output_audio = gr.Audio(label="結果", type="filepath")

    run_btn.click(
        fn=run_mix,
        inputs=[urls, files, crossfade_beats, max_stretch, speed],
        outputs=output_audio,
    )

demo.queue()

if __name__ == "__main__":
    demo.launch(head=PWA_HEAD)
