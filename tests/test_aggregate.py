#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""集計の3つのガードを固定する。

小さい町では、件数が1件と分かるだけで物件が特定できてしまう。
ここが緩むと、個票を出していなくても同じことになる。

    python3 -m unittest discover -s tests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aggregate  # noqa: E402


def 行(**kw):
    row = {"system": "keibai", "pref": "兵庫県", "city": "西宮市",
           "city_code": "28204", "kind": "マンション", "open_date": "2026-09-24",
           "base_price": 10000000, "sale_price": 15000000, "status": "売却"}
    row.update(kw)
    return row


class ガード1_市区町村より下に下りない(unittest.TestCase):

    def test_升の項目は決まったものだけ(self):
        self.assertEqual(aggregate.BUCKET_FIELDS,
                         ("system", "pref", "city", "city_code", "kind",
                          "stage", "ym"))
        for ng in ("address", "addr", "addr_key", "town", "chome", "school"):
            self.assertNotIn(ng, aggregate.BUCKET_FIELDS)

    def test_町丁目があっても升には出てこない(self):
        cells = aggregate.aggregate([
            行(address="甲子園町1-1", addr_key="28204|甲子園町1-1"),
            行(address="甲子園七番町9-9"),
            行(address="上鳴尾町3-3"),
        ])
        # 3件が1つの升にまとまる。町名で分かれない
        kekka = [c for c in cells if c["stage"] == "結果"]
        self.assertEqual(len(kekka), 1)
        self.assertEqual(kekka[0]["count"], 3)
        text = repr(cells)
        for ng in ("甲子園", "上鳴尾", "28204|"):
            self.assertNotIn(ng, text)


class ガード2_月より細かくしない(unittest.TestCase):

    def test_日付は月に丸める(self):
        self.assertEqual(aggregate.to_month("2026-09-24"), "2026-09")
        self.assertEqual(aggregate.to_month("2026-09"), "2026-09")
        self.assertEqual(aggregate.to_month(""), "")

    def test_同じ月なら日がちがっても同じ升(self):
        cells = aggregate.aggregate([
            行(open_date="2026-09-01"),
            行(open_date="2026-09-15"),
            行(open_date="2026-09-30"),
        ])
        kekka = [c for c in cells if c["stage"] == "結果"]
        self.assertEqual(len(kekka), 1)
        self.assertEqual(kekka[0]["ym"], "2026-09")

    def test_月がちがえば別の升(self):
        cells = aggregate.aggregate([行(open_date="2026-09-01"),
                                     行(open_date="2026-10-01")])
        kekka = [c for c in cells if c["stage"] == "結果"]
        self.assertEqual(len(kekka), 2)


class ガード3_1件2件はぼかす(unittest.TestCase):

    def test_1件と2件はまとめて書く(self):
        self.assertEqual(aggregate.mask_count(1), "1-2")
        self.assertEqual(aggregate.mask_count(2), "1-2")

    def test_0件と3件以上はそのまま(self):
        self.assertEqual(aggregate.mask_count(0), 0)
        self.assertEqual(aggregate.mask_count(3), 3)
        self.assertEqual(aggregate.mask_count(40), 40)

    def test_小さい升は件数が実数で出ない(self):
        cells = aggregate.aggregate([行()])
        for c in cells:
            if c["count"] == 0:
                continue          # 兄弟の升の0件。伏せたのではなく本当に0
            self.assertIsNone(c["count"])
            self.assertEqual(c["count_label"], "1-2")

    def test_兄弟の升が欠けたら0で足す(self):
        # 出さないと「伏せた」のか「1件も無かった」のかが見分けられない（正本 3.2）
        cells = aggregate.aggregate([行(status="売却"), 行(status="売却"),
                                     行(status="売却")])
        n = {c["stage"]: (c["count"], c["count_label"]) for c in cells}
        self.assertEqual(n["結果-落札"], (3, "3"))
        self.assertEqual(n["結果-不調"], (0, "0"))   # 不売は1件も無かった

    def test_まとまりが出ていなければ兄弟も足さない(self):
        # 公告日が分からない行は公告の升に入らない。
        # 入っていないまとまりの兄弟まで 0 で作ると、無い月の升が増える
        cells = aggregate.aggregate([行(status="売却")])
        self.assertNotIn("公告-再公告", {c["stage"] for c in cells})

    def test_小さい升は実数を出さず_ラベルで見せる(self):
        cells = aggregate.aggregate([行(status="不売")])
        fubai = [c for c in cells if c["stage"] == "結果-不調"][0]
        self.assertIsNone(fubai["count"])
        self.assertEqual(fubai["count_label"], "1-2")


class 黙って捨てない(unittest.TestCase):
    """**升を作らずに記録する**（正本 9節・2026-09-19）。

    前は「不明」という段階を作って升に出していた。やめた。

    - `kind` に出すと、横断ハブで4サイトの「不明」が1つの塊になる。
      競売の不明は「どの段階にも入らなかった」、大型店の不明は
      「設置者の欄が読めなかった」。意味の違うものが束ねた数だけ独り歩きする
    - **不明は値ではなく徴候。** 増えたら段階の語彙が足りていない印で、
      減らすのが仕事。升にすると「そういう種別がある」顔をして固定される

    正本4節③の住所と同じ形。「空なら決まらなかったと分かるだけで済む」。
    """

    def test_段階が決まらない回は升を作らない(self):
        row = 行(status="読めない語", first_seen=None, open_date="2026-09-24")
        del row["first_seen"]
        cells = aggregate.aggregate([row])
        self.assertEqual([c["stage"] for c in cells], [])

    def test_決まらなかったことは印で分かる(self):
        # **開札日が過ぎている**のに、どの結果にも入らない語
        row = 行(status="読めない語", first_seen=None, open_date="2026-09-01")
        del row["first_seen"]
        self.assertTrue(aggregate.unresolved(row, today="2026-09-19"))

    def test_不明という段階を作らない(self):
        self.assertFalse(hasattr(aggregate, "FUMEI"))

    def test_まだ開札していない回は決まらなかったに入れない(self):
        """開札日が来ていない回は、**決まらなかったのではなく、まだ起きていない。**

        ここを見ないと、予定が入っているだけの回が全部「読めなかった」に出て、
        本当に読めなかったものが埋もれる。
        """
        row = 行(status="", open_date="2027-12-01")
        self.assertFalse(aggregate.unresolved(row, today="2026-09-19"))


class 出す数字(unittest.TestCase):

    def test_3件そろえば中央値が出る(self):
        cells = aggregate.aggregate([
            行(base_price=1000, sale_price=1500, status="売却"),
            行(base_price=2000, sale_price=4000, status="売却"),
            行(base_price=3000, sale_price=3000, status="売却"),
        ])
        c = [x for x in cells if x["stage"] == "結果-落札"][0]
        self.assertEqual(c["base_median"], 2000)
        self.assertEqual(c["sale_median"], 3000)
        self.assertEqual(c["ratio_median"], 1.5)   # 1.5 / 2.0 / 1.0 の中央値

    def test_3件に満たなければ値段は出さない(self):
        cells = aggregate.aggregate([行(status="売却"), 行(status="売却")])
        c = [x for x in cells if x["stage"] == "結果-落札"][0]
        self.assertIsNone(c["base_median"])
        self.assertIsNone(c["sale_median"])
        self.assertIsNone(c["ratio_median"])

    def test_高い1件で壊れない(self):
        # 平均なら 1億超えに引っ張られる。中央値なら効かない
        cells = aggregate.aggregate([
            行(sale_price=1000, status="売却"), 行(sale_price=2000, status="売却"),
            行(sale_price=3000, status="売却"),
            行(sale_price=1000000000, status="売却"),
        ])
        uri = [x for x in cells if x["stage"] == "結果-落札"][0]
        self.assertEqual(uri["sale_median"], 2500)

    def test_不調と取下げを同じ欄に混ぜない(self):
        # 不調は「開札して売れなかった」、取下げは「開札の前に消えた」。
        # 混ぜると、このサイトの値打ちである「出したけれど売れなかった」が
        # 水増しになる（README「数字の出し方」）
        cells = aggregate.aggregate([
            行(status="不売"), 行(status="不売"), 行(status="不落"),
            行(status="取下げ"), 行(status="取下げ"), 行(status="取下げ"),
            行(status="売却"), 行(status="売却"), 行(status="売却"),
        ])
        n = {c["stage"]: c["count"] for c in cells}
        self.assertEqual(n["結果-不調"], 3)      # 不売2＋不落1
        self.assertEqual(n["結果-落札"], 3)
        # **取下げの升は作らない。** 置き場が正本で決まっていない
        self.assertNotIn("取下げ", n)

    def test_回の取消を物件の取下げに混ぜない(self):
        """**取消は回の単位の語。** 物件の取下げとは別のもの。

        回には `city_code` が付けようがないので升にならず、段階の語を要らない
        （回の状態は `data/agg/kaisatsu.json` の「状態」に別立てで出している）。

        前は WITHDRAWN に 取消・中止・変更 が入っていて、物件のカードに
        取消が出た日に**黙って取下げへ合流する**形だった。
        `docs/kiji-no-tane.md` が2か所で禁じていることを、コードが許していた。
        """
        self.assertEqual(aggregate.WITHDRAWN, ("取下げ",))
        cells = aggregate.aggregate([行(status="取消")])
        self.assertEqual([c["stage"] for c in cells], [],
                         "回の取消が物件の段階になっている")
        self.assertFalse(aggregate.undecided(行(status="取消")),
                         "取消は読めていない。置き場の話ではない")
        self.assertTrue(
            aggregate.unresolved(行(status="取消", open_date="2026-09-01"),
                                 today="2026-09-19"),
            "取消が data/parse-unknown.md に出ない")

    def test_取下げは結果の升に入れない(self):
        # 結果は「その月に開札された回」。取下げは開札そのものが行われていない。
        # 落札率の分母に入れると、分母が水増しになる
        cells = aggregate.aggregate([
            行(status="売却"), 行(status="売却"), 行(status="売却"),
            行(status="取下げ"), 行(status="取下げ"), 行(status="取下げ"),
        ])
        n = {c["stage"]: c["count"] for c in cells}
        self.assertEqual(n["結果"], 3)           # 取下げの3回は入らない
        self.assertEqual(n["結果-落札"], 3)
        self.assertNotIn("取下げ", n)

    def test_結果は落札と不調の足し算になっている(self):
        cells = aggregate.aggregate([
            行(status="売却"), 行(status="売却"), 行(status="売却"),
            行(status="不売"), 行(status="不売"), 行(status="不売"),
            行(status="取下げ"),
        ])
        n = {c["stage"]: c["count"] for c in cells}
        self.assertEqual(n["結果"], n["結果-落札"] + n["結果-不調"])


class 入札中と売却済みを混ぜない(unittest.TestCase):

    def test_段階ごとに別の升になる(self):
        cells = aggregate.aggregate([
            行(status="", first_seen="2026-09-02"),
            行(status="売却", first_seen="2026-09-02"),
            行(status="不売", first_seen="2026-09-02"),
        ])
        self.assertEqual({c["stage"] for c in cells},
                         {"公告", "公告-新規", "公告-再公告",
                          "結果", "結果-落札", "結果-不調"})

    def test_1つの回が公告と結果の両方に入る(self):
        # 9月に公告されて10月に売れた回は、9月の公告と10月の売却の両方に入る。
        # どちらも「その月に起きたこと」なので二重計上ではない
        cells = aggregate.aggregate([
            行(status="売却", first_seen="2026-09-02", open_date="2026-10-06"),
        ])
        got = {(c["stage"], c["ym"]) for c in cells}
        self.assertEqual(got, {("公告", "2026-09"), ("公告-新規", "2026-09"),
                               ("公告-再公告", "2026-09"),
                               ("結果", "2026-10"), ("結果-落札", "2026-10"),
                               ("結果-不調", "2026-10")})

    def test_再公告は新規に数えない(self):
        # 不売のあと、また公告に出た回。合計には入るが新規には入らない。
        # **再公告の升も出す。** 出さないと「公告 − 公告-新規」の引き算で
        # 再公告の正確な件数が分かってしまう（正本 3.2）
        cells = aggregate.aggregate([
            行(status="", first_seen="2026-11-02", re_notice=True),
        ])
        self.assertEqual({c["stage"] for c in cells},
                         {"公告", "公告-新規", "公告-再公告"})
        n = {c["stage"]: c["count"] for c in cells}
        self.assertEqual(n["公告-新規"], 0)      # 新規は1件も無かった

    def test_新規と再公告を足すと公告になる(self):
        cells = aggregate.aggregate([
            行(status="", first_seen="2026-11-02"),
            行(status="", first_seen="2026-11-05", re_notice=True, case_no="別"),
            行(status="", first_seen="2026-11-06", re_notice=True, case_no="別2"),
        ])
        n = {c["stage"]: c["count"] for c in cells}
        self.assertEqual(n["公告"], 3)
        self.assertIsNone(n["公告-新規"])        # 1件なのでぼかす
        self.assertIsNone(n["公告-再公告"])      # 2件なのでぼかす

    def test_新規だけを見れば新しく出た担保が分かる(self):
        cells = aggregate.aggregate([
            行(status="", first_seen="2026-11-02"),
            行(status="", first_seen="2026-11-05", re_notice=True,
              case_no="別"),
            行(status="", first_seen="2026-11-06", re_notice=True,
              case_no="別2"),
        ])
        kokoku = [c for c in cells if c["stage"] == "公告"][0]
        shinki = [c for c in cells if c["stage"] == "公告-新規"][0]
        self.assertEqual(kokoku["count"], 3)
        self.assertIsNone(shinki["count"])      # 1件なので伏せる
        self.assertEqual(shinki["count_label"], "1-2")

    def test_公告はその月に新しく出た数で数える(self):
        # 初めて見た日の月に入る。開札日（翌月）ではない
        cells = aggregate.aggregate([
            行(status="", first_seen="2026-09-02", open_date="2026-10-06"),
        ])
        self.assertEqual(cells[0]["stage"], "公告")
        self.assertEqual(cells[0]["ym"], "2026-09")

    def test_同じ物件を翌月また数えない(self):
        # 9月に出て10月まで一覧に残っていても、公告として数えるのは9月だけ
        row = 行(status="", first_seen="2026-09-02", last_seen="2026-10-20",
                open_date="2026-10-06")
        cells = aggregate.aggregate([row])
        kokoku = [c for c in cells if c["stage"] == "公告"]
        self.assertEqual(len(kokoku), 1)
        self.assertEqual(kokoku[0]["ym"], "2026-09")

    def test_結果は開札のあった月に入る(self):
        cells = aggregate.aggregate([
            行(status="売却", first_seen="2026-08-01", open_date="2026-10-06"),
        ])
        uri = [c for c in cells if c["stage"] == "結果-落札"][0]
        self.assertEqual(uri["ym"], "2026-10")

    def test_落札率の分母と分子が分かれている(self):
        # 「売れた件数」をレコード数で数えると、不調まで混ざって水増しになる
        cells = aggregate.aggregate([
            行(status="売却"), 行(status="売却"), 行(status="売却"),
            行(status="不売"), 行(status="不売"), 行(status="不売"),
            行(status="不売"), 行(status="不売"), 行(status="不売"),
        ])
        kekka = [c for c in cells if c["stage"] == "結果"][0]
        ochi = [c for c in cells if c["stage"] == "結果-落札"][0]
        fucho = [c for c in cells if c["stage"] == "結果-不調"][0]
        self.assertEqual(kekka["count"], 9)     # 分母
        self.assertEqual(ochi["count"], 3)      # 分子
        self.assertEqual(fucho["count"], 6)
        self.assertEqual(ochi["count"] + fucho["count"], kekka["count"])

    def test_必要な項目がすべて入っている(self):
        cells = aggregate.aggregate([行(), 行(), 行()])
        for k in ("system", "pref", "city", "city_code", "kind", "stage",
                  "ym", "count", "count_label", "base_median", "sale_median",
                  "ratio_median"):
            self.assertIn(k, cells[0])


if __name__ == "__main__":
    unittest.main()


class 段階は3つのまま(unittest.TestCase):
    """**段階は値ではなく位置なので、鍵に入れてよい**（正本 9節）。

    取下げは「公告に至るまでの位置」ではなく「公告のあとに起きたこと」で、
    **位置ではなく値**。段階を鍵に入れてよい理由が、取下げには当てはまらない。
    段階は **予定／公告／結果** の3つのまま（2026-09-19 に訂正が来た）。

    **では取下げをどこに入れるかは、まだ決まっていない。**
    決まるまで、升は作らず、行も捨てず、数だけ出す。
    """

    def test_段階の語は予定と公告と結果だけ(self):
        got = set(aggregate.FAMILIES.parents) | set(aggregate.FAMILIES.children)
        for stage in got:
            self.assertTrue(stage.startswith(("予定", "公告", "結果")), stage)

    def test_取下げの升を作らない(self):
        cells = aggregate.aggregate([行(status="取下げ")])
        self.assertEqual([c["stage"] for c in cells if "取下" in c["stage"]], [])

    def test_取下げの行は捨てない(self):
        row = 行(status="取下げ")
        self.assertTrue(aggregate.undecided(row))
        self.assertFalse(aggregate.unresolved(row, today="2026-09-19"),
                         "読めているのに「読めなかった」に混ざっている")

    def test_読めなかったと置き場が無いを混ぜない(self):
        """混ぜると、**語彙の穴がいくつあるのかが読めなくなる。**

        こちらが直せるのは `unresolved` のほうだけ。
        """
        yomenai = 行(status="執行停止", open_date="2026-09-01")
        okiba = 行(status="取下げ", open_date="2026-09-01")
        self.assertTrue(aggregate.unresolved(yomenai, today="2026-09-19"))
        self.assertFalse(aggregate.undecided(yomenai))
        self.assertFalse(aggregate.unresolved(okiba, today="2026-09-19"))
        self.assertTrue(aggregate.undecided(okiba))


class 取下げと繰り越しは別物(unittest.TestCase):
    """2026-09-19、実務からの整理。

        取下げ    手続きが止まる。以後、同じ物件は出てこない
        繰り越し  売却できず次回へ。次の期間の公告に**同じ物件がまた出る**

    **消えた物件を全部「取下げ」と数えると、繰り越し待ちが混ざって
    取下げ率が過大になる。** 見分けるには、次の期間に再登場するかを追うしかない。

    化けたあとでは気づけない。消えた行はもう一覧に残っていないので、
    照らし合わせる相手がいない。**だから母集団の保存が先。**
    """

    def 消えた(self, **kw):
        row = 行(status=aggregate.GONE, gone_on="2026-10-01", **kw)
        return row

    def test_消えた物件は3つめの箱に入る(self):
        row = self.消えた()
        self.assertTrue(aggregate.gone(row))
        self.assertFalse(aggregate.unresolved(row, today="2026-10-01"),
                         "語彙の穴に混ざっている")
        self.assertFalse(aggregate.undecided(row),
                         "取下げと同じ箱に入っている")

    def test_開札日より前に消えても見える(self):
        """**取下げのいちばん多い形。** 開札日で切ると丸ごと見えなくなる。

        公告に出たあと、開札日より前に取り下げられる
        （任意売却がまとまる、債務者や親族が払う）。
        2026-09-19 まで、この形はどこにも出ていなかった。
        """
        row = self.消えた(open_date="2027-11-05")
        self.assertTrue(aggregate.gone(row))

    def test_消えた物件を取下げの升にしない(self):
        cells = aggregate.aggregate([self.消えた()])
        for c in cells:
            self.assertNotIn("取下", c["stage"])

    def test_3つの箱は重ならない(self):
        """1つの行が2つの箱に入ると、足したときに数が合わなくなる。"""
        rows = [self.消えた(),
                行(status="取下げ", open_date="2026-09-01"),
                行(status="執行停止", open_date="2026-09-01"),
                行(status="売却", open_date="2026-09-01")]
        for r in rows:
            n = sum((aggregate.gone(r),
                     aggregate.unresolved(r, today="2026-09-19"),
                     aggregate.undecided(r)))
            self.assertLessEqual(n, 1, "%r が2つの箱に入っている" % r.get("status"))

    def test_再登場を追える形で残している(self):
        """`property_key` に開札日を入れない。

        入れると、同じ物件が期間をまたいだときに別の鍵になり、
        **繰り越しを追えなくなる**（正本 9節「鍵にはあとから変わらないものだけ」）。
        """
        import parse
        key = parse.property_key_of if hasattr(parse, "property_key_of") else None
        row = 行()
        pk = row.get("property_key") or ""
        self.assertNotIn(row.get("open_date") or "@@", pk,
                         "property_key に開札日が入っている")
