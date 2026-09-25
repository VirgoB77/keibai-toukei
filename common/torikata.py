#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""取得元の可否（4語）と、題材の可否（通れる取得元が1つでもあるか）。

正本 9節「『その取得元が使えない』と『その題材が成立しない』を分ける」。**取得元と題材を分ける。**

    ある入札サイトが STOP  ≠  入札・公募 DB 全体が STOP

前は `sources.json` の `enabled` という真偽1つで決めていた。
実測（2026-09-21）: `enabled: false` の26件の中身は3種類で、
**「取ってはいけない」は1件も無かった。**

    題材が別（姉妹サイト送り）        21
    GETで再現できない（手で保存）      4
    相手にその頁が無い                 1

規約の話は1件も無い。**3つの違う話を、1つの真偽に潰していた。**

## 2026-09-25 から：4語は sources.json に書かない。カードから導く

前は `sources.json` の `torikata` / `torikata_riyuu` 欄に4語を人が書いていた。
いまは **`common/kado.py` のカード（`data/ref/torimoto-card.json`）＋運営者承認**
から導いた**正式状態**（`Kado.seishiki()`）を、そのまま4語として使う。
sources.json の2つの欄は消した（前の値はカードの「移行元」に写してある。
二重に持たない）。

**真偽を4語に替えるときの罠。** どの語も非空文字列なので、
`if not src.get("torikata")` のままだと**どの語でも真**になり、
「取ってはいけない」にも取りに行く。だから判定はここ1か所に集める。
**知らない語・欄が無いものは「取らない」に倒す**（きつい側）。

この置き場（keibai-toukei）だけの話ではなく、姉妹サイトと同じ形にそろえてある。
"""

import os

from common import kado
from common import site

# torikata.py（common/ の中）の親フォルダが、置き場の根。
# recon.py 等の「置き場の根にある .py」の HERE と同じ場所になる
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = "keibai-toukei"

# 取得元の欄。**この4語だけ**（正本 9節の同じ節の表）。値は kado.YON と同じ
GO = kado.YON
TORU = "取ってよい"          # **取りに行くのは、この1語だけ**
TORANAI = "取ってはいけない"

# いま取りに行かない理由。**取得元の話と、取り方の話と、題材の話を分ける**
RIYUU_DAIZAI = "題材が別（姉妹サイト送り）"
RIYUU_NAI = "相手にその頁が無い"
RIYUU_TEMOCHI = "GETで再現できない（人が手で保存して inbox に置く）"


def _kado():
    """カードを読むためだけの門。**install はしない**（通信はしない・できない）。

    呼ぶたびに作る。ROOT はテストが差し替えられるように、ここでモジュール変数を読む
    （関数の既定引数にすると、差し替えが効かない）。
    """
    return kado.Kado(ROOT, REPO, site.user_agent())


def go(src):
    """その取得元の4語。**カードから導いた正式状態**（`common/kado.py`）。

    `handoff` の取得元にはカードが無い（もともと取らない）。カードが無い id は
    `Kado.seishiki()` が「未確認」として返すので、ここで特別扱いはしない。
    """
    cid = src.get("id")
    if not cid:
        return ""
    return _kado().seishiki(cid)


def riyuu(src):
    """いまの判定理由。**表示用。** カードの「判定理由」、無ければ移行時に写した
    「移行元」の旧理由を見る。どちらも無ければ空文字（呼ぶ側で「理由が書いていない」等に倒す）。
    """
    cid = src.get("id")
    if not cid:
        return ""
    card = _kado().card(cid)
    if not card:
        return ""
    r = (card.get("判定理由") or "").strip()
    if r:
        return r
    return ((card.get("移行元") or {}).get("旧理由") or "").strip()


def naze_toranai(src):
    """いま自動で取りに行かない理由。取りに行くなら空文字。

    **理由を1つの真偽にしない。** 減らす手が違う。

        題材が別        こちらでは減らせない（よそがやる）
        相手に無い      相手が出したら取れる
        GETで再現できない  人が手で保存する
        カードの状態     カード（＋運営者承認）が「取ってよい」になれば動く
    """
    if src.get("handoff"):
        return RIYUU_DAIZAI
    # **手で保存するものが先。** BIT の一覧・結果・過去・取下げは
    # GETで再現できないので url が空になっている。url から見ると
    # 「相手にその頁が無い」と名乗ってしまう（実測 2026-09-21: 4件が誤名乗り）
    if src.get("manual"):
        return RIYUU_TEMOCHI
    if not src.get("url"):
        return RIYUU_NAI
    g = go(src)
    if not g:
        # id の無い取得元。sources.json の形が壊れている。**知らない語と同じく取らない側に倒す**
        return "取得元にカードidが無い（%r）" % (src.get("id"),)
    # **取りに行くのは「取ってよい」だけ**（2026-09-24）。
    # 前は「取ってはいけない」だけを止め、「未確認」「規約未確定」は取りに行っていた。
    # 迷ったら止まる。未確認を許可扱いしない（鯨屋DBの固定線）
    if g != TORU:
        return "取得元の欄が「%s」（取りに行くのは「%s」だけ）" % (g, TORU)
    return ""


def toru(src):
    """いま自動で取りに行くか。"""
    return not naze_toranai(src)


def kiwadoi(sources):
    """取りに行っているのに、欄が「取ってよい」ではない取得元。

    **黙って通さない。** 規約を読んでいない先から取っているなら、
    何件かを数えて出す。0 なら 0 と出す（欠けているキーは0ではない）。
    `naze_toranai()` が「取ってよい」だけを通すので、**いつも空が正しい。**
    空でなければ、関所が緩んでいる。
    """
    return [s for s in sources if toru(s) and go(s) != TORU]


def daizai(sources):
    """題材ごとに、通れる取得元が1つでもあるか。

    **取得元が1つ止まっても、題材が止まるとはかぎらない**（正本 9節の同じ節）。
    逆に、題材ぜんぶが止まっていることは、ここでしか見えない。
    """
    out = {}
    for s in sources:
        name = s.get("system") or "その他"
        枠 = out.setdefault(name, {"取得元": 0, "通る": 0, "通れる": False})
        枠["取得元"] += 1
        if toru(s):
            枠["通る"] += 1
            枠["通れる"] = True
    return {k: out[k] for k in sorted(out)}
