#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""親の升と、内訳の升のまとまりを「登録表」にする。

正本は https://github.com/VirgoB77/ogataten-nippo/blob/main/docs/kyotsu-shiyo.md
（3.2「合計の升と、内訳の升を、両方出さない」）。

決まりは3つ。

    1. 合計（親）の升は出さない。内訳（子）の升だけを出す
    2. 内訳は全部出す。1つでも欠けさせない
    3. 0件の内訳も 0 と書く（伏せた升 count: null と見た目で分ける）

**このファイルは決まりを守らせる仕組みだけを持つ。**
どんな親子があるかはサイトごとに違う（競売なら 公告／結果、
街頭窃盗なら手口）ので、そちらは各サイトが登録する。

    FAMILIES = Families(("結果", "結果-落札", "結果-不調"),
                        ("公告", "公告-新規", "公告-再公告"))

**規則を文章で書くと忘れられる。登録表にすると、書き忘れをテストが拾える。**
内訳を足すのに登録を忘れると undeclared() が拾う。

Python 3 の標準ライブラリだけで動く。
"""


class Families:
    """親と内訳のまとまりの登録表。

    1つのまとまりは `(親, 子1, 子2, ...)`。子を全部足すと親になる関係。
    種別が互いに排他なら（土地／戸建て／マンションのように）親子が無いので、
    ここには登録しない。登録するのは「全体」と「そのうち○○」を
    両方出したくなったときだけ。
    """

    SEP = "-"          # 内訳は「-」でつなぐ（正本 9節）

    def __init__(self, *families):
        for f in families:
            if len(f) < 2:
                raise ValueError("まとまりは親と子が要る: %r" % (f,))
            if self.SEP in f[0]:
                raise ValueError("親に「%s」は入らない: %r" % (self.SEP, f[0]))
            for kid in f[1:]:
                if not kid.startswith(f[0] + self.SEP):
                    raise ValueError("子は「親-…」の形にする: %r" % (kid,))
        self.families = tuple(tuple(f) for f in families)
        self.parents = tuple(f[0] for f in self.families)
        self.children = tuple(k for f in self.families for k in f[1:])

    def family_of(self, stage):
        """その段階が属するまとまり。内訳でも親でもなければ None。"""
        for f in self.families:
            if stage in f:
                return f
        return None

    def undeclared(self, stages):
        """内訳の形をしているのに、登録されていない段階。

        **書き忘れを拾うのがこの関数の仕事。**
        「土地-農地」を足して登録を忘れると、ここに出る。
        親を消すだけでは足りない。兄弟をそろえるところまでが1組。
        """
        return sorted({s for s in stages
                       if self.SEP in s and self.family_of(s) is None})

    def fill_siblings(self, buckets, stage_at, empty):
        """兄弟の升が欠けていたら足す（決まり2）。

        `buckets` は升の鍵（タプル）から中身への辞書。
        `stage_at` は鍵の何番目が段階か。`empty` は空の中身を作る関数。

        出さないと「伏せた」のか「1件も無かった」のかが読者に分からない。
        **まとまりが1つも出ていない升には足さない。** 足すと、
        そもそも何も起きていない月の升が増える。
        """
        for f in self.families:
            kids = f[1:]
            for key in [k for k in list(buckets) if k[stage_at] in kids]:
                for kid in kids:
                    sib = key[:stage_at] + (kid,) + key[stage_at + 1:]
                    if sib not in buckets:
                        buckets[sib] = empty()
        return buckets

    def is_parent(self, stage):
        """出してはいけない合計の升か（決まり1）。"""
        return stage in self.parents

    def missing_siblings(self, stages):
        """まとまりのうち1つでも出ていて、兄弟が欠けているもの。

        出す直前に自分で確かめるために使う。空なら欠けていない。
        """
        got = set(stages)
        out = []
        for f in self.families:
            kids = set(f[1:])
            if got & kids and (got & kids) != kids:
                out.append((f[0], sorted(kids - got)))
        return out


# **data/agg/ は公開しない。公開してよいのは data/public/ だけ。**
#
# data/agg/ には「同じ数を2つ以上の粗さで」置いてある（種別あり・種別なし、
# 庁×月・庁×年・府県×月…）。どの粗さで出すかを選ぶのはまだ先なので、
# 選べるように並べてある。**並べてあるものを2つ出すと、引き算で伏せた升が
# 戻る**（正本 3.2）。公開するときは、ここから**1つの粗さだけ**を選んで
# data/public/ に出す。
#
# 中の1つ1つは 3.2 を守っている（親の升は落とし、兄弟はそろえ、1〜2件は
# 伏せてある）。守れていないのは**ファイル全体**のほうで、粗さが混ざって
# いる。だから升ごとの手当てでは直らない。置き場所で分ける。
NOT_PUBLIC = ("このファイルは公開しない。公開してよいのは data/public/ だけ。"
              "ここには同じ数が2つ以上の粗さで入っている（どの粗さで出すかを"
              "選ぶのが先なので、選べるように並べてある）。2つの粗さを同時に"
              "出すと、引き算で伏せた升が戻る（正本 3.2）。"
              "出すときは1つの粗さだけを選んで data/public/ に写す")


def yoyuu(counts, small=2):
    """伏せた升のまとまり1つぶんの「余裕」（正本 3.2）。

    `counts` はそのまとまりに入る升の**真の件数**の並び。
    `small` は伏せる上限（1〜small 件を伏せる）。

    **「引き算で戻る升 0」だけでは足りない。** 戻る升を数えて0になっても、
    いまのデータでぎりぎり成り立っているだけかもしれない。升が減る、
    件数が増えて伏せる升が減る、月が1つ増える。どれでも同じ作りのまま戻る。

    親の合計から引けば伏せた升の**和**は出るので、`m`（2件だった升の数）は
    確定すると思ってよい。守っているのは和ではなく
    「**どの m 個が2件か**」の組合せのほうで、その数が C(k, m) 通りある。

        k    伏せた升の数
        m    そのうち上限（2件）だった升の数
        余裕 = min(m, k - m)

    `m` が 0 か `k` に張り付くほど組合せが減り、張り付けば升が特定できる。
    **`k` が1なら、和が分かった時点で確定する。**

    戻すのは辞書。`余裕` が 0 なら、親がどこかに1度出た瞬間に
    まとまり全部の升が決まる。

    **足してから測るのではなく、足す前に測る**（正本 3.2）。
    年や市や種別を足す手順に、この測定を組み込むこと。
    """
    hidden = [n for n in counts if 0 < n <= small]
    k = len(hidden)
    m = sum(1 for n in hidden if n == small)
    return {
        "k": k,
        "m": m,
        "余裕": min(m, k - m) if k else 0,
        "組合せ": _choose(k, m) if k else 0,
        "和": sum(hidden),
    }


def must_hide_parent(counts, small=2):
    """親を出してはいけないまとまりか（正本 3.2）。

        **当てる組合せが1通りしかないまとまりは、親を出さない。例外なし。**

    `C(k, m) = 1` は「伏せた升がすべて確定する」という意味で、
    伏せていないのと同じ。**`k = 1` は常にこれに当たる。**

        k=1   → 1通り        確定する
        k=2   → 最大 2通り    ほぼ確定する
        k=4   → 最大 6通り
        k=10  → 最大 252通り
        k=20  → 最大 184,756通り

    **残りのしきい値は、4サイトの実測が出そろってから決まる。**
    それまでは各サイトが実測を決定ログに置き、**親を出さない側に倒す**
    （出さない判断のほうが、あとから戻せる）。

    伏せた升が無いまとまり（`k = 0`）は False。隠すものが無い。
    """
    d = yoyuu(counts, small)
    return d["k"] > 0 and d["組合せ"] == 1


def _choose(n, r):
    """C(n, r)。math.comb は 3.8 から。古い Python でも動くように自前で持つ。"""
    if r < 0 or r > n:
        return 0
    r = min(r, n - r)
    out = 1
    for i in range(r):
        out = out * (n - i) // (i + 1)
    return out
