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

from common import addr  # noqa: E402  内側（_clean）を見る検査があるため
from common.addr import city_code, kanji_to_int, normalize, to_city  # noqa: E402


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
        # 共通仕様 4節のテスト例。大字と全角空白が消えて、番地までの鍵が出ること
        r = normalize("兵庫県", "西宮市", "大字上ケ原　二番町3-5")
        self.assertEqual(r["addr"], "西宮市上ケ原2番町3-5")
        self.assertEqual(r["addr_key"], "28204|上ケ原2番町3-5")
        # 町丁目までの鍵は、正本では「②の町丁目一覧で決まる。
        # **一覧が無いうちは空文字にして記録する（③）**」。このサイトに一覧は無い。
        # 3-5 の 3 が丁目の略記でないとは、文字だけでは言えない（2026-09-26）
        self.assertEqual(r["town"], "")
        self.assertEqual(r["addr_key_town"], "")

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


class 番地落としは番地の印があるときだけ(unittest.TestCase):
    """2026-09-26・統括判断。

    「丁目」の無い住所では、町名のあとの数字を番地として落として町名を決めていた。
    ところが「X3-5」「X3-5-1」の 3 は、**丁目の略記かもしれない**（住居表示の
    3丁目5番1号）。落とすと、3丁目の記録を丁目の無い粗い「X」に丸めてしまう。

    だから、町名のすぐあとが「N番地」「N番」と**書かれているときだけ**決める。
    印が無ければ決めない（未決）。町名を新しく推し量ることはしない。
    """

    def 町丁目(self, 住所):
        return normalize("大阪府", "大阪市北区", 住所)

    def test_番地と書いてあれば決める(self):
        for 住所 in ("角田町3番25号", "角田町3番地25", "角田町 3 番地",
                     "角田町三番二十五号", "角田町３番２５号",
                     "大阪市北区角田町3番25号", "大阪府大阪市北区角田町3番25号",
                     "大阪市北区－角田町3番25号",
                     "角田町3番25号 グランフロント大阪"):
            with self.subTest(住所=住所):
                r = self.町丁目(住所)
                self.assertEqual(r["town"], "角田町")
                self.assertEqual(r["addr_key_town"], "27127|角田町")

    def test_ハイフンだけなら決めない(self):
        for 住所 in ("角田町3-25", "角田町3-5-1", "角田町3－5－1", "角田町3",
                     "角田町3-25 グランフロント大阪"):
            with self.subTest(住所=住所):
                r = self.町丁目(住所)
                self.assertEqual(r["town"], "")
                self.assertEqual(r["addr_key_town"], "")

    def test_決めなくても番地までの鍵は変わらない(self):
        # 変えるのは町丁目の側だけ。番地までの鍵は、前と同じに出る
        self.assertEqual(self.町丁目("角田町3-25")["addr_key"], "27127|角田町3-25")
        self.assertEqual(self.町丁目("角田町3-5-1")["addr_key"], "27127|角田町3-5-1")

    def test_町名の中の番は番地の印にしない(self):
        # 「七番町」の番は町名。そのあとに番地の印があれば決める、無ければ決めない
        self.assertEqual(normalize("兵庫県", "西宮市", "甲子園七番町1番2号")["town"], "甲子園7番町")
        self.assertEqual(normalize("兵庫県", "西宮市", "甲子園7番町1-2")["town"], "")

    def test_丁目と町名だけの住所は変わらない(self):
        self.assertEqual(self.町丁目("梅田1丁目1番1号")["town"], "梅田1")
        self.assertEqual(self.町丁目("梅田1丁目1-1")["town"], "梅田1")
        self.assertEqual(self.町丁目("梅田")["town"], "梅田")
        self.assertEqual(normalize("兵庫県", "豊岡市", "城崎町湯島")["town"], "城崎町湯島")


class 空白が挟まっても同じ鍵になる(unittest.TestCase):
    """**空白の落とし方が遅れていた**（2026-09-19）。

    前は「丁目・番地・番・号をハイフンにする」4本より**後ろ**で空白を
    落としていた。すると空白が挟まった住所で4本が1本も当たらない。

        空白なし  梅田1丁目1番1号  → 町丁目 梅田1
        空白あり  梅田 1 丁目…     → 町丁目 **梅田1丁目**

    同じ場所が2つの鍵に割れて、姉妹サイトとつながらない。
    しかも `梅田1丁目` という形は町丁目の一覧には無いので、
    **あとから当て直すこともできない。**
    """

    def 町丁目(self, 住所):
        return addr.normalize("大阪府", "大阪市北区", 住所)

    def test_半角の空白が挟まっても同じ(self):
        a = self.町丁目("梅田1丁目1番1号")
        b = self.町丁目("梅田 1 丁目 1 番 1 号")
        self.assertEqual(a["town"], "梅田1")
        self.assertEqual(b["town"], a["town"])
        self.assertEqual(b["addr_key_town"], a["addr_key_town"])
        self.assertEqual(b["addr_key"], a["addr_key"])

    def test_全角の空白と漢数字が混ざっても同じ(self):
        """**空白を「一」と「丁目」のあいだに置く。**

        `梅田　一丁目` のように漢数字の手前に置いた形だと、
        漢数字を直す規則の先読み `(?=丁目)` がそのまま当たって①が通る。
        **直しを外しても鳴らない。** 鳴る位置に置いてある。
        """
        a = self.町丁目("梅田1丁目1番1号")
        b = self.町丁目("梅田　一　丁目　1番1号")
        self.assertEqual(b["town"], a["town"])
        self.assertEqual(b["addr_key_town"], a["addr_key_town"])

    def test_丁目の字が町丁目に残らない(self):
        """`梅田1丁目` の形で出ると、町丁目の一覧のどれとも当たらない。"""
        for 住所 in ("梅田 1 丁目 1 番 1 号", "梅田　一　丁目　1番1号"):
            self.assertNotIn("丁目", self.町丁目(住所)["town"], 住所)

    def test_号のうしろの建物名を番地の続きにしない(self):
        """空白を先に落としても、ここは前と同じであること。"""
        self.assertEqual(addr._clean("1号 グランフロント大阪"),
                         "1グランフロント大阪")


class 収集先の市を住所に被せない(unittest.TestCase):
    """正本 4節（2026-09-19）。

    姉妹サイト（開発系）が実物で踏んだ。大阪市の一覧に他県の土地が入っていて、
    456件中454件が切れ、残り2件を呼ぶ側の市で埋めていた。
    **2件を埋めるために454件を汚さない。**

    **被せると、形は正しいので検査を通るのに、この世に無い住所ができる。**
    """

    def test_住所が別の市を名乗るなら空にする(self):
        a = normalize("大阪府", "大阪市北区", "兵庫県西宮市甲子園町1-1")
        self.assertEqual((a["pref"], a["city"], a["city_code"]), ("", "", ""))
        self.assertNotIn("大阪市北区", a["addr"],
                         "この世に無い住所ができている: %r" % a["addr"])
        self.assertEqual(a["addr_key"], "", "食い違ったまま鍵を作っている")

    def test_合っていれば今までどおり(self):
        a = normalize("兵庫県", "西宮市", "兵庫県西宮市甲子園町1-1")
        self.assertEqual((a["city"], a["city_code"]), ("西宮市", "28204"))
        self.assertEqual(a["addr"], "西宮市甲子園町1-1")

    def test_住所から市が読めなければ呼ぶ側を使う(self):
        """**これは被せではない。**

        公売の表のように「見出しに市、欄に番地」という正しい分かれ方がある。
        そこまで拒むと、読めるものまで捨てる。
        """
        a = normalize("兵庫県", "西宮市", "甲子園町1-1")
        self.assertEqual((a["city"], a["city_code"]), ("西宮市", "28204"))

    def test_to_cityは読めなければ空を返す(self):
        """**推測で埋めない**（正本 4節③）。"""
        for t in ("所在地不明", "", "〇〇県××町1-1", "番地不詳"):
            self.assertEqual(to_city(t), ("", ""), repr(t))

    def test_to_cityは長いほうを採る(self):
        """政令市は区まで。「大阪市」で止めない。"""
        self.assertEqual(to_city("大阪市北区梅田1-1-1"),
                         ("大阪府", "大阪市北区"))


if __name__ == "__main__":
    unittest.main()
