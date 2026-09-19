#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""偵察レポートの章を、足すのではなく差し替える。

`terms.py` も `kibo.py` も、自分の章を `open(..., "a")` で書き足していた。
ふだんは `recon.py` がレポートを毎回まっさらから作り直すので気づかないが、
**作り直しが走らない回（収集先を絞って動かしたとき）に章が二重になる。**
実際、手元で3回動かしたら同じ章が3つ並んだ。

同じ見出しの章があれば入れ替え、無ければ末尾に足す。何回動かしても同じ形になる。
"""

import io
import os

SEP = "\n\n---\n\n"

# **走らせた記録は公開しない**（正本 9節）。
# ここには一次情報から写した行や、伏せる前の値がそのまま入りうる。
# 公開してよいのは data/public/ の中だけ。人が開いたときに、
# そのファイルだけを見て分かるように、記録の先頭にこの1行を置く。
NOT_PUBLIC_LINE = ("> **このファイルは公開しない。**"
                   "走らせた記録で、伏せる前の値が入りうる。"
                   "公開してよいのは `data/public/` の中だけ（正本 9節）。")


def not_public(title):
    """記録ファイルの見出し。題名のすぐ下に「公開しない」を置く。"""
    return "# %s\n\n%s\n" % (title, NOT_PUBLIC_LINE)


def put_head(path, text):
    """ファイルのいちばん上（最初の章より前）を入れ替える。

    `put_chapter()` の対。**こちらは書き出す側が1人だけ**の部分を持つ。

    1つの記録に2人以上が書くことがある。`data/parse-unknown.md` は
    `parse.py`（読めなかった見出し）と `aggregate.py`（段階が決まらなかった行）の
    2人が書く。**片方がファイルごと上書きすると、もう片方の章が消える。**
    消えても動くので、走らせても気づけない。実際にそうなっていた（2026-09-19）。

    いちばん上を持つ側は `put_head()`、章を足す側は `put_chapter()` を使う。
    どちらから何回走らせても、同じ形になる。
    """
    try:
        old = io.open(path, encoding="utf-8", newline="").read()
    except OSError:
        old = ""
    # 章の切れ目は「行頭の `# `」。**区切り（---）の有無で探さない。**
    # put_chapter が先に走ると、まっさらなファイルには区切りが付かないので、
    # 区切りで探すと章を見落として消す（2026-09-19 に踏んだ）
    # いちばん上の見出しが、いま書こうとしている頭と同じなら、それが「頭」。
    # 違えば、ファイル全体が章（頭がまだ無い）。
    # **区切り（---）の有無で探さない。** put_chapter が先に走ると、
    # まっさらなファイルには区切りが付かないので、区切りで探すと章を見落として消す
    # （2026-09-19 に踏んだ）
    def first_heading(t):
        for line in t.splitlines():
            if line.startswith("# "):
                return line
        return ""

    if old.startswith("# ") and first_heading(old) != first_heading(text):
        chapters = old.rstrip("\n")          # 頭がまだ無い。全部が章
    else:
        i = old.find("\n# ")
        chapters = old[i + 1:].rstrip("\n") if i >= 0 else ""
    body = text.rstrip("\n")
    # **どちらを先に走らせても同じ形にする。** 順番で差分が立つと、
    # 毎日ぶんの commit にその差分が混ざって、本当の変化が埋もれる
    out = body + (SEP + chapters + "\n" if chapters else "\n")
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(out)


def put_chapter(path, heading, body):
    """`# <heading>` の章を差し替える。無ければ末尾に足す。

    `heading` は `#` を含まない見出しの文字（例「利用規約（全文の控え）」）。
    `body` は章の中身（見出しの行は含めない）。
    """
    mark = "# %s\n" % heading
    try:
        # newline="" で読む。レポートには一次情報から写した行が入っていて、
        # 中に CR が混ざっていることがある。ふつうに読み書きすると黙って
        # 消える。**写したものは写したまま残す**（正本 9節）
        text = io.open(path, encoding="utf-8", newline="").read()
    except OSError:
        text = ""

    chapter = "%s%s\n%s" % (SEP, mark, body.rstrip("\n") + "\n")

    i = text.find("\n" + mark)
    if i < 0 and text.startswith(mark):
        i = -1                      # ファイルの先頭がその章
    if i >= 0 or text.startswith(mark):
        start = 0 if text.startswith(mark) else i + 1
        # 直前の区切り（---）も一緒に置き換える
        head = text[:start].rstrip("\n")
        if head.endswith("---"):
            head = head[:-3].rstrip("\n")
        # 次の章（行頭の `# `）の手前まで
        rest = text[start + len(mark):]
        j = rest.find("\n# ")
        tail = rest[j + 1:] if j >= 0 else ""
        text = head + chapter + (("\n" + tail) if tail else "")
    elif text.strip():
        text = text.rstrip("\n") + chapter
    else:
        # **まっさらなファイルの先頭に区切りを置かない。**
        # 置くと、いちばん上が `---` で始まる見た目になる
        text = chapter.lstrip("\n").replace(SEP.lstrip("\n"), "", 1) \
            if chapter.startswith(SEP) else chapter

    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
