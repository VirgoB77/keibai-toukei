#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""index.json に「出してはいけないもの」が出ないことを固定する。

ここが緩むと、個人名義の居宅が住所つきで一覧に並ぶ。
いちばん壊してはいけない壁なので、テストで縛る。

    python3 -m unittest discover -s tests
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
        self.assertEqual(n["競売/公告-新規"], 4)
        self.assertEqual(n["競売/公告-再公告"], 0)


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
        # 公告-新規は公告の内数で、並べると「公告7＋新規7＝14」と読める
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
        self.assertEqual(n["競売/公告-新規"] + n["競売/公告-再公告"], 7)
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
        # 公告 ＝ 公告-新規 ＋ 公告-再公告。再公告の升を出していなかったころは、
        # 公告6 − 公告-新規5 ＝ 1 で再公告が1件だと分かってしまった
        rows = [self.行(i, "売却") for i in range(5)]
        rows += [dict(self.行(5, "売却"), re_notice=True)]
        cb = make_index.build(rows)["counts_by_city"]
        kinds = {c["kind"]: c["count_label"] for c in cb}
        self.assertIn("競売/公告-新規", kinds)
        self.assertIn("競売/公告-再公告", kinds)
        self.assertNotIn("競売/公告", kinds)     # 親は出さない
        self.assertEqual(kinds["競売/公告-再公告"], "1-2")

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

        {"kind": "競売/公告-新規",   "count": null, "count_label": "1-2"}
        {"kind": "競売/公告-再公告", "count": 0,    "count_label": "0"}
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
        self.assertEqual(got, {"競売/公告-新規": (None, "1-2"),
                               "競売/公告-再公告": (0, "0")})

    def test_決まり1_合計の升を出さない(self):
        rows = [self.行(i) for i in range(5)]
        kinds = {c["kind"] for c in make_index.build(rows)["counts_by_city"]}
        self.assertNotIn("競売/公告", kinds)
        self.assertNotIn("競売/結果", kinds)

    def test_決まり2_内訳を1つも欠けさせない(self):
        rows = [self.行(i) for i in range(5)]
        cb = make_index.build(rows)["counts_by_city"]
        kinds = {c["kind"] for c in cb}
        self.assertIn("競売/公告-新規", kinds)
        self.assertIn("競売/公告-再公告", kinds)
        self.assertIn("競売/落札", kinds)
        self.assertIn("競売/不調", kinds)

    def test_決まり3_0件の内訳は0と書く(self):
        # 伏せた升（null）と本当に0件の升（0）を見た目で分ける
        rows = [self.行(i) for i in range(5)]
        cb = make_index.build(rows)["counts_by_city"]
        n = {c["kind"]: (c["count"], c["count_label"]) for c in cb}
        self.assertEqual(n["競売/公告-再公告"], (0, "0"))
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
        self.assertEqual(n["競売/公告-新規"] + n["競売/公告-再公告"], 5)

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


if __name__ == "__main__":
    unittest.main()
