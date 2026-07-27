---
title: Music Crossfade Mixer
emoji: 🎧
colorFrom: blue
colorTo: purple
sdk: gradio
sdk_version: 6.20.0
app_file: app.py
pinned: false
---

# music-crossfade-mixer

複数の曲(YouTube/SoundCloudリンク or ローカルの音声/動画ファイル)を、BPM(テンポ)とビート位置を解析して
できるだけ切れ目が分からないようにクロスフェードで繋げ、1つのミックス音源にまとめるCLIツールです。

無料・ローカル完結で動きます(有料API・クラウドサービスは使用しません)。

- `yt-dlp` … YouTube/SoundCloudなどから音声を取得
- `ffmpeg` … 音声の変換/抽出/最終エンコード
- `librosa` … BPM・ビート位置の解析、タイムストレッチ(テンポ微調整)

## 仕組み

1. 各入力をWAVに変換(YouTube/SoundCloudは`yt-dlp`でダウンロード、ローカルの動画/音声ファイルは`ffmpeg`で音声抽出)
2. 指定があれば、曲ごとにタイムストレッチ(ピッチを保ったまま再生速度を変更)
3. `librosa`でテンポ(BPM)とビート位置を解析
4. **入力した順番は使わず**、テンポが近い曲同士(倍テンポ・半分テンポの関係も考慮)が隣り合うように
   曲順を自動で組み直す(曲数が少なければ全パターン試行、多い場合は近い曲から繋いでいく方式)
5. 隣り合う曲は、前の曲のテンポに近づくようタイムストレッチ(伸縮率の上限は内部で自動設定、極端な音程/速度変化を避ける)
6. 前の曲の終盤と次の曲の頭を、検出したビート位置に合わせて重ね、イコールパワー(等音量感)カーブでクロスフェード
7. `--workout` / Web版のチェックボックスを付けた場合、ベースを持ち上げてコンプレッサーをかけ、ビートを強めに聴かせるマスタリングを追加
8. 最終的なミックスを指定した形式(mp3/wavなど)で書き出し

クロスフェードの長さやテンポ合わせの許容範囲は、曲ごとに調整しても良い結果にならないことが多いため、
自動で決めた値を内部で使っています(ユーザーが設定する項目はありません)。

BPM解析・ビート検出は完璧ではないため、テンポや曲調が大きく異なる曲同士では自然さに限界があります。
ロック/EDM/ポップスなど拍がはっきりした曲同士だと特に効果を発揮します。

## セットアップ

```bash
# システム側
sudo apt-get install -y ffmpeg   # 未インストールの場合

# Python側
pip install -r requirements.txt
```

## 使い方

```bash
python3 main.py -o mix.mp3 <入力1> <入力2> [<入力3> ...]
```

`<入力>` にはYouTube/SoundCloudのURL、またはローカルの音声/動画ファイルのパスを指定します。
繋げる順番はテンポが近い曲同士になるよう自動で決まるので、指定する順番は気にしなくて大丈夫です。

```bash
# YouTubeリンク2つを繋げる
python3 main.py -o mix.mp3 \
  "https://www.youtube.com/watch?v=XXXXXXXXXXX" \
  "https://www.youtube.com/watch?v=YYYYYYYYYYY"

# ローカルファイル・YouTube・SoundCloudの混在もOK
python3 main.py -o mix.mp3 song1.mp3 "https://www.youtube.com/watch?v=ZZZZZZZZZZZ" "https://soundcloud.com/artist/track" song3.mp4
```

### オプション

| オプション | 既定値 | 説明 |
|---|---|---|
| `-o, --output` | `mix.mp3` | 出力ファイル名(拡張子で形式判定) |
| `--speeds` | 全曲1.0倍 | 曲ごとの再生速度倍率をカンマ区切りで指定(ピッチは保持)。`inputs`に書いた順番に対応(繋がる順ではない)。指定しなかった曲は1.0倍。範囲は0より大きく1.5以下 |
| `--workout` | オフ | ワークアウト向けにベース/ビートを強調するマスタリングをかける |
| `--keep-temp` | オフ | ダウンロード/変換した中間WAVファイルを削除せず残す |

```bash
# 1曲目はそのまま、2曲目は1.15倍、3曲目は1.3倍速にして、ワークアウト向けに強調する例
python3 main.py -o workout_mix.mp3 song1.mp3 song2.mp3 song3.mp3 --speeds 1.0,1.15,1.3 --workout
```

## Webアプリ版(Hugging Face Spaces)

CLIとは別に、ブラウザ(スマホのSafariなど)から使えるGradio製のWebアプリ(`app.py`)も同梱しています。
YouTube/SoundCloudリンクの入力欄とローカルファイルのアップロード欄があり、テンポが近い曲同士が繋がるよう
自動で順番を決めてクロスフェードでミックスします(決定した曲順は結果と一緒に表示されます)。
曲ごとの再生速度指定と、ワークアウト向けマスタリングのチェックボックスも付いています。

ローカルで試す場合:

```bash
pip install -r requirements.txt
python3 app.py
```

Hugging Face Spacesにデプロイする場合は、このフォルダ(`music-crossfade-mixer/`)の中身をそのまま
Spaceのリポジトリにpushするだけで動きます(`README.md`先頭のYAMLがSpaceの設定、`app.py`がエントリーポイント、
`packages.txt`でffmpegを、`requirements.txt`でPython依存関係をインストールします)。
デプロイ後のSpace URLをiPhoneのSafariで開き、共有ボタンから「ホーム画面に追加」するとアプリのように使えます。

## 注意事項

- YouTube動画のダウンロードは私的利用の範囲でお使いください。再配布や公開の場での使用はYouTubeの利用規約に注意してください。
- このリポジトリのCI/サンドボックス環境ではネットワークポリシー上YouTubeへの接続がブロックされていることがあります。ローカルファイル入力での動作は確認済みです。通常のネット接続がある手元の環境であればYouTubeリンクも問題なく取得できます。
