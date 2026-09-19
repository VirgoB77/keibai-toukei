#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""集計の3つのガードを固定する。

小さい町では、件数が1件と分かるだけで物件が特定できてしまう。
ここが緩むと、個票を出していなくても同じことになる。

    python3 -m unittest discover -s tests
"""

import io
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
        self.assertEqual(n["落札"], (3, "3"))
        self.assertEqual(n["不調"], (0, "0"))   # 不売は1件も無かった

    def test_まとまりが出ていなければ兄弟も足さない(self):
        # 公告日が分からない行は公告の升に入らない。
        # 入っていないまとまりの兄弟まで 0 で作ると、無い月の升が増える
        cells = aggregate.aggregate([行(status="売却")])
        self.assertNotIn("公告-再公告", {c["stage"] for c in cells})

    def test_小さい升は実数を出さず_ラベルで見せる(self):
        cells = aggregate.aggregate([行(status="不売")])
        fubai = [c for c in cells if c["stage"] == "不調"][0]
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
        c = [x for x in cells if x["stage"] == "落札"][0]
        self.assertEqual(c["base_median"], 2000)
        self.assertEqual(c["sale_median"], 3000)
        self.assertEqual(c["ratio_median"], 1.5)   # 1.5 / 2.0 / 1.0 の中央値

    def test_3件に満たなければ値段は出さない(self):
        cells = aggregate.aggregate([行(status="売却"), 行(status="売却")])
        c = [x for x in cells if x["stage"] == "落札"][0]
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
        uri = [x for x in cells if x["stage"] == "落札"][0]
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
        self.assertEqual(n["不調"], 3)      # 不売2＋不落1
        self.assertEqual(n["落札"], 3)
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
        self.assertEqual(n["落札"], 3)
        self.assertNotIn("取下げ", n)

    def test_結果は落札と不調の足し算になっている(self):
        cells = aggregate.aggregate([
            行(status="売却"), 行(status="売却"), 行(status="売却"),
            行(status="不売"), 行(status="不売"), 行(status="不売"),
            行(status="取下げ"),
        ])
        n = {c["stage"]: c["count"] for c in cells}
        self.assertEqual(n["結果"], n["落札"] + n["不調"])


class 入札中と売却済みを混ぜない(unittest.TestCase):

    def test_段階ごとに別の升になる(self):
        cells = aggregate.aggregate([
            行(status="", first_seen="2026-09-02"),
            行(status="売却", first_seen="2026-09-02"),
            行(status="不売", first_seen="2026-09-02"),
        ])
        self.assertEqual({c["stage"] for c in cells},
                         {"公告", "公告-新規", "公告-再公告",
                          "結果", "落札", "不調"})

    def test_1つの回が公告と結果の両方に入る(self):
        # 9月に公告されて10月に売れた回は、9月の公告と10月の売却の両方に入る。
        # どちらも「その月に起きたこと」なので二重計上ではない
        cells = aggregate.aggregate([
            行(status="売却", first_seen="2026-09-02", open_date="2026-10-06"),
        ])
        got = {(c["stage"], c["ym"]) for c in cells}
        self.assertEqual(got, {("公告", "2026-09"), ("公告-新規", "2026-09"),
                               ("公告-再公告", "2026-09"),
                               ("結果", "2026-10"), ("落札", "2026-10"),
                               ("不調", "2026-10")})

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
        uri = [c for c in cells if c["stage"] == "落札"][0]
        self.assertEqual(uri["ym"], "2026-10")

    def test_落札率の分母と分子が分かれている(self):
        # 「売れた件数」をレコード数で数えると、不調まで混ざって水増しになる
        cells = aggregate.aggregate([
            行(status="売却"), 行(status="売却"), 行(status="売却"),
            行(status="不売"), 行(status="不売"), 行(status="不売"),
            行(status="不売"), 行(status="不売"), 行(status="不売"),
        ])
        kekka = [c for c in cells if c["stage"] == "結果"][0]
        ochi = [c for c in cells if c["stage"] == "落札"][0]
        fucho = [c for c in cells if c["stage"] == "不調"][0]
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


class 段階は3つのまま(unittest.TestCase):
    """**段階は値ではなく位置なので、鍵に入れてよい**（正本 9節）。

    取下げは「公告に至るまでの位置」ではなく「公告のあとに起きたこと」で、
    **位置ではなく値**。段階を鍵に入れてよい理由が、取下げには当てはまらない。
    段階は **予定／公告／結果** の3つのまま（2026-09-19 に訂正が来た）。

    **では取下げをどこに入れるかは、まだ決まっていない。**
    決まるまで、升は作らず、行も捨てず、数だけ出す。
    """

    # 段階（親）に使ってよい語。位置なので鍵に入れてよい
    段階 = ("予定", "公告", "結果")
    # 結果の語。**この2つだけ**（正本 6節・2026-09-19）
    結果の語 = ("落札", "不調")

    def test_親は段階の3語だけ(self):
        for parent in aggregate.FAMILIES.parents:
            self.assertIn(parent, self.段階, parent)

    def test_子は内訳か結果の語のどちらか(self):
        """子は2通りある（正本 6節）。

            公告-新規   段階の内訳。**親-… の形**
            落札        結果の語。**親の接頭辞を持たない**
        """
        for f in aggregate.FAMILIES.families:
            for kid in f[1:]:
                内訳 = kid.startswith(f[0] + "-")
                self.assertTrue(内訳 or kid in self.結果の語,
                                "%s は内訳でも結果の語でもない" % kid)

    def test_段階と結果を1つの升に混ぜない(self):
        """**`結果-落札` のような名前を作らない**（正本 6節・2026-09-19）。

        段階（結果）と結果（落札）が1つの升に入っている形。
        前はこう書いていた。正本が直したので、こちらも直した。
        """
        got = set(aggregate.FAMILIES.parents) | set(aggregate.FAMILIES.children)
        for stage in got:
            for 段 in self.段階:
                for 語 in self.結果の語:
                    self.assertNotEqual(stage, "%s-%s" % (段, 語), stage)

    def test_結果の升に出るのは落札と不調だけ(self):
        """相手のページの語（売却・不売・売却済）は**読むだけ**。

        こちらが書き出す語は 落札／不調 の2つ。取り違えると、
        4サイトで同じものが4通りの名前になる。
        """
        for 語, 原文たち in (("落札", aggregate.SOLD),
                          ("不調", aggregate.UNSOLD)):
            for 原文 in 原文たち:
                cells = aggregate.aggregate(
                    [行(status=原文, open_date="2026-10-01")])
                stages = {c["stage"] for c in cells}
                self.assertIn(語, stages, 原文)
                # **「落札」は両方に入っている。** 相手のページにも出るし、
                # こちらが書き出す語でもある。だから
                # 「相手の語が升に出ていないこと」は、語が違うときだけ見る
                if 原文 != 語:
                    self.assertNotIn(原文, stages,
                                     "相手の語 %s をそのまま升に出している" % 原文)

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


class 足したときに数が合うこと(unittest.TestCase):
    """正本 3.2（2026-09-19）。**合わなければ黙って落としている。**

    正本の等式は「升の合計 ＋ not_counted の3つ ＝ 見た行の数」。
    **このサイトではそのままでは閉じない。** 1つの行が2つ以上の升に入り、
    取下げになった行は公告の升にも入ったまま残るため
    （母集団の保存が先。正本 3.5）。実測で 106 ＋ 1 ＝ 107 ≠ 106 になった。

    だから2つに分けて見る（食い違いとして報告ずみ。
    docs/seihon-toiawase.md #11）。

        ① 行方の保存（在庫）… 1行は必ず1つの行方に入る
        ② 内訳の保存（流量）… 子の升を足すと親の升になる
    """

    def test_1行は必ず1つの行方に入る(self):
        rows = [行(status="売却", open_date="2026-10-01"),
                行(status="不売", open_date="2026-10-01"),
                行(status="取下げ"),
                行(status="", gone_on="2026-09-18"),
                行(status="", open_date="2099-01-01"),
                行(status="よく分からない語", open_date="2026-10-01")]
        got = [aggregate.yukue(r, today="2026-10-20") for r in rows]
        self.assertEqual(got, ["落札", "不調", "取下げ", "消えた", "待ち",
                               "読めない"])

    def test_行方を足すと見た行の数になる(self):
        rows = [行(status="売却", first_seen="2026-09-01",
                  open_date="2026-10-01"),
                行(status="取下げ", first_seen="2026-09-01"),
                行(status="", first_seen="2026-09-01",
                  open_date="2099-01-01")]
        d = aggregate.kazu_ga_au(rows, today="2026-10-20")
        self.assertEqual(sum(d["行方"].values()), len(rows))
        self.assertEqual(d["食い違い"], [])

    def test_升が1つもできない行を拾う(self):
        """**これが「黙って落ちる」の実体。**

        前の検査（行方の合計 ＝ 見た行の数）は恒真で、1つも拾えなかった。
        日付の列を読み落とすと `events()` が空を返し、
        升にも not_counted にも出ないまま消える。
        """
        # 日付が1つも無い。行方は「待ち」だが、升は1つもできない
        rows = [行(status="", first_seen="", open_date="", bid_end="",
                  last_seen="")]
        d = aggregate.kazu_ga_au(rows, today="2026-10-20")
        self.assertEqual(d["升にならない行"], 1)
        self.assertTrue(d["食い違い"], "升が1つもできないのに鳴らない")

    def test_落札と読めているのに落札の升が無い行を拾う(self):
        """**①より見つけにくい形。** 公告の升には入るので、消えた顔をしない。"""
        rows = [行(status="売却", first_seen="2026-09-01",
                  open_date="", bid_end="", last_seen="")]
        d = aggregate.kazu_ga_au(rows, today="2026-10-20")
        self.assertEqual(d["升にならない行"], 1)
        self.assertTrue(any("落札" in b for b in d["食い違い"]), d["食い違い"])

    def test_内訳は升ごとに見る(self):
        """**全体で1本に畳むと、逆向きの食い違いが打ち消しあう。**

        9月に親が1多く、10月に子が1多いと、足した合計は合ってしまう。
        """
        f = aggregate.FAMILIES
        self.assertEqual(f.check_sums({"結果": 4, "落札": 1, "不調": 3}), [],
                         "全体で足すと通ってしまう（これが打ち消しあい）")
        self.assertTrue(f.check_sums({"結果": 3, "落札": 1, "不調": 1}))
        self.assertTrue(f.check_sums({"結果": 1, "落札": 0, "不調": 2}))

    def test_打ち消しあう食い違いを_kazu_ga_auが拾う(self):
        """**升ごとに見ていないと、これが通る。**

        `events()` は1行から親と子をちょうど1つずつ出すので、
        全体で足すと 親 ＝ 子の合計 が恒等的に成り立つ。
        月をまたいで逆向きにずらすと、合計は合ったまま升は合わない。
        """
        rows = [行(status="売却", first_seen="2026-09-01",
                  open_date="2026-09-10"),
                行(status="売却", first_seen="2026-10-01",
                  open_date="2026-10-10", case_no="別")]
        cells = aggregate.aggregate(rows, with_raw=True)
        通る = aggregate.kazu_ga_au(rows, cells, today="2026-10-20")
        self.assertEqual(通る["食い違い"], [], "壊す前から鳴っている")

        # 月をまたいで逆向きにずらす。**全体の合計は変えない**
        ochi = sorted([c for c in cells if c["stage"] == "落札"],
                      key=lambda c: c["ym"])
        self.assertEqual(len(ochi), 2)
        ochi[0]["_n"] -= 1
        ochi[1]["_n"] += 1
        合計 = {}
        for c in cells:
            合計[c["stage"]] = 合計.get(c["stage"], 0) + c["_n"]
        self.assertEqual(合計["結果"], 合計["落札"] + 合計["不調"],
                         "全体では合っている（これが打ち消しあい）")

        d = aggregate.kazu_ga_au(rows, cells, today="2026-10-20")
        self.assertTrue(d["食い違い"],
                        "全体では合うが升ごとには合わない形を拾えていない")
        self.assertEqual(len(d["内訳"]), 2, d["内訳"])

    def test_実数の無い升を渡したら黙って通さない(self):
        """`_n` が無いと②は見られない。**飛ばさずに落とす。**"""
        rows = [行(status="売却", first_seen="2026-09-01",
                  open_date="2026-10-01")]
        with self.assertRaises(ValueError):
            aggregate.kazu_ga_au(rows, aggregate.aggregate(rows),
                                 today="2026-10-20")

    def test_notcountedに入る行は升が無くてよい(self):
        """取下げ・消えた・読めない は、升が無くても数えられている。"""
        rows = [行(status="取下げ", first_seen="", open_date="",
                  bid_end="", last_seen="")]
        d = aggregate.kazu_ga_au(rows, today="2026-10-20")
        self.assertEqual(d["升にならない行"], 0)
        self.assertEqual(d["食い違い"], [])

    def test_開札より前に消えたのに結果が出ている行を拾う(self):
        """**これだけが本当の食い違い。**

        消えたあとに結果が出ることはない。どちらかの読みが間違っている。
        """
        r = 行(status="売却", open_date="2026-10-01", gone_on="2026-09-18")
        self.assertTrue(aggregate.yukue_conflicts(r))
        self.assertEqual(aggregate.kazu_ga_au([r])["食い違う合図"], 1)

    def test_普通の一生を食い違いにしない(self):
        """**開札が済んで一覧から落ちるのは、食い違いではない。**

        `parse.merge_snapshot()` は、その日の一覧に出てこなかった行すべてに
        `gone_on` を付ける。売れた物件も不売の物件も、開札が済めば落ちる。
        ここを食い違いに数えると、結果が溜まるほど毎回鳴る見張りになる
        （正本 9節「誤報を出す見張りは、そのうち誰も見なくなる」）。
        """
        for r in (行(status="売却", open_date="2026-10-01",
                    gone_on="2026-10-02"),
                  行(status="不売", open_date="2026-10-01",
                    gone_on="2026-10-05"),
                  行(status="取下げ", open_date="2026-10-01",
                    gone_on="2026-09-18"),
                  行(status="", open_date="2026-10-01",
                    gone_on="2026-09-18")):
            self.assertEqual(aggregate.yukue_conflicts(r), [],
                             "普通の一生が食い違いになっている: %r" % (r,))

    def test_内訳が合わなければ拾う(self):
        rows = [行(status="売却", open_date="2026-10-01")]
        cells = aggregate.aggregate(rows, with_raw=True)
        self.assertEqual(aggregate.kazu_ga_au(rows, cells,
                                              today="2026-10-20")["食い違い"], [])
        # 子の升を1つ落とすと鳴る
        欠け = [c for c in cells if c["stage"] != "不調"]
        d = aggregate.kazu_ga_au(rows, 欠け, today="2026-10-20")
        self.assertTrue(d["食い違い"], "子を落としたのに鳴らない")

    def test_行方の語は全部数えられる(self):
        """**YUKUE に足した語を、kazu_ga_au が数え落とさない。**"""
        rows = [行(status="売却", open_date="2026-10-01"),
                行(status="不売", open_date="2026-10-01"),
                行(status="取下げ"), 行(status="", gone_on="2026-09-18"),
                行(status="", open_date="2099-01-01"),
                行(status="謎", open_date="2026-10-01")]
        d = aggregate.kazu_ga_au(rows, today="2026-10-20")
        self.assertEqual(set(d["行方"]), set(aggregate.YUKUE))

    def test_not_countedの3つは行方から作る(self):
        """**数え方を2つ持たない**（正本 9節）。

        述語を別々に呼ぶと、排他でない行が2つの欄に入って合計が超える。
        """
        import make_index
        rows = [行(status="取下げ", gone_on="2026-09-18")]
        got = make_index.not_counted(rows)
        self.assertEqual(sum(got.values()), 1,
                         "同じ行が2つの欄に入っている: %r" % (got,))
        self.assertEqual(got["undecided"], 1)
        self.assertEqual(got["gone"], 0)


class 見張りと出力語がずれない(unittest.TestCase):
    """**自分が書き出した語を、自分の見張りが人名として拾わないこと。**

    「不調」は漢字2文字で、`looks_like_person_name` の網（2〜8文字）に
    素で掛かる。`OUR_WORDS` に足し忘れると、公開ファイルの見張りが
    毎回鳴って誰も見なくなる（正本 9節「鳴らせていない見張り」の裏返し）。
    """

    def test_出力語はOUR_WORDSに入っている(self):
        from common import privacy
        words = (set(aggregate.FAMILIES.parents)
                 | set(aggregate.FAMILIES.children) | {aggregate.TORISAGE})
        欠け = sorted(w for w in words
                     if "-" not in w and w not in privacy.OUR_WORDS)
        self.assertEqual(欠け, [], "OUR_WORDS に無い出力語")

    def test_出力語を人名として拾わない(self):
        from common import privacy
        words = (set(aggregate.FAMILIES.parents)
                 | set(aggregate.FAMILIES.children) | {aggregate.TORISAGE})
        for w in sorted(words):
            self.assertFalse(privacy.looks_like_person_name(w), w)


class 実数を出力に残さない(unittest.TestCase):
    """`_n` は**伏せた升の真の件数**。出力に残ると、伏せた意味が消える。

    `with_raw=True` は2つのためだけに使う。

        引き算の手当て（親を出すか決める。正本 3.2）
        足したときに数が合うかの検査

    どちらも書き出す前に終わる。**書き出すときには落ちていること。**
    ここが抜けると、"1-2" と書いた升の隣に 1 か 2 がそのまま並ぶ。
    """

    def test_with_rawを付けたときだけ実数が付く(self):
        rows = [行(status="売却", open_date="2026-10-01")]
        self.assertNotIn("_n", aggregate.aggregate(rows)[0])
        self.assertIn("_n", aggregate.aggregate(rows, with_raw=True)[0])

    def test_伏せた升の実数が出力に残らない(self):
        """1件の升（"1-2" に伏せる）で確かめる。**いちばん危ない形。**"""
        cells = aggregate.aggregate([行(status="売却", open_date="2026-10-01")])
        伏せた = [c for c in cells if c["count"] is None]
        self.assertTrue(伏せた, "1件の升が伏せられていない")
        for c in 伏せた:
            self.assertEqual(c["count_label"], "1-2")
            self.assertNotIn("_n", c, "伏せた升に実数が付いている")

    def test_書き出したファイルに実数が入っていない(self):
        """**実物を読んで確かめる。** 落とす処理の順番が変わっても鳴る。"""
        import json
        import os
        if not os.path.exists(aggregate.OUT_PATH):
            self.skipTest("data/agg/monthly.json が無い（金庫の外）")
        with io.open(aggregate.OUT_PATH, encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn('"_n"', text,
                         "%s に実数が残っている" % aggregate.OUT_PATH)
        for cell in json.loads(text)["cells"]:
            self.assertNotIn("_n", cell)


if __name__ == "__main__":
    unittest.main()
