#!/bin/sh
# 検査を1本にまとめる。**手で unittest を打たないための入口。**
#
#     sh scripts/check.sh
#
# やっているのは2つだけ。
#
#   1. **__pycache__ を消す**
#   2. 終了コードで見る（**後ろにパイプを置かない**）
#
# ## なぜ消すのか。-B では足りない
#
# `python3 -B` は「**新しく .pyc を書かない**」だけで、
# **もうある .pyc は読む。** `PYTHONDONTWRITEBYTECODE=1` も同じ。
# 実測（2026-09-19）:
#
#     書き換えた直後   python3 r.py                 → 古い
#                      python3 -B r.py              → 古い
#                      PYTHONDONTWRITEBYTECODE=1    → 古い
#                      __pycache__ を消す           → 新しい
#
# キャッシュが使われるのは、元ファイルの **mtime とサイズの両方**が
# 一致したとき。mtime は秒単位なので、「**同じ秒のうちに、同じバイト数で**
# 書き換える」と両方一致する。漢字2文字を漢字2文字に替えるとそうなる
# （落札 → 売却）。**編集して即実行、が一番踏む。急いだ日だけ踏む。**
#
# いちばん危ないのは、**壊して鳴らす手順が嘘をつく**こと。
# 壊したのに鳴らない・直したのに鳴り続ける、のどちらも起きる。
# 「-B にしたから大丈夫」と思ったまま続けるのが、いちばん危ない。
#
# ## なぜ後ろにパイプを置かないのか
#
#     ./check.sh | tail -2 && git commit
#
# **パイプの先の終了コードが返る。** tail は必ず 0 を返すので、
# 検査が落ちても先に進む。head・grep・jq・tee も同じ。
# ログに落として、落ちたときだけ読む。
set -e
cd "$(dirname "$0")/.."

find . -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true

LOG=${CHECK_LOG:-/tmp/keibai-check.log}
if ! python3 -m unittest discover -s tests > "$LOG" 2>&1; then
    tail -30 "$LOG"
    echo "**検査が落ちた。**（全文: $LOG）"
    exit 1
fi
tail -3 "$LOG"

if ! python3 scripts/check_copy.py; then
    echo "**評価の言葉が残っている。**"
    exit 1
fi
