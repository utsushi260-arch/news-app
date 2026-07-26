#!/usr/bin/env python3
"""Music crossfade mixer CLI.

Usage:
    python3 main.py -o mix.mp3 <input1> <input2> [input3 ...]

Each <input> can be a YouTube URL or a path to a local audio/video file.
Tracks are combined in the order given, crossfaded on the beat.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

import soundfile as sf

from crossfade_mixer.beat_analysis import analyze
from crossfade_mixer.input_handler import encode_output, resolve_input
from crossfade_mixer.mixer import mix_tracks, time_stretch_stereo

MAX_SPEED = 1.5


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="複数の曲をBPM同期クロスフェードでつなげて1つのミックスにします。"
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="YouTubeのURL、または音声/動画ファイルのパス(2つ以上、繋げたい順に指定)",
    )
    parser.add_argument(
        "-o", "--output", default="mix.mp3",
        help="出力ファイル名(拡張子で形式を判定。既定: mix.mp3)",
    )
    parser.add_argument(
        "--crossfade-beats", type=int, default=16,
        help="クロスフェードに使うビート数(既定: 16)",
    )
    parser.add_argument(
        "--max-stretch", type=float, default=0.08,
        help="テンポ合わせで許容する最大伸縮率(既定: 0.08 = ±8%%)",
    )
    parser.add_argument(
        "--speed", type=float, default=1.0,
        help="完成したミックス全体の再生速度倍率(ピッチは保持)。1.0〜1.5の範囲で0.05刻み目安(例: 1.2, 1.25, 1.3)。既定: 1.0",
    )
    parser.add_argument(
        "--keep-temp", action="store_true",
        help="ダウンロード/変換した中間WAVファイルを削除せず残す",
    )
    args = parser.parse_args(argv)
    if not (0 < args.speed <= MAX_SPEED):
        parser.error(f"--speed は 0 より大きく {MAX_SPEED} 以下で指定してください")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    if len(args.inputs) < 2:
        print("曲を2つ以上指定してください。", file=sys.stderr)
        return 1

    work_dir = Path(tempfile.mkdtemp(prefix="crossfade_mixer_"))
    try:
        print(f"[1/3] 入力を解決中... (作業ディレクトリ: {work_dir})")
        wav_paths = []
        for i, spec in enumerate(args.inputs):
            print(f"  - ({i + 1}/{len(args.inputs)}) {spec}")
            wav_paths.append(resolve_input(spec, i, work_dir))

        print("[2/3] BPM/ビートを解析中...")
        analyzed = []
        for p in wav_paths:
            info = analyze(p)
            print(f"  - {p.name}: {info.tempo:.1f} BPM, {info.duration:.1f}秒")
            analyzed.append(info)

        print("[3/3] クロスフェードでミックス中...")
        mixed_y, sr = mix_tracks(
            analyzed,
            crossfade_beats=args.crossfade_beats,
            max_stretch=args.max_stretch,
        )

        if args.speed != 1.0:
            print(f"再生速度を{args.speed}倍に変換中...")
            mixed_y = time_stretch_stereo(mixed_y, args.speed)

        tmp_wav = work_dir / "_mixed_output.wav"
        sf.write(str(tmp_wav), mixed_y.T, sr)

        out_path = Path(args.output)
        if out_path.suffix.lower() == ".wav":
            shutil.copyfile(tmp_wav, out_path)
        else:
            encode_output(tmp_wav, out_path)

        print(f"完了: {out_path} ({mixed_y.shape[1] / sr:.1f}秒)")
        return 0
    finally:
        if not args.keep_temp:
            shutil.rmtree(work_dir, ignore_errors=True)
        else:
            print(f"中間ファイルを保持しました: {work_dir}")


if __name__ == "__main__":
    raise SystemExit(main())
