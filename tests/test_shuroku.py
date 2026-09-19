#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""どこまで見たか（shuroku.py）。

升は見たところにしか出ない。「升が無い」を「0件」と読んでよいかは、
升のほうを見ても分からない。ここが決める。

    python3 -m unittest discover -s tests
"""

import json
import os
import sys
import unittest

import kinko  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import shuroku  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class 状態は4つ(unittest.TestCase):
    """3つでは足りない。「見ていないが別の出どころで0と分かる」が要る。"""

    def setUp(self):
        with open(os.path.join(ROOT, "sources.json"), encoding="utf-8") as f:
            self.範囲 = shuroku.build(json.load(f)["sources"])

    def test_状態は決まった言い方だけ(self):
        言い方 = {"見た", "見ていないが0と言える", "見ていない"}
        for r in self.範囲:
            self.assertIn(r["状態"], 言い方, r)

    def test_見ていないが0と言えるものがある(self):
        kinko.need(self)
        # 堺支部・岸和田支部。予定表に回が無いので一覧は空になる
        zero = [r for r in self.範囲 if r["状態"] == "見ていないが0と言える"]
        self.assertTrue(zero)
        for r in zero:
            self.assertEqual(r["物件"], 0)

    def test_0にも出典がある(self):
        # **0 は記録が無いので出典を付けられない、ではない。**
        # 0 を証明した別の記録が source_url と fetched_on を持っている（正本 3.5）
        for r in self.範囲:
            if r["状態"] != "見ていないが0と言える":
                continue
            self.assertTrue(r["source_url"], r)
            self.assertTrue(r["fetched_on"], r)
            self.assertTrue(r["0の根拠"], r)

    def test_見たものにも出典がある(self):
        for r in self.範囲:
            if r["状態"] == "見た":
                self.assertTrue(r["source_url"], r)
                self.assertTrue(r["fetched_on"], r)

    def test_見ていないものは理由を書く(self):
        for r in self.範囲:
            if r["状態"] == "見ていない":
                self.assertTrue(r["なぜ"], r)


class 黙って落とさない(unittest.TestCase):
    """収録範囲そのものに穴を開けない。"""

    def test_番号が引けない裁判所も出す(self):
        # 豊岡支部は BIT の裁判所一覧に載っておらず court_id が無い。
        # 落とすと、収録範囲に穴が開いたまま気づけない
        with open(os.path.join(ROOT, "sources.json"), encoding="utf-8") as f:
            sources = json.load(f)["sources"]
        範囲 = shuroku.build(sources)
        全部 = {s["name"].replace("BIT 売却スケジュール ", "")
                for s in sources if s.get("kind") == "bit-schedule"}
        self.assertEqual({r["name"] for r in 範囲}, 全部)
        なし = [r for r in 範囲 if not r["id"]]
        self.assertTrue(なし)
        self.assertEqual(なし[0]["状態"], "見ていない")


class 嘘の精度を作らない(unittest.TestCase):
    """割り当てられないものは、割り当てない。"""

    def test_管轄は一次情報の書き方のまま(self):
        with open(os.path.join(ROOT, "sources.json"), encoding="utf-8") as f:
            範囲 = shuroku.build(json.load(f)["sources"])
        # 「南河内」「泉州」は市区町村コードに落ちない。落とさずそのまま持つ
        文 = " ".join(r.get("管轄", "") for r in 範囲)
        self.assertIn("南河内", 文)
        self.assertIn("泉州", 文)

    def test_市区町村コードを勝手に付けない(self):
        import re
        with open(os.path.join(ROOT, "sources.json"), encoding="utf-8") as f:
            範囲 = shuroku.build(json.load(f)["sources"])
        裁判所 = {"33111", "33131", "33141", "33311", "33331", "33332"}
        for r in 範囲:
            for k, v in r.items():
                if k == "id" or not isinstance(v, str):
                    continue
                if re.fullmatch(r"\d{5}", v) and v not in 裁判所:
                    self.fail("市区町村コードらしき値: %s=%r" % (k, v))

    def test_割り当ては空で理由が書いてある(self):
        path = os.path.join(ROOT, "data", "agg", "shuroku.json")
        if not os.path.exists(path):
            self.skipTest("まだ出力が無い")
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        self.assertEqual(doc["割り当て"], [])
        self.assertIn("推測で埋めてはいけない", doc["割り当てが空な理由"])


if __name__ == "__main__":
    unittest.main()
