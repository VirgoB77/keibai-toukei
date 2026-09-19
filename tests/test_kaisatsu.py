#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""開札の回の集計が、出してはいけない形にならないことを固定する。

この層は物件も住所も当事者も含まないので個人情報の心配は無いが、
**市区町村を推定で付けない**ことと、**並べ替えて順位にしない**ことは守る。

    python3 -m unittest discover -s tests
"""

import json
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import kaisatsu  # noqa: E402


def 回(court_id="33111", open_date="2026-10-06", farmland=False, **kw):
    r = {"court_id": court_id, "open_date": open_date, "farmland": farmland,
         "disposal_date": "2026-08-19", "notice_date": "2026-09-07",
         "view_start": "2026-09-07", "bid_start": "2026-09-24",
         "bid_end": "2026-09-30", "decision_date": "2026-10-27",
         "confirm_date": "2026-11-05", "status": ""}
    r.update(kw)
    return r


class 市区町村を推定で付けない(unittest.TestCase):
    """開札の回は裁判所の予定。神戸地裁本庁の管轄だけで市区町村は15以上ある。

    1市に割り当てれば嘘になり、管轄の全市に配れば同じ1回を15回数えることになる。
    """

    def test_city_codeという欄を持たない(self):
        out = kaisatsu.build([回(), 回(farmland=True)],
                             {"33111": "大阪地方裁判所 本庁"}, date(2026, 9, 16))

        def 欄(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    yield k
                    for x in 欄(v):
                        yield x
            elif isinstance(o, list):
                for v in o:
                    for x in 欄(v):
                        yield x

        self.assertNotIn("city_code", list(欄(out)))

    def test_市区町村コードらしき値が値に入らない(self):
        # 27127（大阪市北区）のような5桁が混ざっていたら、推定で付けている
        import re
        out = kaisatsu.build([回(), 回(farmland=True)],
                             {"33111": "大阪地方裁判所 本庁"}, date(2026, 9, 16))

        def 値(o):
            if isinstance(o, dict):
                for v in o.values():
                    for x in 値(v):
                        yield x
            elif isinstance(o, list):
                for v in o:
                    for x in 値(v):
                        yield x
            elif isinstance(o, str):
                yield o

        for v in 値(out):
            if v in ("33111", "33131", "33141", "33311", "33331", "33332"):
                continue                      # これは裁判所の番号
            self.assertIsNone(re.fullmatch(r"\d{5}", v), v)

    def test_都道府県までは名前で決める(self):
        out = kaisatsu.build([回(court_id="33311")],
                             {"33311": "神戸地方裁判所 本庁"}, date(2026, 9, 16))
        self.assertEqual(out["裁判所"][0]["pref"], "兵庫県")


class 並べ替えて順位にしない(unittest.TestCase):
    """件数順に並べ替えるのは順位そのもの（正本 3.3）。"""

    def test_裁判所はcourt_idの昇順(self):
        rows = [回(court_id="33311") for _ in range(5)] + [回(court_id="33111")]
        out = kaisatsu.build(rows, {"33311": "神戸", "33111": "大阪"},
                             date(2026, 9, 16))
        self.assertEqual([c["court_id"] for c in out["裁判所"]],
                         ["33111", "33311"])


class 小さい母数(unittest.TestCase):

    def test_1件と2件は実数を出さない(self):
        out = kaisatsu.build([回(), 回(open_date="2026-11-10")],
                             {"33111": "大阪"}, date(2026, 9, 16))
        for cell in out["庁×月"]:
            self.assertIsNone(cell["count"])
            self.assertEqual(cell["count_label"], "1-2")

    def test_3件以上は実数を出す(self):
        rows = [回(case=i) for i in range(3)]
        out = kaisatsu.build(rows, {"33111": "大阪"}, date(2026, 9, 16))
        cell = out["庁×月"][0]
        self.assertEqual(cell["count"], 3)
        self.assertEqual(cell["count_label"], "3")

    def test_元が3件未満なら中央値を出さない(self):
        out = kaisatsu.build([回(), 回()], {"33111": "大阪"}, date(2026, 9, 16))
        self.assertIsNone(out["日数"]["公告→開札"]["全体"]["中央値"])

    def test_3件以上なら中央値を出す(self):
        rows = [回(case=i) for i in range(3)]
        out = kaisatsu.build(rows, {"33111": "大阪"}, date(2026, 9, 16))
        self.assertEqual(out["日数"]["公告→開札"]["全体"]["中央値"], 29)


class 伏せるのは升だけで粗さは伏せない(unittest.TestCase):
    """このファイルの中では、粗いほうの数を伏せない（kaisatsu.py の説明）。

    **2026-09-17 まで、伏せたつもりの数が同じファイルの中で戻っていた。**
    合計.公告まで進んだ回 = null の2行下に どこまで進んだか.公告日が来た回 = 26、
    合計.一般の回 = null なのに 日数[*].一般の回.n = 80。
    言い換えを1つずつ塞ごうとしても塞ぎきれない。同じ回を5つの粗さで
    数えているので、粗いほうを伏せても細かいほうを足せば戻る。

    だから中で伏せるのをやめ、守るのは置き場所（data/public/ だけが公開用）にした。
    **升1つ1つの 1〜2件 はいままでどおり伏せる。** そちらは粗さの話ではなく
    升の話なので、どの粗さを選んでも効き続ける。

    正本 3.2 の決まり1 と食い違うので、正本 11節に従って報告してある。
    """

    def test_裁判所ごとの件数も伏せる(self):
        # 升の話。前は生の件数をそのまま出していたので、1件・2件の庁が読めた
        rows = [回(court_id="33111")] + [回(court_id="33311", case=i)
                                         for i in range(5)]
        out = kaisatsu.build(rows, {"33111": "大阪", "33311": "神戸"},
                             date(2026, 9, 16))
        osaka = [c for c in out["裁判所"] if c["court_id"] == "33111"][0]
        self.assertIsNone(osaka["回"])
        self.assertEqual(osaka["回_label"], "1-2")

    def test_粗いほうは伏せない(self):
        rows = [回(court_id="33111", farmland=True)]
        rows += [回(court_id="33311", farmland=True, case=i) for i in range(5)]
        out = kaisatsu.build(rows, {"33111": "大阪", "33311": "神戸"},
                             date(2026, 9, 16))
        self.assertEqual(out["合計"]["農地専用の回"], 6)

    def test_伏せても細かいほうを足せば戻ることを確かめておく(self):
        """**伏せない理由そのもの。** 戻らなくなったら、判断を見直すこと。"""
        rows = [回(court_id="33311", case=i) for i in range(3)]
        rows += [回(court_id="33311", farmland=True, case=100 + i)
                 for i in range(4)]
        out = kaisatsu.build(rows, {"33311": "神戸"}, date(2026, 9, 16))
        # 府県×月×農地（細かいほう）を足すと 府県×月（粗いほう）に一致する
        kids = [c for c in out["府県×月×農地"] if c["升"][0] == "兵庫県"]
        parent = [c for c in out["府県×月"] if c["升"][0] == "兵庫県"]
        self.assertEqual(sum(c["count"] for c in kids), 7)
        self.assertEqual(sum(c["count"] for c in parent), 7)
        # 裁判所の内訳も、合計と一致する
        self.assertEqual(
            sum(c["うち一般"] for c in out["裁判所"]), out["合計"]["一般の回"])
        self.assertEqual(
            sum(c["うち農地専用"] for c in out["裁判所"]),
            out["合計"]["農地専用の回"])

    def test_言い換えが実数と食い違わない(self):
        """同じ回を2か所で数えている場所は、同じ数でなければならない。

        片方だけ伏せて、もう片方が実数、という状態を作らないための見張り。
        """
        rows = [回(court_id="33311", notice_date="2026-08-01", case=i)
                for i in range(3)]
        out = kaisatsu.build(rows, {"33311": "神戸"}, date(2026, 9, 16))
        self.assertEqual(out["合計"]["公告まで進んだ回"],
                         out["どこまで進んだか"]["公告日が来た回"])
        self.assertEqual(out["合計"]["一般の回"],
                         out["日数"]["公告→開札"]["一般の回"]["n"])
        self.assertEqual(out["合計"]["農地専用の回"],
                         out["日数"]["公告→開札"]["農地専用の回"]["n"])
        self.assertEqual(out["合計"]["回"],
                         out["合計"]["一般の回"] + out["合計"]["農地専用の回"])
        self.assertEqual(out["合計"]["回"],
                         out["合計"]["公告まで進んだ回"]
                         + out["合計"]["まだ公告前の回"])

    def test_公開しないと書いてある(self):
        out = kaisatsu.build([回()], {"33111": "大阪"}, date(2026, 9, 16))
        self.assertIn("公開しない", out)
        self.assertIn("data/public/", out["公開しない"])
        self.assertIn("5つの粗さ", out["粗さについて"])


class 日数は予定であって実績ではない(unittest.TestCase):

    def test_どこまで進んだかを出す(self):
        rows = [回(notice_date="2026-08-01", open_date="2026-08-20",
                   bid_start="2026-08-10", bid_end="2026-08-15",
                   decision_date="2027-01-01", confirm_date="2027-02-01")]
        out = kaisatsu.build(rows, {"33111": "大阪"}, date(2026, 9, 16))
        d = out["どこまで進んだか"]
        self.assertEqual(d["公告日が来た回"], 1)
        self.assertEqual(d["開札日が過ぎた回"], 1)
        self.assertEqual(d["確定日が過ぎた回"], 0)   # まだ先

    def test_予定であることを書いてある(self):
        out = kaisatsu.build([回()], {"33111": "大阪"}, date(2026, 9, 16))
        self.assertIn("間隔", out["日数について"])
        self.assertIn("実績ではない", out["日数について"])


class 言い方(unittest.TestCase):

    def test_農地ではなく農地専用の回と書く(self):
        # BITの予定表に「★は農地専用のスケジュールです。ただし，それ以外の
        # スケジュールについても農地が含まれる場合があります」とある
        out = kaisatsu.build([回(farmland=True)], {"33111": "大阪"},
                             date(2026, 9, 16))
        self.assertIn("農地専用の回", out["合計"])
        self.assertIn("農地専用の回", out["日数"]["公告→開札"])
        self.assertIn("農地専用のスケジュール", out["農地について"])

    def test_数えているのは回であって物件ではない(self):
        out = kaisatsu.build([回()], {"33111": "大阪"}, date(2026, 9, 16))
        self.assertIn("回", out["数えているもの"])
        self.assertIn("物件の数ではない", out["数えているもの"])


class 状態の空を1つの意味にしない(unittest.TestCase):
    """「空」には公告前の予定枠と、読み取れなかったものが混ざりうる。

    歩留まりとして読むと分母が過大になる。公告日で分けて数える。
    """

    def test_公告前の回は状態の内訳に入れない(self):
        rows = [回(notice_date="2027-01-01", status=""),      # まだ公告前
                回(notice_date="2026-08-01", status="終了")]   # 公告ずみ
        out = kaisatsu.build(rows, {"33111": "大阪"}, date(2026, 9, 16))
        self.assertEqual(out["合計"]["公告まで進んだ回"], 1)
        self.assertEqual(out["合計"]["まだ公告前の回"], 1)
        self.assertEqual([c["升"][0] for c in out["状態"]], ["終了"])


if __name__ == "__main__":
    unittest.main()
