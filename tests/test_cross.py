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


if __name__ == "__main__":
    unittest.main()
