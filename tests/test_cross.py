#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跡地ファイルの条件を固定する。

ここは「よそのサイトに焼き付ける」データなので、いちど出すと引っ込めにくい。
入れる条件を1つでも緩めたらテストが落ちるようにしておく。

    python3 -m unittest discover -s tests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import make_cross  # noqa: E402


def 行(**kw):
    """条件をぜんぶ満たす行。テストごとに1つずつ崩して確かめる。"""
    row = {"system": "koyu", "key": "k1", "pref": "大阪府", "city": "大阪市北区",
           "address": "中津3丁目1番1号", "kind": "土地", "kind_raw": "工場",
           "zoning": "準工業地域", "area_sqm": 800, "status": "売却",
           "open_date": "2026-08-20", "last_seen": "2026-09-14",
           "sources": ["koyu-osaka-city"]}
    row.update(kw)
    return row


class 入れる条件(unittest.TestCase):

    def test_ぜんぶ満たせば入る(self):
        self.assertTrue(make_cross.is_atochi(行()))

    def test_種別は土地か土地建物だけ(self):
        self.assertTrue(make_cross.is_atochi(行(kind="土地建物")))
        for ng in ("マンション", "戸建て", "その他", ""):
            self.assertFalse(make_cross.is_atochi(行(kind=ng)), ng)

    def test_用途は事業用だけ(self):
        for ok in ("工場", "倉庫", "店舗", "事務所", "ホテル", "旅館",
                   "病院", "診療所"):
            self.assertTrue(make_cross.is_atochi(行(kind_raw=ok)), ok)
        for ng in ("農地", "山林", ""):
            self.assertFalse(make_cross.is_atochi(行(kind_raw=ng)), ng)

    def test_用途地域は工業系か商業系だけ(self):
        for ok in ("工業地域", "準工業地域", "工業専用地域",
                   "商業地域", "近隣商業地域"):
            self.assertTrue(make_cross.is_atochi(行(zoning=ok)), ok)
        for ng in ("第一種低層住居専用地域", "第二種中高層住居専用地域", ""):
            self.assertFalse(make_cross.is_atochi(行(zoning=ng)), ng)

    def test_面積は500平米以上(self):
        # 500平米に理屈がある。大阪・兵庫の都市部で開発許可が要るのがここから
        self.assertEqual(make_cross.DEFAULT_SQM, 500)
        self.assertTrue(make_cross.is_atochi(行(area_sqm=500)))
        self.assertFalse(make_cross.is_atochi(行(area_sqm=499)))
        self.assertFalse(make_cross.is_atochi(行(area_sqm=None)))

    def test_市町村ごとに下限を下げられる(self):
        # 条例で300平米に下げている市があれば、そちらに合わせる
        make_cross.CITY_SQM["27127"] = 300
        try:
            self.assertTrue(make_cross.is_atochi(行(area_sqm=300)))
            self.assertFalse(make_cross.is_atochi(行(area_sqm=299)))
        finally:
            del make_cross.CITY_SQM["27127"]

    def test_売却済みだけ(self):
        for ok in ("売却", "落札", "売却済", "契約済"):
            self.assertTrue(make_cross.is_atochi(行(status=ok)), ok)
        for ng in ("入札中", "予定", "公告", "受付中", "不売", "取下げ"):
            self.assertFalse(make_cross.is_atochi(行(status=ng)), ng)

    def test_住まいは名指しで落とす(self):
        for ng in ("居宅", "共同住宅", "アパート", "マンション", "寄宿舎",
                   "長屋", "住宅"):
            self.assertFalse(make_cross.is_atochi(行(kind_raw=ng)), ng)

    def test_事業用と住まいが混じっていたら落とす(self):
        # 「店舗兼住宅」は人が住んでいる。落とすほうを採る
        self.assertFalse(make_cross.is_atochi(行(kind_raw="店舗兼住宅")))
        self.assertFalse(make_cross.is_atochi(
            行(kind_raw="工場", former_use="社員寄宿舎")))

    def test_種別がマンションや区分所有なら落とす(self):
        for ng in ("マンション", "区分所有"):
            self.assertFalse(make_cross.is_atochi(行(kind=ng)), ng)

    def test_住居系の用途地域は落とす(self):
        for ng in ("第一種低層住居専用地域", "第二種中高層住居専用地域",
                   "第一種住居地域", "準住居地域", "田園住居地域"):
            self.assertFalse(make_cross.is_atochi(行(zoning=ng)), ng)

    def test_町丁目が無ければ入らない(self):
        # 競売・公売は市区町村までしか持っていないので、ここで自然に外れる
        self.assertFalse(make_cross.is_atochi(行(address="")))
        self.assertFalse(make_cross.is_atochi(
            行(system="keibai", address="", city="大阪市北区")))


class 出す中身(unittest.TestCase):

    def setUp(self):
        self.out = make_cross.build([行(), 行(kind="マンション")])
        self.rec = self.out["records"][0]

    def test_条件に合う1件だけ出る(self):
        self.assertEqual(len(self.out["records"]), 1)

    def test_決めた項目がそろっている(self):
        need = ("id", "kind", "date", "city_code", "city", "addr",
                "addr_key_town", "use", "area_sqm", "url", "source_url",
                "fetched_on")
        for k in need:
            self.assertIn(k, self.rec)

    def test_所有者名は出さない(self):
        self.assertNotIn("party", self.rec)

    def test_住所は町丁目まで_地番は出さない(self):
        # 表示用なので市区町村から書く。番地は落とす。
        # **丁目は落とさない**（正本 4節「丁目は必ず含める」）。
        # 元は「中津3丁目1番1号」なので、町丁目は「中津3」。
        # 「中津」まで丸めると、中津1〜5丁目が1つに混ざる
        self.assertEqual(self.rec["addr"], "大阪市北区中津3")
        self.assertEqual(self.rec["addr_key_town"], "27127|中津3")
        self.assertNotIn("3-1-1", repr(self.rec))
        self.assertNotIn("1番1号", repr(self.rec))

    def test_細かいほうの鍵は出さない(self):
        self.assertNotIn("addr_key", self.rec)


class 競売と公売は跡地に渡さない(unittest.TestCase):
    """DESIGN 1章の決定と正本 3.1。

    工業地域の工場でも、競売・公売の物件なら渡さない。
    跡地ファイルは1件1行なので、段（system）のふるいが無いと、
    競売の物件が個票として姉妹サイトへ出ていく。
    """

    def 行(self, **kw):
        r = {"system": "koyu", "key": "k", "pref": "大阪府",
             "city": "大阪市北区", "address": "中津3丁目1番1号",
             "kind": "土地", "kind_raw": "工場", "zoning": "準工業地域",
             "area_sqm": 2000, "status": "売却", "open_date": "2026-08-20",
             "sources": ["x"]}
        r.update(kw)
        return r

    def test_公有と国有は渡す(self):
        for system in ("koyu", "kokuyu"):
            self.assertTrue(make_cross.is_atochi(self.行(system=system)), system)

    def test_競売と公売は渡さない(self):
        for system in ("keibai", "kobai"):
            self.assertFalse(make_cross.is_atochi(self.行(system=system)), system)

    def test_渡さないものは記録にも出ない(self):
        out = make_cross.build([self.行(system="keibai")])
        self.assertEqual(out["records"], [])


class 規約の確認が済むまで止める(unittest.TestCase):

    def test_既定では止まっている(self):
        # 環境変数 ATOCHI を付けない限り、ファイルを書かない
        self.assertFalse(make_cross.ENABLED)


class 語を2か所に持たない(unittest.TestCase):
    """**数えるのは1か所だけ**（正本 9節）。

    前は `make_cross.py` に `SOLD` の並びを書き写していた。
    `aggregate.SOLD` に語を1つ足しても跡地には効かない形だった。
    **語彙が2か所にあると、必ず片方が古くなる。**
    """

    def test_売却の語はaggregateのものを使う(self):
        import aggregate
        self.assertIs(make_cross.SOLD, aggregate.SOLD,
                      "make_cross が SOLD を写し持っている")


class 紙の表が効いていないことを紙に書く(unittest.TestCase):
    """**表に書いた数字が、実際の下限を決めていなかった**（2026-09-20）。

    `common/kaihatsu_kibo.json` の `areas` は偵察レポートに表として出るが、
    下限を決めているのは `default_sqm` と `city_overrides` だけ。
    実測: 姫路市（播磨）は表では 1,000㎡ なのに、実際は 500㎡ で拾っている。
    600㎡の土地が跡地に入る。

    **一覧を推測で作らない。** かわりに、**効いていない行をそう名乗る。**
    """

    def test_表に無い市町村は既定値で拾う(self):
        self.assertEqual(make_cross.min_sqm("28201"), make_cross.DEFAULT_SQM)

    def test_表の広さは下限を動かさない(self):
        import json
        p = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "common", "kaihatsu_kibo.json")
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        ちがう = [a for a in d["areas"] if a["sqm"] != d["default_sqm"]]
        self.assertTrue(
            ちがう,
            "表の広さが全部 default_sqm と同じになった。"
            "**それなら『効いていない』という名乗りは要らないので、"
            "kibo.py の列ごと外すこと**（要らない名乗りを残さない）")
        for a in ちがう:
            self.assertEqual(
                make_cross.min_sqm(""), d["default_sqm"],
                "%s %s は表で %d㎡ なのに、コードは %d㎡ で拾っている。"
                "効いていないなら、紙にそう書くこと"
                % (a["pref"], a["範囲"], a["sqm"], make_cross.min_sqm("")))

    def test_効いていない行が偵察レポートに名指しで出ている(self):
        """**3段目。作り終えた紙を読む。**"""
        import io as _io
        import json
        ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        p = os.path.join(ROOT, "data", "recon-report.md")
        if not os.path.exists(p):
            self.skipTest("偵察レポートがまだ無い")
        with _io.open(p, encoding="utf-8") as f:
            文 = f.read()
        if "開発許可が要る土地の広さ" not in 文:
            self.skipTest("その章がまだ無い")
        # 毎朝の最初の検査は、kibo.py が走る前に、前の日のレポートを読む。
        # 前の形の章なら、この日の kibo.py が書き直したあとの2回目の検査で見る
        if "いま効いているか" not in 文:
            self.skipTest("kibo.py がまだ今の形でレポートを書き直していない"
                          "（前の形の章。書き直したあとの検査で見る）")
        with open(os.path.join(ROOT, "common", "kaihatsu_kibo.json"),
                  encoding="utf-8") as f:
            d = json.load(f)
        n = sum(1 for a in d["areas"] if a["sqm"] != d["default_sqm"])
        self.assertIn("表の広さと、いま効いている下限が違う範囲: %d 件" % n, 文,
                      "効いていない範囲の数が紙に出ていない")


if __name__ == "__main__":
    unittest.main()
