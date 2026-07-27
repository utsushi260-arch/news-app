#!/usr/bin/env python3
"""Music crossfade mixer CLI.

Usage:
    python3 main.py -o mix.mp3 <input1> <input2> [input3 ...]
    python3 main.py -o mix.mp3 --speeds 1.0,1.15,1.3 <input1> <input2> <input3>

Each <input> can be a YouTube/SoundCloud URL (or anything else yt-dlp
supports) or a path to a local audio/video file. The order you list them in
doesn't matter: tracks are automatically resequenced so adjacent tempos are
as close as possible, then crossfaded on the beat. Crossfade length and
tempo-matching tolerance are also chosen automatically.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from pathlib import Path

import soundfile as sf

from crossfade_mixer.beat_analysis import analyze
from crossfade_mixer.input_handler import encode_output, is_youtube_url, resolve_input
from crossfade_mixer.mixer import mix_tracks
from crossfade_mixer.ordering import order_for_smooth_mix
from crossfade_mixer.workout_fx import apply_workout_master

MAX_SPEED = 1.5


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="複数の曲をBPM同期クロスフェードでつなげて1つのミックスにします。"
    )
    parser.add_argument(
        "inputs",
        nargs="+",
        help="YouTube/SoundCloudのURL、または音声/動画ファイルのパス(2つ以上)。"
             "並べる順番は自動で決めるので、指定順は気にしなくてよい",
    )
    parser.add_argument(
        "-o", "--output", default="mix.mp3",
        help="出力ファイル名(拡張子で形式を判定。既定: mix.mp3)",
    )
    parser.add_argument(
        "--speeds", default="",
        help="各曲の再生速度倍率をカンマ区切りで指定(ピッチは保持)。inputsと同じ順番。"
             "指定しなかった曲は1.0倍。例: --speeds 1.0,1.2,1.15。範囲は0より大きく1.5以下",
    )
    parser.add_argument(
        "--workout", action="store_true",
        help="ワークアウト向けにベース/ビートを強調するマスタリングをかける",
    )
    parser.add_argument(
        "--keep-temp", action="store_true",
        help="ダウンロード/変換した中間WAVファイルを削除せず残す",
    )
    args = parser.parse_args(argv)

    speed_strs = [s.strip() for s in args.speeds.split(",") if s.strip()]
    if len(speed_strs) > len(args.inputs):
        parser.error("--speeds に指定した値の数がinputsの数より多いです")
    try:
        speeds = [float(s) for s in speed_strs]
    except ValueError:
        parser.error("--speeds は数値をカンマ区切りで指定してください")
    speeds += [1.0] * (len(args.inputs) - len(speeds))
    for s in speeds:
        if not (0 < s <= MAX_SPEED):
            parser.error(f"--speeds の各値は 0 より大きく {MAX_SPEED} 以下で指定してください")
    args.speeds = speeds
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    if len(args.inputs) < 2:
        print("曲を2つ以上指定してください。", file=sys.stderr)
        return 1

    work_dir = Path(tempfile.mkdtemp(prefix="crossfade_mixer_"))
    try:
        print(f"[1/4] 入力を解決中... (作業ディレクトリ: {work_dir})")
        wav_paths = []
        prior_youtube = False
        for i, spec in enumerate(args.inputs):
            this_youtube = is_youtube_url(spec)
            if this_youtube and prior_youtube:
                time.sleep(6)  # space out consecutive YouTube fetches to avoid tripping rate limits
            prior_youtube = this_youtube
            print(f"  - ({i + 1}/{len(args.inputs)}) {spec}")
            wav_paths.append(resolve_input(spec, i, work_dir))

        print("[2/4] BPM/ビートを解析中...")
        analyzed = []
        for p, speed in zip(wav_paths, args.speeds):
            info = analyze(p, speed=speed)
            print(f"  - {p.name}: {info.tempo:.1f} BPM, {info.duration:.1f}秒 (再生速度 {speed}倍)")
            analyzed.append(info)

        print("[3/4] テンポが近い曲同士が繋がるよう順番を決定中...")
        order = order_for_smooth_mix(analyzed)
        analyzed = [analyzed[i] for i in order]
        labels = [args.inputs[i] for i in order]
        for n, (label, info) in enumerate(zip(labels, analyzed), start=1):
            print(f"  {n}. {label} ({info.tempo:.1f} BPM)")

        print("[4/4] クロスフェードでミックス中...")
        mixed_y, sr = mix_tracks(analyzed)

        if args.workout:
            print("ワークアウト向けにマスタリング中...")
            mixed_y = apply_workout_master(mixed_y, sr)

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
