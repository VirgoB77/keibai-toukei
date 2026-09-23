#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""index.json に「出してはいけないもの」が出ないことを固定する。

ここが緩むと、個人名義の居宅が住所つきで一覧に並ぶ。
いちばん壊してはいけない壁なので、テストで縛る。

    python3 -m unittest discover -s tests
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import make_index  # noqa: E402


def 行(**kw):
    """試すための行データ。足りない項目は空でよい。"""
    row = {"system": "koyu", "key": "k1", "pref": "兵庫県", "city": "西宮市",
           "address": "甲子園町1番1号", "kind": "土地", "sources": ["koyu-x"],
           "open_date": "2026-09-01", "last_seen": "2026-09-14"}
    row.update(kw)
    return row


class 法人名だけを出す(unittest.TestCase):

    def test_法人は出す(self):
        for name in ("株式会社カネカ", "有限会社山田工務店", "合同会社みらい",
                     "一般社団法人○○協会", "医療法人社団△△会"):
            self.assertEqual(make_index.corp_name(name), name)

    def test_個人名は空文字にする(self):
        for name in ("山田太郎", "", None, "田中", "山田商店"):
            self.assertEqual(make_index.corp_name(name), "")


class 個票を出す条件(unittest.TestCase):

    def test_法人が落札したものは出す(self):
        self.assertTrue(make_index.shows_detail(行(winner_name="株式会社あ")))

    def test_事業用のものは出す(self):
        for kw in ({"kind_raw": "店舗"}, {"kind_raw": "事務所"},
                   {"former_use": "工場跡地"}, {"kind_raw": "倉庫"},
                   {"zoning": "商業地域"}, {"zoning": "工業地域"}):
            self.assertTrue(make_index.shows_detail(行(**kw)), kw)

    def test_個人名義の居宅は出さない(self):
        self.assertFalse(make_index.shows_detail(
            行(kind="戸建て", kind_raw="住宅", winner_name="山田太郎")))
        self.assertFalse(make_index.shows_detail(
            行(kind="マンション", kind_raw="区分所有建物")))

    def test_競売と公売は中身にかかわらず出さない(self):
        for system in ("keibai", "kobai"):
            self.assertFalse(make_index.shows_detail(
                行(system=system, kind_raw="店舗", winner_name="株式会社あ")),
                system)


class 人が住んでいるものは個票にしない(unittest.TestCase):
    """正本 3.1「人が住んでいる可能性があるものは、個票として扱わない
    （競売・公売の入札中物件、居住用途の建物、住居系用途地域）」。

    法人が買った土地でも、そこに居宅が建っていれば住んでいる人がいる。
    買い手が誰かと、住んでいる人がいるかは別の話。**迷ったら住んでいる側に倒す。**
    """

    def 行(self, **kw):
        r = 行(winner_name="株式会社あ", kind_raw="工場", zoning="工業地域")
        r.update(kw)
        return r

    def test_事業用のものは出す(self):
        self.assertTrue(make_index.shows_detail(self.行()))

    def test_居住用途は出さない(self):
        for kw in ({"kind_raw": "居宅"}, {"kind_raw": "共同住宅"},
                   {"kind_raw": "アパート"}, {"kind": "マンション"},
                   {"kind": "戸建て"}, {"kind_raw": "寄宿舎"}):
            self.assertFalse(make_index.shows_detail(self.行(**kw)), kw)

    def test_住居系の用途地域は出さない(self):
        for z in ("第一種低層住居専用地域", "第二種中高層住居専用地域",
                  "準住居地域", "田園住居地域"):
            self.assertFalse(make_index.shows_detail(self.行(zoning=z)), z)

    def test_事業用と住まいが混じったら落とすほうを採る(self):
        self.assertFalse(make_index.shows_detail(self.行(kind_raw="店舗兼住宅")))

    def test_間取りが書いてあれば人が住む形の建物(self):
        self.assertFalse(make_index.shows_detail(self.行(madori="3LDK")))


class 升は3つ組でひとつ(unittest.TestCase):
    """正本 6節「升は city_code × kind × period で決まる。**1 要素 = 1 つの升**」。

    物件の種別（土地・マンション・戸建て）はこの3本に書く場所が無い。
    軸を1本落としたまま升を分けると、同じ3つ組の升がいくつも出て、
    読む側はどれがどれか分からず、足すこともできない。
    """

    def 行(self, no, kind, status):
        return {"system": "keibai", "court_id": "33111", "kind": kind,
                "pref": "大阪府", "city": "大阪市北区",
                "address": "梅田1丁目1番1号", "status": status,
                "open_date": "2026-09-11", "notice_date": "2026-08-12",
                "base_price": 1000000, "first_seen": "2026-09-01",
                "last_seen": "2026-09-16", "case_no": "令和06年(ケ)第%d号" % no,
                "item_no": "1", "key": "33111:%d:1:2026-09-11" % no,
                "property_key": "33111:%d:1" % no,
                "source_url": "https://x", "name_column": "未確認"}

    def test_同じ3つ組の升が2つ出ない(self):
        rows = [self.行(1, "土地", "売却"), self.行(2, "マンション", "売却"),
                self.行(3, "戸建て", "不売"), self.行(4, "土地", "売却")]
        cb = make_index.build(rows)["counts_by_city"]
        keys = [(c["city_code"], c["kind"], c["period"]) for c in cb]
        self.assertEqual(len(keys), len(set(keys)), keys)

    def test_種別を畳んでも件数は合う(self):
        # 土地2＋マンション1＋戸建て1＝4。種別で割って 1-2 が並ぶのではなく、
        # 畳んだ1つの升に4と出る。親（公告）は出さないので、子で見る
        rows = [self.行(1, "土地", "売却"), self.行(2, "マンション", "売却"),
                self.行(3, "戸建て", "不売"), self.行(4, "土地", "売却")]
        cb = make_index.build(rows)["counts_by_city"]
        n = {c["kind"]: c["count"] for c in cb}
        self.assertEqual(n["競売/公告-初出"], 4)
        self.assertEqual(n["競売/公告-再出"], 0)


class 引き算で伏せた升を戻せない(unittest.TestCase):
    """正本 3.2「同じものを2つの粗さで出していると、引き算で正確な値が分かる」。

        結果 6 ／ 落札 4 ／ 不調 1-2  →  6 − 4 ＝ 2

    1件なのか2件なのかまで分かり、伏せた意味が消える。
    """

    def 行(self, no, status):
        return {"system": "keibai", "court_id": "33111", "kind": "土地",
                "pref": "大阪府", "city": "大阪市北区",
                "address": "梅田1丁目1番1号", "status": status,
                "open_date": "2026-09-11", "notice_date": "2026-08-12",
                "base_price": 1000000, "first_seen": "2026-09-01",
                "last_seen": "2026-09-16", "case_no": "令和06年(ケ)第%d号" % no,
                "item_no": "1", "key": "33111:%d:1:2026-09-11" % no,
                "property_key": "33111:%d:1" % no,
                "source_url": "https://x", "name_column": "未確認"}

    def test_子が伏せてあるとき親を出さない(self):
        # 落札4 ＋ 不調2。不調は 1-2 に伏せる。親を出すと 6-4=2 で戻る
        rows = [self.行(i, "売却") for i in range(4)]
        rows += [self.行(i, "不売") for i in range(4, 6)]
        cb = make_index.build(rows)["counts_by_city"]
        kinds = {c["kind"] for c in cb}
        self.assertIn("競売/落札", kinds)
        self.assertIn("競売/不調", kinds)
        self.assertNotIn("競売/結果", kinds)

    def test_親は常に出さない(self):
        # 伏せる升が無くても親は出さない。**足し算が二重になるから。**
        # 公告-初出は公告の内数で、並べると「公告7＋初出7＝14」と読める
        rows = [self.行(i, "売却") for i in range(4)]
        rows += [self.行(i, "不売") for i in range(4, 7)]
        cb = make_index.build(rows)["counts_by_city"]
        kinds = {c["kind"] for c in cb}
        self.assertNotIn("競売/結果", kinds)
        self.assertNotIn("競売/公告", kinds)

    def test_残った升を足すと物件の数になる(self):
        # 親を外したので、残る升は互いに重ならない。足し算がそのまま正しい
        rows = [self.行(i, "売却") for i in range(4)]
        rows += [self.行(i, "不売") for i in range(4, 7)]
        cb = make_index.build(rows)["counts_by_city"]
        n = {c["kind"]: c["count"] for c in cb}
        self.assertEqual(n["競売/公告-初出"] + n["競売/公告-再出"], 7)
        self.assertEqual(n["競売/落札"] + n["競売/不調"], 7)

    def test_落札率の材料は残る(self):
        # 親を落としても、分母は「落札＋不調」で読者が作れる
        rows = [self.行(i, "売却") for i in range(4)]
        rows += [self.行(i, "不売") for i in range(4, 6)]
        cb = make_index.build(rows)["counts_by_city"]
        got = {c["kind"]: c["count_label"] for c in cb}
        self.assertEqual(got["競売/落札"], "4")
        self.assertEqual(got["競売/不調"], "1-2")

    def test_公告も同じように守る(self):
        # 公告 ＝ 公告-初出 ＋ 公告-再出。再出の升を出していなかったころは、
        # 公告6 − 公告-初出5 ＝ 1 で再出が1件だと分かってしまった
        rows = [self.行(i, "売却") for i in range(5)]
        rows += [dict(self.行(5, "売却"), saishutsu=True)]
        cb = make_index.build(rows)["counts_by_city"]
        kinds = {c["kind"]: c["count_label"] for c in cb}
        self.assertIn("競売/公告-初出", kinds)
        self.assertIn("競売/公告-再出", kinds)
        self.assertNotIn("競売/公告", kinds)     # 親は出さない
        self.assertEqual(kinds["競売/公告-再出"], "1-2")

    def test_内部の目印が公開ファイルに漏れない(self):
        rows = [self.行(i, "売却") for i in range(4)]
        cb = make_index.build(rows)["counts_by_city"]
        for c in cb:
            self.assertNotIn("_n", c)
            self.assertNotIn("_hide", c)


class 黙って捨てない(unittest.TestCase):
    """正本 9節「知らないものを黙って捨てない。落ちているものは落ちていると分かる形で残す」。"""

    def test_市区町村コードが引けない升を控える(self):
        # 府中市は東京都と広島県にあり、都道府県が空だとコードが決まらない
        row = 行(pref="", city="府中市", winner_name="株式会社あ",
                 kind_raw="工場", status="売却")
        out = make_index.build([row])
        self.assertTrue(out["_dropped"], "捨てた升を控えていない")
        self.assertEqual(out["counts_by_city"], [])

    def test_控えは出力に混ぜない(self):
        import json as _json
        import os as _os
        import tempfile
        row = 行(pref="", city="府中市", winner_name="株式会社あ",
                 kind_raw="工場", status="売却")
        out = make_index.build([row])
        dropped = out.pop("_dropped")
        self.assertNotIn("_dropped", _json.dumps(out))
        # 書き出しても落ちない
        d = tempfile.mkdtemp()
        keep = make_index.DROPPED_PATH
        try:
            make_index.DROPPED_PATH = _os.path.join(d, "x.md")
            make_index.write_dropped(dropped)
            with open(make_index.DROPPED_PATH, encoding="utf-8") as f:
                self.assertIn("府中市", f.read())
        finally:
            make_index.DROPPED_PATH = keep


class privacyを迂回させない(unittest.TestCase):
    """正本 5節「出力する値は必ずここを通す。通さない経路を作らない」。"""

    def test_行データが名乗るparty_kindを信じない(self):
        # 行データに undisclosed と書いてあっても、確かめていなければ individual。
        # undisclosed は地番まで出してよい種類なので、騙られると地番が出る
        row = 行(winner_name="山田太郎", party_kind="undisclosed",
                 kind_raw="工場", zoning="工業地域", name_column="未確認",
                 address="甲子園町1番1号")
        rec = make_index.build([row])["records"][0]
        self.assertEqual(rec["party_kind"], "individual")
        self.assertEqual(rec["party"], "")
        self.assertEqual(rec["addr"], "西宮市甲子園町")   # 町丁目まで丸める
        self.assertEqual(rec["addr_key"], "")            # 細かい鍵は出さない

    def test_法人でも名乗りをそのまま通さない(self):
        row = 行(winner_name="株式会社あ", party_kind="undisclosed",
                 kind_raw="工場", zoning="工業地域", name_column="未確認")
        rec = make_index.build([row])["records"][0]
        self.assertEqual(rec["party_kind"], "corp")


class 正本6_個票に出した種別は升に出さない(unittest.TestCase):
    """正本 6節（2026-09-17 に直った）。

        その種別を個票の粒度で出しているなら、`counts_by_city` には出さない。
        親と子の両方を出すことになり、引き算で伏せた子が戻る（3.2）。
        …同じ数を2か所に書かないのはもちろんだが、
        **危ないのは重複ではなく粗さの違う両方出しのほう。**

    個票は番地まで、升は市区町村まで。同じ行を両方に出すと、
    読者は個票を数えて升から引ける。

    競売・公売は個票を1件も出さないので、いまは発火しない。
    **国有財産・公有財産の行が入った日に発火する。**
    """

    def 国有財産(self, i, name, kind):
        return 行(key="n%d" % i, system="kokuyu", pref="大阪府", city="豊中市",
                  address="○○町%d番%d" % (i, i), kind=kind, kind_raw=kind,
                  winner_name=name, first_seen="2026-09-01",
                  month_kokoku="2026-09", case_no="X%d" % i, item_no="1",
                  property_key="k%d" % i)

    def test_個票に出した行は升で数えない(self):
        # 4行のうち3行が法人＝個票に出る。残る1行は個人なので出ない
        rows = [self.国有財産(1, "○○株式会社", "工場"),
                self.国有財産(2, "○○株式会社", "工場"),
                self.国有財産(3, "○○合同会社", "工場"),
                self.国有財産(4, "", "戸建て")]
        out = make_index.build(rows)
        self.assertEqual(len(out["records"]), 3)
        # 升が実数4を出すと、個票3を引いて残り1が確定する。
        # 個票に出した3行を数えないので、実数の升は1つも出ない
        # （0 は引き算の起点にならないので数えない）
        real = [c for c in out["counts_by_city"] if c["count"]]
        self.assertEqual(real, [], "個票を引いて戻る実数が升に出ている")

    def test_個票に出さなかった行は升に残す(self):
        """**黙って捨てない**（正本 9節）。

        制度（system）ごと丸ごと外すと、同じ制度の中の
        「個票にしないと決めた行」まで消える。行ごとに分けること。
        """
        rows = [self.国有財産(1, "○○株式会社", "工場"),
                self.国有財産(4, "", "戸建て")]
        out = make_index.build(rows)
        self.assertEqual(len(out["records"]), 1)
        codes = {c["city_code"] for c in out["counts_by_city"]}
        self.assertIn("27203", codes)   # 豊中市。個人の1行がここで数えられている


class 正本32_合計の升と内訳の升を両方出さない(unittest.TestCase):
    """正本 3.2「合計の升と、内訳の升を、両方出さない」。

    **この節は、このリポジトリの index.json から書かれた**（2026-09-17）。
    正本に載っている例そのものを、ここで固定する。
    形を変えるときは、正本のほうも直すこと。

        {"kind": "競売/公告-初出",   "count": null, "count_label": "1-2"}
        {"kind": "競売/公告-再出", "count": 0,    "count_label": "0"}
    """

    def 行(self, no, status="売却", **kw):
        r = {"system": "keibai", "court_id": "33111", "kind": "土地",
             "pref": "大阪府", "city": "大阪市西区",
             "address": "九条1丁目1番1号", "status": status,
             "open_date": "2026-09-11", "notice_date": "2026-09-01",
             "base_price": 1000000, "first_seen": "2026-09-01",
             "last_seen": "2026-09-17", "case_no": "令和06年(ケ)第%d号" % no,
             "item_no": "1", "key": "33111:%d:1:2026-09-11" % no,
             "property_key": "33111:%d:1" % no,
             "source_url": "https://x", "name_column": "未確認"}
        r.update(kw)
        return r

    def test_正本に載っている例と同じ形が出る(self):
        # 新規が1件（伏せる）、再公告は0件
        cb = make_index.build([self.行(1)])["counts_by_city"]
        got = {c["kind"]: (c["count"], c["count_label"]) for c in cb
               if c["kind"].startswith("競売/公告")}
        self.assertEqual(got, {"競売/公告-初出": (None, "1-2"),
                               "競売/公告-再出": (0, "0")})

    def test_決まり1_合計の升を出さない(self):
        rows = [self.行(i) for i in range(5)]
        kinds = {c["kind"] for c in make_index.build(rows)["counts_by_city"]}
        self.assertNotIn("競売/公告", kinds)
        self.assertNotIn("競売/結果", kinds)

    def test_決まり2_内訳を1つも欠けさせない(self):
        rows = [self.行(i) for i in range(5)]
        cb = make_index.build(rows)["counts_by_city"]
        kinds = {c["kind"] for c in cb}
        self.assertIn("競売/公告-初出", kinds)
        self.assertIn("競売/公告-再出", kinds)
        self.assertIn("競売/落札", kinds)
        self.assertIn("競売/不調", kinds)

    def test_決まり3_0件の内訳は0と書く(self):
        # 伏せた升（null）と本当に0件の升（0）を見た目で分ける
        rows = [self.行(i) for i in range(5)]
        cb = make_index.build(rows)["counts_by_city"]
        n = {c["kind"]: (c["count"], c["count_label"]) for c in cb}
        self.assertEqual(n["競売/公告-再出"], (0, "0"))
        self.assertEqual(n["競売/不調"], (0, "0"))
        for c in cb:
            if c["count"] is None:
                self.assertEqual(c["count_label"], "1-2")
            elif c["count"] == 0:
                self.assertEqual(c["count_label"], "0")

    def test_足すと物件の数に合う(self):
        rows = [self.行(i) for i in range(5)]
        cb = make_index.build(rows)["counts_by_city"]
        n = {c["kind"]: c["count"] for c in cb}
        self.assertEqual(n["競売/公告-初出"] + n["競売/公告-再出"], 5)

    def test_内訳を足すときは必ずまとまりに書く(self):
        # 「-」でつないだ段階は内訳。FAMILIES に書かずに足すと、
        # 兄弟がそろっているかを誰も確かめない。
        # 将来「土地-農地」を足すときに、ここが効く
        import aggregate
        self.assertEqual(aggregate.FAMILIES.undeclared(aggregate.CHILDREN), [])
        # わざと登録していない内訳を渡すと拾う
        self.assertEqual(
            aggregate.FAMILIES.undeclared(["土地-農地", "落札", "土地"]),
            ["土地-農地"])
        for stage in aggregate.PARENTS:
            self.assertNotIn("-", stage, stage)

    def test_undeclaredは接頭辞なしの段階を拾えない(self):
        """**この網が何を見ていないかを、書いておく。**

        `undeclared()` は「-」を含む名前しか拾わない。
        結果の語が `結果-落札` → `落札` になった日から、
        **接頭辞を持たない段階の登録忘れは、この網を素通りする。**
        上のテストは一括置換で `落札` を渡すようになっていて、
        素通りすることを**偶然**示していたが、そうとは書いていなかった。

        素通りしたものを受けるのは `kazu_ga_au()` のほう
        （升に出る段階が全部登録されているか）。**2本で1組。**
        """
        import aggregate
        self.assertEqual(aggregate.FAMILIES.undeclared(["落札", "取下げ"]), [],
                         "接頭辞なしの段階を undeclared が拾えるようになった")
        # 受けるのはこちら
        rows = [{"system": "keibai", "pref": "兵庫県", "city": "西宮市",
                 "city_code": "28204", "kind": "土地",
                 "first_seen": "2026-09-01", "open_date": "2026-09-10",
                 "status": "売却"}]
        cells = aggregate.aggregate(rows, with_raw=True)
        にせ = cells + [dict(cells[0], stage="取下げ", _n=1)]
        d = aggregate.kazu_ga_au(rows, にせ, today="2026-09-19")
        self.assertTrue(any("登録されていない段階" in b for b in d["食い違い"]),
                        "素通りしたものを、誰も受けていない")

    def test_出した内訳は全部まとまりに属している(self):
        # 実際に出した升を見て、知らない内訳が混ざっていないか確かめる
        import aggregate
        rows = [self.行(i) for i in range(5)]
        for c in make_index.build(rows)["counts_by_city"]:
            stage = c["kind"].split("/", 1)[1]
            if "-" not in stage:
                continue
            self.assertIsNotNone(
                aggregate.family_of(stage),
                "%s は内訳なのに aggregate.FAMILIES に書かれていない。"
                "兄弟をそろえないと引き算で戻る（正本 3.2）" % c["kind"])

    def test_出した内訳は兄弟がそろっている(self):
        # まとまりのうち1つでも出ていたら、残りも全部出ていること
        import collections

        import aggregate
        rows = [self.行(i) for i in range(5)]
        cb = make_index.build(rows)["counts_by_city"]
        by = collections.defaultdict(set)
        for c in cb:
            by[(c["city_code"], c["period"])].add(c["kind"].split("/", 1)[1])
        for key, stages in by.items():
            self.assertEqual(aggregate.FAMILIES.missing_siblings(stages), [],
                             "%s で兄弟が欠けている" % (key,))
            for st in stages:
                self.assertFalse(aggregate.FAMILIES.is_parent(st),
                                 "%s で親の升 %s が出ている" % (key, st))

    def test_種別が排他なら親子は作らない(self):
        # 土地／戸建て／マンションは互いに排他なので、そもそも親子が無い。
        # 「全体」と「そのうち○○」を両方出したくなったときだけ効く規則
        rows = [self.行(1, kind="土地"), self.行(2, kind="戸建て"),
                self.行(3, kind="マンション")]
        kinds = {c["kind"] for c in make_index.build(rows)["counts_by_city"]}
        for ng in ("競売/土地", "競売/戸建て", "競売/マンション"):
            self.assertNotIn(ng, kinds)


class サイトの名乗り(unittest.TestCase):
    """site は**このサイトの名前**。公開先の置き場の名前ではない（正本 6節）。

    id は `<site>:<source>:<date>:<連番>` で「サイトをまたいで衝突しないこと」。
    ic-log は生成物を受け取る公開リポジトリで、開発系サイトの生成物も
    同じ場所に入る予定なので、site に使うと2サイトの id がぶつかる。
    """

    def test_siteはこのサイトの名前(self):
        # 2026-09-18 に決めた。独自ドメイン keibai-toukei.com の語幹
        self.assertEqual(make_index.SITE, "keibai-toukei")

    def test_公開先の置き場の名前をsiteに使わない(self):
        self.assertNotEqual(make_index.SITE, "ic-log")

    def test_リポジトリ名をsiteに使わない(self):
        """リポジトリ名は変わる（金庫は `keibai-toukei-raw` に rename する）。

        正本 9節「鍵にはあとから変わらないものだけを入れる」。
        """
        self.assertNotEqual(make_index.SITE, "keibai-data")
        self.assertNotEqual(make_index.SITE, "keibai-toukei-raw")

    def test_名乗りはsite_jsonから配る(self):
        from common import site
        self.assertEqual(make_index.SITE, site.SITE["site_id"])


class 組み立てたindex(unittest.TestCase):

    def setUp(self):
        # status を入れる。**段階が決まらない行は升を作らない**ようになったので
        # （2026-09-19。「不明」という段階をやめた）、升を見るテストには要る
        self.index = make_index.build([
            行(key="a", winner_name="株式会社あ", address="甲子園町1番1号",
              status="売却"),
            行(key="b", kind="戸建て", kind_raw="住宅", winner_name="山田太郎",
              status="売却"),
            行(key="c", system="keibai", city="大阪市北区", pref="大阪府",
              address="", kind_raw="店舗", status="売却"),
        ], today="2026-09-14")

    def test_形が決まりどおり(self):
        for k in ("site", "site_name", "generated_at", "records",
                  "counts_by_city"):
            self.assertIn(k, self.index)
        self.assertEqual(self.index["generated_at"], "2026-09-14")

    def test_出るのは法人の1件だけ(self):
        self.assertEqual(len(self.index["records"]), 1)
        r = self.index["records"][0]
        self.assertEqual(r["party"], "株式会社あ")
        self.assertEqual(r["city_code"], "28204")
        self.assertEqual(r["addr_key"], "28204|甲子園町1-1")

    def test_出さなかったものは件数で残る(self):
        cells = self.index["counts_by_city"]
        # 升は city_code × kind × period の3本で決まる（正本 6節）
        for c in cells:
            for k in ("city_code", "city", "kind", "period",
                      "count", "count_label"):
                self.assertIn(k, c)
        codes = {c["city_code"] for c in cells}
        self.assertEqual(codes, {"28204", "27127"})
        # 1件しか無い升は実数を出さず、ラベルで見せる
        hidden = [c for c in cells if c["count_label"] == "1-2"]
        self.assertTrue(hidden)
        for c in hidden:
            self.assertIsNone(c["count"])
        # **兄弟の0件は 0 と書く**（正本 3.2 決まり3）。
        # 伏せた升（null）と見た目で分ける
        for c in cells:
            if c["count"] == 0:
                self.assertEqual(c["count_label"], "0")
            else:
                self.assertIsNone(c["count"])

    def test_升に何をいつ数えたかが書いてある(self):
        c = self.index["counts_by_city"][0]
        self.assertRegex(c["kind"], r"^(競売|公売|国有財産|公有財産)/")
        self.assertRegex(c["period"], r"^\d{4}-\d{2}$")

    def test_必須の項目がすべて入っている(self):
        need = ("id", "title", "kind", "date", "pref", "city", "city_code",
                "addr", "addr_key", "party", "url", "source_url", "fetched_on")
        for r in self.index["records"]:
            for k in need:
                self.assertIn(k, r)
                self.assertIsNotNone(r[k])

    def test_個人名はどこにも入らない(self):
        text = repr(self.index)
        self.assertNotIn("山田太郎", text)


class 数が合わない日はindexを作らない(unittest.TestCase):
    """**`make_index.build()` の `RuntimeError` を、実際に落として確かめる。**

    2026-09-19 に sys.settrace で数えたら、この raise は
    テストから**一度も通っていなかった**。検査ごと消しても全部緑だった。
    """

    行 = {"system": "keibai", "pref": "兵庫県", "city": "西宮市",
         "city_code": "28204", "kind": "土地", "first_seen": "2026-09-01",
         "open_date": "2026-09-10", "status": "売却"}

    def test_合っていれば作れる(self):
        out = make_index.build([dict(self.行)], today="2026-09-19")
        self.assertTrue(out["counts_by_city"])

    def test_升がまとまりごと落ちたら止まる(self):
        """**これが「黙って落としている」の実体。**

        升を作る側を差し替えて、まとまりを1つ落とす。
        前はこれで `counts_by_city` が減ったまま通っていた。

        **書き出し先を仮の場所に向ける。** `build()` は落ちる前に
        「数が合うこと」の章を書くので、向けないと
        **テストが `data/parse-unknown.md` を本当に書き換える**
        （2026-09-19、それが公開用の木に1つ混ざった）。
        """
        import aggregate
        本物 = make_index.make_cells
        元の先 = aggregate.UNKNOWN_PATH
        d = tempfile.mkdtemp()
        aggregate.UNKNOWN_PATH = os.path.join(d, "parse-unknown.md")

        def 落とす(rows, fields, with_raw=False):
            cells = 本物(rows, fields, with_raw=with_raw)
            return [c for c in cells if c["stage"] != "落札"]

        make_index.make_cells = 落とす
        try:
            with self.assertRaises(RuntimeError):
                make_index.build([dict(self.行)], today="2026-09-19")
        finally:
            make_index.make_cells = 本物
            aggregate.UNKNOWN_PATH = 元の先
            shutil.rmtree(d, ignore_errors=True)


class テストはdataを書き換えない(unittest.TestCase):
    """**テストが置き場を書き換えると、木に混ざる**（2026-09-19）。

    公開用の木を作ったあと、その木でテストを走らせた。
    テストが index を作る道を通り、その途中で `data/parse-unknown.md` が
    書かれ、**そのまま公開用に1コミット入った**（中身は架空の1行で、
    実在の物件・住所・事件番号は含まなかったが、置き場が違う）。

    書き出し先を仮の場所に向けるのを忘れると、また起きる。
    """

    def test_落ちる道を通っても本物を書かない(self):
        import aggregate
        本物 = make_index.make_cells
        元の先 = aggregate.UNKNOWN_PATH
        前 = (os.path.getmtime(元の先)
             if os.path.exists(元の先) else None)
        d = tempfile.mkdtemp()
        aggregate.UNKNOWN_PATH = os.path.join(d, "parse-unknown.md")

        def 落とす(rows, fields, with_raw=False):
            cells = 本物(rows, fields, with_raw=with_raw)
            return [c for c in cells if c["stage"] != "落札"]

        make_index.make_cells = 落とす
        try:
            with self.assertRaises(RuntimeError):
                make_index.build([{"system": "keibai", "pref": "兵庫県",
                                   "city": "西宮市", "city_code": "28204",
                                   "kind": "土地", "first_seen": "2026-09-01",
                                   "open_date": "2026-09-10",
                                   "status": "売却"}], today="2026-09-19")
            self.assertTrue(os.path.exists(aggregate.UNKNOWN_PATH),
                            "仮の場所にも書かれていない（向け先が効いていない）")
        finally:
            make_index.make_cells = 本物
            aggregate.UNKNOWN_PATH = 元の先
            shutil.rmtree(d, ignore_errors=True)
        後 = (os.path.getmtime(元の先)
             if os.path.exists(元の先) else None)
        self.assertEqual(前, 後, "テストが %s を書き換えた" % 元の先)


class 名乗れる語だけで数える(unittest.TestCase):
    """**主語を「こちら」にすると外れない**（2026-09-19）。

        ❌ 新規 / 再公告   事実の主張。こちらが見る前の回があると外れる
        ✅ 初出 / 再出     観測の記述。外れようがない

    こちらは 2026-09-17 から一覧を重ねている。7月に公告されて9月に
    再公告された物件も、こちらには「初めて見た回」として届く。
    それを「新規」と呼ぶのは、**持っていない知識を名乗る**こと。
    """

    def 行(self, i, saishutsu=False):
        return {"system": "keibai", "pref": "大阪府", "city": "茨木市",
                "kind": "土地", "first_seen": "2026-09-17",
                "seen": ["2026-09-17"],
                "open_date": "2026-11-05", "status": "",
                "property_key": "x:%d:1" % i, "key": "x:%d:1:2026-11-05" % i,
                "saishutsu": saishutsu}

    def test_事実を名乗る語を升に出さない(self):
        rows = [self.行(i) for i in range(4)]
        cb = make_index.build(rows)["counts_by_city"]
        文 = "".join(c["kind"] for c in cb)
        for 語 in ("新規", "再公告"):
            self.assertNotIn(語, 文,
                             "**こちらが見る前を知らない**のに、知っている語で"
                             "名乗っている（%s）" % 語)

    def test_観測の語で数える(self):
        rows = [self.行(i) for i in range(4)] + [self.行(9, True)]
        kinds = {c["kind"] for c in make_index.build(rows)["counts_by_city"]}
        self.assertIn("競売/公告-初出", kinds)
        self.assertIn("競売/公告-再出", kinds)

    def test_いつから見ているかを数字の隣に出す(self):
        """**これが無いと「初出」が読めない。**"""
        out = make_index.build([self.行(i) for i in range(4)])
        self.assertIn("observed", out, "いつから見ているかが出ていない")
        self.assertEqual(out["observed"]["競売"]["from"], "2026-09-17")
        self.assertEqual(out["observed"]["競売"]["days"], 1)

    def test_重ねた日の数はカレンダーの差ではない(self):
        """**1日しか重ねていなければ、初出が100%になるのは決まっている。**"""
        rows = [self.行(0), self.行(1)]
        rows[1]["seen"] = ["2026-09-17", "2026-09-30"]
        out = make_index.build(rows)
        self.assertEqual(out["observed"]["競売"]["days"], 2,
                         "見た日の数ではなく、日付の幅を数えている")

    def test_行が無い制度は出さない(self):
        """**空の欄を作って「0日見た」と読ませない。**"""
        out = make_index.build([self.行(0)])
        self.assertEqual(list(out["observed"]), ["競売"])

    def test_率を出していない(self):
        """正本 3.2「分子・分母のどちらかが伏せ字なら、率も出さない」。

            再出率 = 再出 ÷（初出 + 再出）
            再出が実数で率も出ていれば  初出 = 再出 ÷ 率 − 再出

        伏せた升が**正確に**戻る。実数が出せているのは 46組のうち14組だけ。
        **率はまだ早い**（DESIGN「率は出さない」）。
        """
        out = make_index.build([self.行(i) for i in range(4)])
        欄 = set()
        for c in out["counts_by_city"]:
            欄 |= set(c)
        for 語 in ("rate", "ratio", "percent", "率"):
            for k in 欄:
                self.assertNotIn(語, k, "升に率の欄がある（%s）" % k)
        self.assertNotIn("rate", set(out))


class 原因の違うものを1つの欄に入れない(unittest.TestCase):
    """**`unresolved` は「試して失敗した」という主張**（2026-09-19）。

    6節の意味は「読めなかった。語彙の穴。**こちらが減らす**」。
    ところが競売の結果は1枚も取りに行っていない
    （`bit-result` は URL が無く `enabled: false`、読み取りも無い）。

    開札日が過ぎた行は、**語が分からなかったのではなく、見に行っていない**。
    語をいくつ足しても1件も減らない。

        きょう 2026-09-19   0 件
        2026-10-03          37 件
        2026-12-25          **105 / 106**

    `open_date` が全部未来だったので、**この道は1度も走っていない。**
    10月2日に最初の1件が入る。

    正本に聞いている（docs/seihon-toiawase.md #18）。
    ここは**答えが来るまで、数が動くことを留めておく**ための検査。
    """

    def 行(self, i, open_date):
        return {"system": "keibai", "pref": "大阪府", "city": "茨木市",
                "kind": "土地", "first_seen": "2026-09-17",
                "seen": ["2026-09-17"], "open_date": open_date, "status": "",
                "property_key": "x:%d:1" % i,
                "key": "x:%d:1:%s" % (i, open_date), "saishutsu": False}

    def test_開札日が来る前は読めないに入れない(self):
        """**まだ起きていないものを「読めなかった」と言わない。**"""
        rows = [self.行(i, "2026-11-05") for i in range(3)]
        self.assertEqual(
            make_index.not_counted(rows, "2026-09-19")["unresolved"], 0)

    def test_開札日が過ぎたら見に行っていないに入る(self):
        """**答えが来たので分けた**（正本 6節・2026-09-19）。

        前はここが `unresolved` だった。**分けた日にこの検査が落ちた。
        落ちるのが正しかった。**

            unresolved  取りに行って、読んだが語が分からなかった → 語彙を足す
            unobserved  決めるのに要るページを取りに行っていない → 出どころを足す
        """
        rows = [self.行(i, "2026-11-05") for i in range(3)]
        got = make_index.not_counted(rows, "2026-12-25")
        self.assertEqual(got["unobserved"], 3)
        self.assertEqual(got["unresolved"], 0,
                         "取りに行っていないものを「読めなかった」と言っている")

    def test_4つとも必ず出す(self):
        """**欠けているキーは0ではない**（正本 6節）。

        3つしか出さないサイトが1つでもあると、横断で読む側は
        「0」と「このサイトは数えていない」を見分けられない。
        """
        for きょう in ("2026-09-19", "2026-12-25"):
            got = make_index.not_counted(
                [self.行(0, "2026-11-05")], きょう)
            self.assertEqual(sorted(got),
                             ["gone", "undecided", "unobserved", "unresolved"],
                             きょう)

    def test_語が書いてあれば語彙の穴のほう(self):
        """**読めた語と、読んでいない欄は別**（正本 6節・2026-09-19）。

        「取消」のように**読めたが置き場の無い語**は `unresolved`。
        欄が空のまま開札日が過ぎたものだけが `unobserved`。

        最初、こちらは制度だけで分けていた。**粗すぎた。**
        `取消` が「見に行っていない」に落ちて、
        `data/parse-unknown.md` から消えるところだった。
        """
        r = dict(self.行(0, "2026-11-05"), status="取消")
        got = make_index.not_counted([r], "2026-12-25")
        self.assertEqual(got["unresolved"], 1)
        self.assertEqual(got["unobserved"], 0)

    def test_読み取りを書いたら語彙の穴に移る(self):
        """**KEKKA_YOMERU に足した日から、意味が変わる。**

        出どころと読み取りができた制度は、欄が空でも「読んだのに無かった」。
        そこで初めて「語を足す」が効く。
        """
        import aggregate
        keep = aggregate.KEKKA_YOMERU
        try:
            aggregate.KEKKA_YOMERU = ("keibai",)
            got = make_index.not_counted(
                [self.行(0, "2026-11-05")], "2026-12-25")
            self.assertEqual(got["unresolved"], 1)
            self.assertEqual(got["unobserved"], 0)
        finally:
            aggregate.KEKKA_YOMERU = keep

    def test_結果の読み取りはまだ無い(self):
        """**これが「減らせない」の根拠。**

        読み取りが書かれた日に、上の2本の意味が変わる。
        そのとき一緒に見直すために、ここで留めておく。
        """
        import parse
        self.assertEqual(parse.INBOX_READABLE, ("list",))
        with open(os.path.join(ROOT, "sources.json"), encoding="utf-8") as f:
            srcs = json.load(f)["sources"]
        結果 = [s for s in srcs if s["id"] == "bit-result"][0]
        from common import torikata
        self.assertFalse(torikata.toru(結果),
                         "競売の結果を取り始めたなら、not_counted の意味も見直すこと")

    def test_正本に聞いてあることを控えてある(self):
        """**チャットで送っただけでは、両方が忘れる**（docs の冒頭）。"""
        path = os.path.join(ROOT, "docs", "seihon-toiawase.md")
        if not os.path.exists(path):
            self.skipTest("問い合わせの控えがここには無い")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("unresolved", text)
        self.assertIn("見に行っていない", text)


class 空の鍵で升を作らない(unittest.TestCase):
    """**横断ハブはコードで引く**（2026-09-19、姉妹サイトの実物から）。

    大型店日報が `city_code` を空のまま升を16枚作って公開していた。
    横断ハブはコードで引くので、**空の鍵にまとまるか、黙って落ちる。**
    どちらも「そこに何もなかった」と読めてしまう。

    こちらの実装は落としている（`make_index.build` が
    `if c.get("city_code")` で絞り、落ちた分は `data/index-dropped.md`）。
    **ただし、それを留めている検査が1本も無かった。**
    実装が正しいことと、見張りがあることは別。
    """

    def 行(self, city, i, code=None):
        r = {"system": "keibai", "pref": "大阪府", "city": city,
             "kind": "土地", "first_seen": "2026-09-17",
             "seen": ["2026-09-17"], "open_date": "2026-11-05", "status": "",
             "property_key": "x:%d:1" % i, "key": "x:%d:1:o" % i,
             "saishutsu": False}
        if code is not None:
            r["city_code"] = code
        return r

    def test_コードが引けない升は出さない(self):
        rows = [self.行("茨木市", i) for i in range(3)]
        rows += [self.行("そんな市は無い", 9 + i, code="") for i in range(3)]
        out = make_index.build(rows)
        空 = [c for c in out["counts_by_city"]
              if not (c.get("city_code") or "").strip()]
        self.assertEqual(空, [], "空の鍵で升を作っている")

    def test_全部の升にコードがある(self):
        rows = [self.行("茨木市", i) for i in range(3)]
        for c in make_index.build(rows)["counts_by_city"]:
            self.assertIn("city_code", c, "欄そのものが無い升がある")
            self.assertTrue((c["city_code"] or "").strip(), c)

    def test_落としたものは記録に残る(self):
        """**黙って捨てない**（正本 9節）。出せないことと、無いことは別。"""
        rows = [self.行("茨木市", i) for i in range(3)]
        rows += [self.行("そんな市は無い", 9, code="")]
        out = make_index.build(rows)
        self.assertTrue(out["_dropped"], "落とした升が控えに残っていない")

    def test_配っているものにも空の鍵が無い(self):
        """**仕掛けではなく実物を見る。** 出来上がったファイルを読む。"""
        path = os.path.join(ROOT, "data", "public", "index.json")
        if not os.path.exists(path):
            path = os.path.join(ROOT, "data", "index.json")
        if not os.path.exists(path):
            self.skipTest("配るファイルがここには無い")
        with open(path, encoding="utf-8") as f:
            cb = json.load(f)["counts_by_city"]
        for c in cb:
            code = (c.get("city_code") or "").strip()
            self.assertTrue(code, c)
            self.assertTrue(code.isdigit() and len(code) == 5,
                            "市区町村コードの形が違う（%r）" % code)


class 出した欄が空になっていないか(unittest.TestCase):
    """**同じ欄を見ていても、向きが逆だと捕まらない**（2026-09-19）。

    `city_code` は「ある値が入っているか」の検査がいくつもあったのに、
    「空のものが出ていないか」を見るものが1本も無かった。

    そこで**全部の欄を1つずつ空にして走らせた。** 3つ黙った。

        site       **横断ハブの結び目。** 空だとどのサイトの升か分からない
        site_name  人が読む名前
        city       人が読む市区町村名。コードは合っていても読めない

    `city_code` `kind` `period` `count` `count_label` `generated_at`
    `observed` は鳴った。

    **空でよい欄には理由を書く。理由が書けないなら、空にしてはいけない。**
    """

    # 空でよい欄と、その理由。**ここに無いものは空にしてはいけない**
    空でよい = {
        "records": "**個票は出さない**（正本 1節）。空が正しい姿",
        "count": "1〜2件は伏せる（正本 3.2）。`count_label` が '1-2' を持つ",
    }

    def 行(self, i):
        return {"system": "keibai", "pref": "大阪府", "city": "茨木市",
                "kind": "土地", "first_seen": "2026-09-17",
                "seen": ["2026-09-17"], "open_date": "2026-11-05",
                "status": "", "property_key": "x:%d:1" % i,
                "key": "x:%d:1:o" % i, "saishutsu": False}

    def 空か(self, v):
        return v is None or v == "" or v == {} or v == []

    def test_上の階層に空の欄がない(self):
        out = make_index.build([self.行(i) for i in range(4)])
        for k, v in out.items():
            if k.startswith("_") or k in self.空でよい:
                continue
            self.assertFalse(self.空か(v), "%s が空で出ている" % k)

    def test_升の欄に空がない(self):
        out = make_index.build([self.行(i) for i in range(4)])
        for c in out["counts_by_city"]:
            for k, v in c.items():
                if k in self.空でよい:
                    continue
                self.assertFalse(self.空か(v),
                                 "升の %s が空で出ている（%s）" % (k, c))

    def test_空でよい欄には理由が書いてある(self):
        for k, なぜ in self.空でよい.items():
            self.assertTrue(なぜ, "%s を空にしてよい理由が書いていない" % k)

    def test_配っているものにも空の欄がない(self):
        """**仕掛けではなく実物を見る**（③）。"""
        path = os.path.join(ROOT, "data", "public", "index.json")
        if not os.path.exists(path):
            path = os.path.join(ROOT, "data", "index.json")
        if not os.path.exists(path):
            self.skipTest("配るファイルがここには無い")
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        for k, v in d.items():
            if k in self.空でよい:
                continue
            self.assertFalse(self.空か(v), "配っている %s が空" % k)
        for c in d["counts_by_city"]:
            for k, v in c.items():
                if k in self.空でよい:
                    continue
                self.assertFalse(self.空か(v),
                                 "配っている升の %s が空" % k)


class 単位の語を手で書かない(unittest.TestCase):
    """**地図に色を塗る単位の名乗り。**

    「大阪府・兵庫県の 121 **区市町**」と手で書いていた。
    実測（2026-09-20）: 121 = 市59・区40・町21・**村1**（千早赤阪村）。
    村が1つだけの日でも、名乗りから落とすと「村は見ていない」と読める。

    **材料は、村を持つものと持たないものの両方でないと見分けられない。**
    村を含む材料しか渡さなければ、手で書いた「区市町村」でも通ってしまう。
    """

    def 単位(self, *まち):
        return [{"code": "%05d" % i, "pref": "大阪府", "city": c}
                for i, c in enumerate(まち)]

    def test_村があれば村と名乗る(self):
        self.assertEqual(
            make_index.unit_go(self.単位("豊中市", "北区", "岬町", "千早赤阪村")),
            "区市町村")

    def test_村が無ければ村と名乗らない(self):
        self.assertEqual(
            make_index.unit_go(self.単位("豊中市", "北区", "岬町")), "区市町")

    def test_知らない字が来たら黙って落とさない(self):
        語 = make_index.unit_go(self.単位("豊中市", "○○郡"))
        self.assertIn("市", 語)
        self.assertIn("郡", 語, "知らない字が名乗りから黙って消えている: " + 語)

    def test_実物の一覧にも村が入っている(self):
        """**3段目。作り終えた紙を読む。**"""
        p = os.path.join(make_index.HERE, "data", "jissuu-ritsu.md")
        if not os.path.exists(p):
            self.skipTest("jissuu-ritsu.md がまだ無い")
        with io.open(p, encoding="utf-8") as f:
            文 = f.read()
        語 = make_index.unit_go(make_index.map_units())
        self.assertIn("の %d %s）" % (len(make_index.map_units()), 語), 文,
                      "紙の名乗りが、いま数えている単位と合っていない")


if __name__ == "__main__":
    unittest.main()
