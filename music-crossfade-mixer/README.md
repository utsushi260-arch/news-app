# music-crossfade-mixer

複数の曲(YouTubeリンク or ローカルの音声/動画ファイル)を、BPM(テンポ)とビート位置を解析して
できるだけ切れ目が分からないようにクロスフェードで繋げ、1つのミックス音源にまとめるCLIツールです。

無料・ローカル完結で動きます(有料API・クラウドサービスは使用しません)。

- `yt-dlp` … YouTubeから音声を取得
- `ffmpeg` … 音声の変換/抽出/最終エンコード
- `librosa` … BPM・ビート位置の解析、タイムストレッチ(テンポ微調整)

## 仕組み

1. 各入力をWAVに変換(YouTubeは`yt-dlp`でダウンロード、ローカルの動画/音声ファイルは`ffmpeg`で音声抽出)
2. `librosa`でテンポ(BPM)とビート位置を解析
3. 2曲目以降は先頭の曲のテンポに近づくようタイムストレッチ(伸縮率は`--max-stretch`で上限を設定、極端な音程/速度変化を避ける)
4. 前の曲の終盤と次の曲の頭を、検出したビート位置に合わせて重ね、イコールパワー(等音量感)カーブでクロスフェード
5. 最終的なミックスを指定した形式(mp3/wavなど)で書き出し

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

`<入力>` にはYouTubeのURL、またはローカルの音声/動画ファイルのパスを、繋げたい順番で指定します。

```bash
# YouTubeリンク2つを繋げる
python3 main.py -o mix.mp3 \
  "https://www.youtube.com/watch?v=XXXXXXXXXXX" \
  "https://www.youtube.com/watch?v=YYYYYYYYYYY"

# ローカルファイルとYouTubeリンクの混在もOK
python3 main.py -o mix.mp3 song1.mp3 "https://www.youtube.com/watch?v=ZZZZZZZZZZZ" song3.mp4
```

### オプション

| オプション | 既定値 | 説明 |
|---|---|---|
| `-o, --output` | `mix.mp3` | 出力ファイル名(拡張子で形式判定) |
| `--crossfade-beats` | `16` | クロスフェードに使うビート数(長いほどゆったり切り替わる) |
| `--max-stretch` | `0.08` | テンポ合わせで許容する最大伸縮率(±8%) |
| `--speed` | `1.0` | 完成したミックス全体の再生速度倍率(ピッチは保持したまま速度だけ変える)。`2.0`で倍速 |
| `--keep-temp` | オフ | ダウンロード/変換した中間WAVファイルを削除せず残す |

```bash
# 倍速で書き出す例
python3 main.py -o mix_2x.mp3 song1.mp3 song2.mp3 --speed 2.0
```

## 注意事項

- YouTube動画のダウンロードは私的利用の範囲でお使いください。再配布や公開の場での使用はYouTubeの利用規約に注意してください。
- このリポジトリのCI/サンドボックス環境ではネットワークポリシー上YouTubeへの接続がブロックされていることがあります。ローカルファイル入力での動作は確認済みです。通常のネット接続がある手元の環境であればYouTubeリンクも問題なく取得できます。
