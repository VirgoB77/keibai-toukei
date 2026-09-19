#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""共通住所モジュールの決まりを固定する。

3つのサイト（大型店日報・競売公売・開発届出）を住所で突き合わせるので、
ここが揺れると横断ページが作れない。書き方の違う同じ住所が、
同じ addr_key になることを確かめる。

    python3 -m unittest discover -s tests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.addr import city_code, kanji_to_int, normalize  # noqa: E402


class 市区町村コード(unittest.TestCase):

    def test_引ける(self):
        self.assertEqual(city_code("大阪府", "大阪市北区"), "27127")
        self.assertEqual(city_code("兵庫県", "西宮市"), "28204")
        self.assertEqual(city_code("兵庫県", "神戸市中央区"), "28110")
        self.assertEqual(city_code("大阪府", "堺市美原区"), "27147")

    def test_都道府県が無くても市名で1つに決まれば引ける(self):
        self.assertEqual(city_code("", "西宮市"), "28204")

    def test_決められないときは空文字(self):
        # 同じ名前の市が複数ある（府中市は東京都と広島県）ので決められない
        self.assertEqual(city_code("", "府中市"), "")
        self.assertEqual(city_code("大阪府", "存在しない市"), "")
        self.assertEqual(city_code("大阪府", ""), "")


class 漢数字(unittest.TestCase):

    def test_直せる(self):
        self.assertEqual(kanji_to_int("三"), 3)
        self.assertEqual(kanji_to_int("十"), 10)
        self.assertEqual(kanji_to_int("十一"), 11)
        self.assertEqual(kanji_to_int("二十三"), 23)
        self.assertEqual(kanji_to_int("百二十三"), 123)


class 住所をそろえる(unittest.TestCase):

    def test_丁目番号がハイフンになる(self):
        r = normalize("大阪府", "大阪市北区", "梅田一丁目1番1号")
        # addr は表示用。市区町村から書く（正本 4節）
        self.assertEqual(r["addr"], "大阪市北区梅田1-1-1")
        self.assertEqual(r["town"], "梅田1")     # 丁目を含む（正本 4節）
        self.assertEqual(r["city_code"], "27127")
        self.assertEqual(r["addr_key"], "27127|梅田1-1-1")

    def test_全角は半角になる(self):
        r = normalize("大阪府", "大阪市北区", "梅田１丁目１番１号")
        self.assertEqual(r["addr"], "大阪市北区梅田1-1-1")

    def test_書き方が違っても同じ鍵になる(self):
        書き方 = [
            "梅田一丁目1番1号",
            "梅田１丁目１番１号",
            "梅田 1丁目 1番 1号",
            "梅田1-1-1",
            "大阪府大阪市北区梅田1丁目1番1号",
            "大字梅田1丁目1番1号",
        ]
        keys = {normalize("大阪府", "大阪市北区", a)["addr_key"] for a in 書き方}
        self.assertEqual(keys, {"27127|梅田1-1-1"})

    def test_建物名は_addr_に残り_addr_keyからは落ちる(self):
        r = normalize("大阪府", "大阪市北区", "梅田1丁目1番1号 グランフロント大阪")
        self.assertEqual(r["addr"], "大阪市北区梅田1-1-1グランフロント大阪")
        self.assertEqual(r["addr_key"], "27127|梅田1-1-1")

    def test_部屋番号も_addr_keyからは落ちる(self):
        r = normalize("兵庫県", "西宮市", "甲子園町1番1号 ○○マンション101号室")
        self.assertEqual(r["addr_key"], "28204|甲子園町1-1")

    def test_町名の中の数字を壊さない(self):
        # 「七番町」は町の名前。ここで切ると別の場所になってしまう
        r = normalize("兵庫県", "西宮市", "甲子園七番町1番2号")
        self.assertEqual(r["addr"], "西宮市甲子園7番町1-2")
        self.assertEqual(r["town"], "甲子園7番町")
        self.assertEqual(r["addr_key"], "28204|甲子園7番町1-2")

    def test_番地が無い住所はそのまま(self):
        r = normalize("兵庫県", "豊岡市", "城崎町湯島")
        self.assertEqual(r["addr"], "豊岡市城崎町湯島")
        self.assertEqual(r["addr_key"], "28209|城崎町湯島")

    def test_地名の漢数字は直さない(self):
        # 「三田」を「3田」にしてしまうと、まったく別の地名になる
        r = normalize("兵庫県", "三田市", "三輪1丁目1番")
        self.assertEqual(r["addr"], "三田市三輪1-1")

    def test_町丁目までの粗い鍵も出す(self):
        r = normalize("大阪府", "大阪市北区", "梅田1丁目1番1号 グランフロント大阪")
        self.assertEqual(r["addr_key"], "27127|梅田1-1-1")
        # **丁目を含む**（正本 4節 338行「丁目は必ず含める」）。
        # 梅田は1〜3丁目あり、駅の北と南ほど違う場所になる。
        # 「梅田」でまとめると、3つの丁目が1つの升に混ざって意味をなさない
        self.assertEqual(r["addr_key_town"], "27127|梅田1")

    def test_丁目の数字と番地の数字を取り違えない(self):
        # どちらも「町名のあとの数字」で、正規化すると同じ形になる。
        # 「丁目」という語が元の住所にあったかどうかでしか決まらない（正本 4節 ①）
        丁目 = normalize("大阪府", "大阪市北区", "梅田1丁目1番1号")
        番地 = normalize("大阪府", "大阪市北区", "角田町3番25号")
        self.assertEqual(丁目["town"], "梅田1")      # 1 は丁目。町丁目の一部
        self.assertEqual(番地["town"], "角田町")     # 3 は番地。町丁目ではない

    def test_粗い鍵は町名の中の数字を残す(self):
        r = normalize("兵庫県", "西宮市", "甲子園七番町1番2号")
        self.assertEqual(r["addr_key"], "28204|甲子園7番町1-2")
        self.assertEqual(r["addr_key_town"], "28204|甲子園7番町")

    def test_番地が無ければ2本の鍵は同じになる(self):
        r = normalize("兵庫県", "豊岡市", "城崎町湯島")
        self.assertEqual(r["addr_key"], "28209|城崎町湯島")
        self.assertEqual(r["addr_key_town"], "28209|城崎町湯島")

    def test_丁目まで持つ側と町名しか持たない側は粗い鍵でも一致しない(self):
        # 精度が違っても粗い鍵なら突き合わせられる——が、**丁目より上では揃わない**。
        # 「梅田1丁目」と、丁目を知らない「梅田」は、同じ場所とは言えない。
        # ここを一致させると、梅田1丁目の記録が2丁目・3丁目と混ざる（正本 4節 338-343行）。
        # 揃わないほうが正しい。つながらなかったことが分かるだけで済む
        細かい = normalize("大阪府", "大阪市北区", "梅田1丁目1番1号")
        粗い = normalize("大阪府", "大阪市北区", "梅田")
        self.assertNotEqual(細かい["addr_key"], 粗い["addr_key"])
        self.assertEqual(細かい["addr_key_town"], "27127|梅田1")
        self.assertEqual(粗い["addr_key_town"], "27127|梅田")
        self.assertNotEqual(細かい["addr_key_town"], 粗い["addr_key_town"])

    def test_正本が出している例が通る(self):
        # 共通仕様 4節のテスト例。大字と全角空白が消えて、鍵が両方出ること
        r = normalize("兵庫県", "西宮市", "大字上ケ原　二番町3-5")
        self.assertEqual(r["addr"], "西宮市上ケ原2番町3-5")
        self.assertEqual(r["addr_key"], "28204|上ケ原2番町3-5")
        self.assertEqual(r["addr_key_town"], "28204|上ケ原2番町")

    def test_コードが引けなければ鍵は空文字(self):
        # 突き合わせに使えない鍵を作るより、空にして後で人が見るほうがよい
        r = normalize("", "府中市", "宮西町1-1")
        self.assertEqual(r["city_code"], "")
        self.assertEqual(r["addr_key"], "")
        self.assertEqual(r["addr_key_town"], "")

    def test_住所が空でも落ちない(self):
        r = normalize("大阪府", "大阪市北区", "")
        self.assertEqual(r["addr"], "大阪市北区")
        self.assertEqual(r["town"], "")
        self.assertEqual(r["addr_key"], "")
        self.assertEqual(r["addr_key_town"], "")
        self.assertEqual(r["city_code"], "27127")


if __name__ == "__main__":
    unittest.main()
