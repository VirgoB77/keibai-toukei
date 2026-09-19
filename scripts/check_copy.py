#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公開する木に、評価の言葉が混ざっていないか（正本 3.3）。

**地名と並ぶと、その土地への決めつけになる言葉**を探す。
「この地域は危険」「◯◯市は治安が悪い」は、事実ではなく評価。
このサイトが出すのは、事実と、事実から機械的に出る数字だけ。

姉妹サイト（街頭窃盗統計）の `scripts/check_copy.py` を写した。

**.md と .py を外さない。** 外していたせいで、姉妹サイトは CLAUDE.md の
評価語13か所を長いあいだ見落としていた（2026-09-17）。
GitHub Pages は `.nojekyll` があるとリポジトリの中身をそのまま配るので、
`.md` も `.py` も画面と同じく人が読める。

**例外リストを作らない。** 当たったら、文脈で言い換える。
「安全な側に倒す」→「きつい側に倒す」のように、設計の言葉なら必ず言い換えられる。
例外を作ると、そこに本物が紛れ込んだときに気づけない。

    python3 scripts/check_copy.py          公開する木を見る
    python3 scripts/check_copy.py --all    金庫の中も全部見る
"""

import io
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 地名と並ぶと、その土地への決めつけになる言葉
NG = (
    "危険", "治安", "物騒", "不安", "安心", "安全", "警戒",
    "注意", "要注意", "気をつけ",
    "悪い", "悪化", "劣悪", "良い", "良好",
    "おすすめ", "オススメ", "お勧め",
    "ワースト", "ベスト", "避けた", "避ける",
)

# 数字の読み方に関わる言葉は、評価ではないので対象にしない
# （凡例の「少ない／多い」、本文の「大きくなりやすい」など）。

TARGET_SUFFIX = {".html", ".css", ".xml", ".md", ".py", ".yml"}

# 自分自身は見ない。NG語を文字列として持っているので必ず当たる
SELF = {"check_copy.py"}

# 金庫にしか無いもの。公開する木には入らない（DESIGN「公開側」）
VAULT_ONLY = ("data", "inbox", "tests/fixtures", ".git", "__pycache__")


def _under(rel, paths):
    return any(rel == q or rel.startswith(q + "/") for q in paths)


def walk(root, everything=False):
    for cur, dirs, files in os.walk(root):
        rel_dir = os.path.relpath(cur, root).replace(os.sep, "/")
        rel_dir = "" if rel_dir == "." else rel_dir
        dirs[:] = [d for d in dirs
                   if everything and d not in (".git", "__pycache__")
                   or not everything
                   and not _under("/".join(filter(None, [rel_dir, d])),
                                  VAULT_ONLY)]
        for name in sorted(files):
            if name in SELF:
                continue
            if os.path.splitext(name)[1] not in TARGET_SUFFIX:
                continue
            rel = "/".join(filter(None, [rel_dir, name]))
            if not everything and _under(rel, VAULT_ONLY):
                continue
            yield rel, os.path.join(cur, name)


def find(root, everything=False):
    out = []
    for rel, path in walk(root, everything):
        with io.open(path, encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f, 1):
                for w in NG:
                    if w in line:
                        out.append((rel, i, w, line.strip()))
    return out


def main(argv):
    everything = "--all" in argv
    hits = find(HERE, everything)
    for rel, i, w, line in hits:
        print("%s:%d  [%s]  %s" % (rel, i, w, line[:90]))
    where = "金庫の中も全部" if everything else "公開する木"
    if hits:
        print()
        print("**%s に評価の言葉が %d か所**（正本 3.3）。" % (where, len(hits)))
        print("**例外リストを作らない。** 文脈で言い換えること。")
        print("設計の言葉なら必ず言い換えられる（「安全な側」→「きつい側」）。")
        return 1
    print("%s に評価の言葉は無かった（%d ファイルを見た）"
          % (where, sum(1 for _ in walk(HERE, everything))))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
