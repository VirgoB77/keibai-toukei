#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""親と内訳のまとまりの登録表（common/shukei.py）。

正本 3.2「合計の升と、内訳の升を、両方出さない」を守らせる仕組み。
**サイト固有のものは入っていない**ので、4サイトで同じ中身にできる。

    python3 -m unittest discover -s tests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.shukei import Families, must_hide_parent, yoyuu  # noqa: E402

競売 = Families(("結果", "結果-落札", "結果-不調"),
                ("公告", "公告-新規", "公告-再公告"))


class 登録表(unittest.TestCase):

    def test_親と子を引ける(self):
        self.assertEqual(競売.parents, ("結果", "公告"))
        self.assertEqual(競売.children,
                         ("結果-落札", "結果-不調", "公告-新規", "公告-再公告"))

    def test_段階からまとまりを引ける(self):
        self.assertEqual(競売.family_of("結果-不調"),
                         ("結果", "結果-落札", "結果-不調"))
        self.assertEqual(競売.family_of("結果"),
                         ("結果", "結果-落札", "結果-不調"))
        self.assertIsNone(競売.family_of("取下げ"))

    def test_親かどうかを引ける(self):
        self.assertTrue(競売.is_parent("公告"))
        self.assertFalse(競売.is_parent("公告-新規"))
        self.assertFalse(競売.is_parent("取下げ"))


class 書き忘れを拾う(unittest.TestCase):
    """**規則を文章で書くと忘れられる。登録表にすると、書き忘れが拾える。**"""

    def test_登録していない内訳を拾う(self):
        # 「土地のうち農地」を足して登録を忘れた、という場面
        self.assertEqual(競売.undeclared(["結果-落札", "土地-農地", "土地"]),
                         ["土地-農地"])

    def test_登録してあれば拾わない(self):
        self.assertEqual(競売.undeclared(競売.children), [])

    def test_内訳でないものは拾わない(self):
        # 種別が互いに排他なら親子が無いので、登録も要らない
        self.assertEqual(競売.undeclared(["土地", "戸建て", "マンション"]), [])

    def test_子は親の名前で始まる形しか登録できない(self):
        with self.assertRaises(ValueError):
            Families(("土地", "戸建て"))          # 「土地-…」の形でない
        with self.assertRaises(ValueError):
            Families(("土地",))                   # 子がいない


class 兄弟をそろえる(unittest.TestCase):
    """親を消すだけでは足りない。兄弟をそろえるところまでが1組。"""

    def test_欠けている兄弟を教える(self):
        self.assertEqual(競売.missing_siblings(["結果-落札"]),
                         [("結果", ["結果-不調"])])

    def test_そろっていれば空(self):
        self.assertEqual(
            競売.missing_siblings(["結果-落札", "結果-不調"]), [])

    def test_まとまりが出ていなければ何も言わない(self):
        self.assertEqual(競売.missing_siblings(["取下げ"]), [])

    def test_欠けた兄弟を0で足す(self):
        # 鍵は (市区町村, 段階, 月)。段階は1番目
        buckets = {("27106", "結果-落札", "2026-09"): {"n": 3}}
        競売.fill_siblings(buckets, 1, lambda: {"n": 0})
        self.assertEqual(set(buckets), {
            ("27106", "結果-落札", "2026-09"),
            ("27106", "結果-不調", "2026-09"),
        })
        self.assertEqual(buckets[("27106", "結果-不調", "2026-09")], {"n": 0})

    def test_出ていないまとまりには足さない(self):
        # 何も起きていない月の升まで作ると、升が無駄に増える
        buckets = {("27106", "取下げ", "2026-09"): {"n": 1}}
        競売.fill_siblings(buckets, 1, lambda: {"n": 0})
        self.assertEqual(len(buckets), 1)

    def test_すでにある升は上書きしない(self):
        buckets = {("27106", "結果-落札", "2026-09"): {"n": 3},
                   ("27106", "結果-不調", "2026-09"): {"n": 7}}
        競売.fill_siblings(buckets, 1, lambda: {"n": 0})
        self.assertEqual(buckets[("27106", "結果-不調", "2026-09")]["n"], 7)


if __name__ == "__main__":
    unittest.main()


class 余裕(unittest.TestCase):
    """正本 3.2「「引き算で戻る升 0」だけでは足りない。余裕も出す」。

    戻る升を数えて0でも、いまのデータでぎりぎり成り立っているだけかもしれない。
    守っているのは伏せた升の**和**ではなく、「どの m 個が2件か」の組合せ。
    """

    def test_伏せた升が1つなら余裕0(self):
        # 和が分かった時点で確定する。いちばん危ない形
        self.assertEqual(yoyuu([1])["余裕"], 0)
        self.assertEqual(yoyuu([2])["余裕"], 0)
        self.assertEqual(yoyuu([1])["k"], 1)

    def test_全部1件でも余裕0(self):
        # k=3・m=0。「どれが2件か」の候補が1通りしかない
        d = yoyuu([1, 1, 1])
        self.assertEqual((d["k"], d["m"], d["余裕"], d["組合せ"]), (3, 0, 0, 1))

    def test_全部2件でも余裕0(self):
        d = yoyuu([2, 2, 2])
        self.assertEqual((d["k"], d["m"], d["余裕"], d["組合せ"]), (3, 3, 0, 1))

    def test_1と2が混ざると余裕が出る(self):
        d = yoyuu([1, 1, 2, 2])
        self.assertEqual((d["k"], d["m"], d["余裕"], d["組合せ"]), (4, 2, 2, 6))

    def test_伏せない升は数えない(self):
        # 3件以上は実数で出しているので、組合せに関係しない
        d = yoyuu([1, 2, 7, 11])
        self.assertEqual((d["k"], d["m"], d["和"]), (2, 1, 3))

    def test_0件は伏せていない(self):
        # 本当に0件の升は count 0 で出している。伏せた升ではない
        self.assertEqual(yoyuu([0, 0, 0])["k"], 0)

    def test_伏せる升が無ければ余裕0(self):
        self.assertEqual(yoyuu([5, 9])["k"], 0)
        self.assertEqual(yoyuu([])["k"], 0)

    def test_上限を変えられる(self):
        # 1〜3件を伏せるサイトなら small=3
        d = yoyuu([1, 2, 3], small=3)
        self.assertEqual((d["k"], d["m"], d["余裕"]), (3, 1, 1))


class 当てる組合せが1通り(unittest.TestCase):
    """正本 3.2「当てる組合せが1通りしかないまとまりは、親を出さない。例外なし」。

    `C(k, m) = 1` は「伏せた升がすべて確定する」という意味で、
    伏せていないのと同じ。**`k = 1` は常にこれに当たる。**
    しきい値はまだ無いので、それ以外は各サイトが出さない側に倒す。
    """

    def test_k1は常に当たる(self):
        self.assertTrue(must_hide_parent([1]))
        self.assertTrue(must_hide_parent([2]))
        self.assertTrue(must_hide_parent([1, 7, 11]))   # 伏せた升は1つだけ

    def test_全部同じ値なら当たる(self):
        self.assertTrue(must_hide_parent([1, 1, 1, 1]))   # m=0
        self.assertTrue(must_hide_parent([2, 2, 2, 2]))   # m=k

    def test_混ざれば当たらない(self):
        self.assertFalse(must_hide_parent([1, 2]))        # C(2,1)=2
        self.assertFalse(must_hide_parent([1, 1, 2]))     # C(3,1)=3

    def test_伏せる升が無ければ当たらない(self):
        # 隠すものが無いので、親を出しても戻るものが無い
        self.assertFalse(must_hide_parent([]))
        self.assertFalse(must_hide_parent([0, 0]))
        self.assertFalse(must_hide_parent([5, 9]))

    def test_kが増えると組合せが増える(self):
        # 正本の表と同じ数になること
        self.assertEqual(yoyuu([1, 2])["組合せ"], 2)
        self.assertEqual(yoyuu([1, 1, 2, 2])["組合せ"], 6)
        self.assertEqual(yoyuu([1] * 5 + [2] * 5)["組合せ"], 252)
        self.assertEqual(yoyuu([1] * 10 + [2] * 10)["組合せ"], 184756)
