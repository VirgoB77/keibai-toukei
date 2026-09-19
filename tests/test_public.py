#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公開してよい置き場は data/public/ だけ、を見張る。

**これは升1つ1つの話ではない。ファイル全体の話。**

`data/agg/` には同じ数が2つ以上の粗さで入っている（種別あり・種別なし、
庁×月・庁×年・府県×月…）。1つ1つの升は正本 3.2 を守っていても、
**2つの粗さを同時に出せば引き算で伏せた升が戻る**。だから升ごとの手当てでは
直らない。置き場所で分ける。

見張るのは3つ。

    1. data/agg/*.json は全部「公開しない」の欄を持っている
    2. その文言は common/shukei.py の NOT_PUBLIC と同じ（各ファイルで書き直さない）
    3. data/public/*.json はその欄を持たない（持っていたら置き場を間違えている）

そして 4つめ。**monthly.json に親（合計）の升が1つも無い。**
これは正本 3.2 の例そのものなので、数字ごと固定する。

    python3 -m unittest discover -s tests
"""

import glob
import io
import json
import os
import sys
import unittest

import kinko  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "scripts"))

from common.report import NOT_PUBLIC_LINE  # noqa: E402
from common.shukei import NOT_PUBLIC  # noqa: E402

AGG = os.path.join(HERE, "data", "agg")
PUBLIC = os.path.join(HERE, "data", "public")
MARK = "公開しない"


def jsons(d):
    return sorted(glob.glob(os.path.join(d, "*.json")))


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class 置き場(unittest.TestCase):

    def test_aggは全部が公開しないと書いてある(self):
        kinko.need(self)
        got = jsons(AGG)
        self.assertTrue(got, "data/agg/ に集計が1つも無い")
        for path in got:
            name = os.path.basename(path)
            doc = load(path)
            self.assertIn(MARK, doc, "%s に「%s」の欄が無い" % (name, MARK))
            self.assertEqual(doc[MARK], NOT_PUBLIC,
                             "%s の文言が NOT_PUBLIC と違う。"
                             "各ファイルで書き直さない" % name)

    def test_publicには公開しないと書いていない(self):
        for path in jsons(PUBLIC):
            doc = load(path)
            self.assertNotIn(MARK, doc,
                             "%s は公開する置き場にあるのに「%s」と書いてある。"
                             "置き場が違う" % (os.path.basename(path), MARK))

    def test_publicに置いてよいのは決めたものだけ(self):
        # 増やすときは、その1つが「1つの粗さだけ」であることを確かめてから
        # ここに足す。黙って増えないように、名前で固定する
        ALLOWED = {"index.json", "kokuyu.json", "koyu.json", "atochi.json"}
        got = {os.path.basename(p) for p in jsons(PUBLIC)}
        self.assertEqual(got - ALLOWED, set(),
                         "data/public/ に見覚えのないファイルがある")


class 走らせた記録(unittest.TestCase):
    """`data/*.md` は走らせた記録。**公開しない**（正本 9節）。

        走らせた記録（`data/*.md`・…）は生の値を含みうるので、収集用の
        `data/reports/` に写す。公開用には commit しない

    ここには一次情報から写した行や、伏せる前の値がそのまま入りうる。
    人が開いたときに、そのファイルだけを見て分かるように先頭に1行置く。
    """

    def test_記録は全部が公開しないと書いてある(self):
        kinko.need(self)
        got = sorted(glob.glob(os.path.join(HERE, "data", "*.md")))
        self.assertTrue(got, "data/ に記録が1つも無い")
        for path in got:
            with open(path, encoding="utf-8") as f:
                head = "".join([next(f, "") for _ in range(5)])
            self.assertIn(NOT_PUBLIC_LINE, head,
                          "%s の先頭に「公開しない」の1行が無い"
                          % os.path.basename(path))


class 実数が出せた升の割合(unittest.TestCase):
    """正本 3.2「判定は『実数が出せた升の割合』で見る」（2026-09-17）。

    伏せ字の割合で機械判定すると、本当に0件ばかりの層がすり抜ける。
    **このサイトの 競売/公告-再公告 がまさにその形**（伏せ字 0% ・
    本当に0件 100% ・実数 0%）。伏せ字の割合では絶対に引っかからない。
    """

    def test_分母は地図に色を塗る単位(self):
        import make_index
        units = make_index.map_units()
        # 大阪府・兵庫県。政令市（大阪市・堺市・神戸市）は区で数え、親は数えない
        self.assertEqual(len(units), 121)
        names = {c["city"] for c in units}
        self.assertNotIn("大阪市", names)
        self.assertIn("大阪市西区", names)

    def test_伏せ字の割合では見つからない層を拾う(self):
        import make_index
        by_city = [
            # 伏せ字は1つも無いのに、実数も1つも出せていない層
            {"kind": "競売/公告-再公告", "count": 0},
            {"kind": "競売/公告-再公告", "count": 0},
            # 伏せ字だらけだが実数もいくらか出せている層
            {"kind": "競売/公告-新規", "count": None},
            {"kind": "競売/公告-新規", "count": 5},
        ]
        per = make_index.shown_ratio(by_city, [0] * 100)
        self.assertEqual(per["競売/公告-再公告"]["伏せ字"], 0)
        self.assertEqual(per["競売/公告-再公告"]["実数の割合"], 0.0)
        self.assertEqual(per["競売/公告-新規"]["実数の割合"], 1.0)

    def test_升なしを0件と数えない(self):
        import make_index
        per = make_index.shown_ratio([{"kind": "x", "count": 0}], [0] * 10)
        self.assertEqual(per["x"]["升の0"], 1)
        self.assertEqual(per["x"]["升なし"], 9)   # 見ていないだけ。0件ではない


class 余裕を測ってある(unittest.TestCase):
    """正本 3.2「足してから測るのではなく、足す前に測る」。

    **測っていないと「戻らない」とは言えない。** 戻る升が0でも、
    いまのデータでぎりぎり成り立っているだけかもしれない。
    """

    def test_測った結果が置いてある(self):
        kinko.need(self)
        path = os.path.join(HERE, "data", "yoyuu.md")
        self.assertTrue(os.path.exists(path),
                        "余裕を測っていない（make_index.py を走らせること）")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("余裕", text)
        self.assertIn("いま組合せが1通りのまとまり", text)

    def test_余裕は公開しない(self):
        """k と m を公開側に書くと、m が出て組合せが減る。"""
        kinko.need(self)
        path = os.path.join(HERE, "data", "yoyuu.md")
        with open(path, encoding="utf-8") as f:
            head = "".join([next(f, "") for _ in range(5)])
        self.assertIn(NOT_PUBLIC_LINE, head)

    def test_組合せ1通りのまとまりの親を出していない(self):
        """正本 3.2「当てる組合せが1通りしかないまとまりは、親を出さない。例外なし」。

        いまの実測では、まとまりのほとんどが `k=1`。
        **親を1つ出した瞬間に、その市の伏せた升が全部そのまま決まる。**
        """
        import make_index
        from common.shukei import must_hide_parent
        rows = make_index.load_rows()
        if not rows:
            self.skipTest("行データが無い（公開側のチェックアウト）")
        index = make_index.build(rows)
        cells = [c for c in index["_yoyuu"] if c["組合せ"] == 1]
        self.assertTrue(cells, "組合せ1通りのまとまりが1つも無い。"
                               "測り方が変わっていないか確かめること")
        # 親（合計）の升が1つも出ていないこと。出したら上の全部が決まる
        stages = {c["kind"].split("/", 1)[1]
                  for c in index["counts_by_city"]}
        self.assertEqual(stages & set(make_index.FAMILIES.parents), set())
        # 市区町村ごとの合計を作れる欄が無いこと
        for c in index["counts_by_city"]:
            self.assertNotIn("city_total", c)
            self.assertNotIn("total", c)

    def test_index_jsonに合計の欄が無い(self):
        """余裕0のまとまりがあるので、**親を1つ出したら全部決まる**。

        ここが見張れるのは index.json だけ。**記事と SNS は機械では止まらない**
        ので、決定として docs/kiji-no-tane.md の「出さないもの」に書いてある。
        """
        index = load(os.path.join(PUBLIC, "index.json"))
        for name in ("total", "合計", "counts_total", "by_city_total"):
            self.assertNotIn(name, index)
        # 升そのものにも「その市の合計」を入れない
        for c in index.get("counts_by_city") or []:
            self.assertNotIn("city_total", c)
            self.assertIn("/", c["kind"], "kind は <制度>/<種別> の形（正本 6節）")


class 不明を升にしない(unittest.TestCase):
    """**「不明」という段階を作らない**（正本 9節・2026-09-19）。

    `kind` に出すと、横断ハブで4サイトの「不明」が1つの塊になる。
    競売の不明は「どの段階にも入らなかった」、大型店の不明は
    「設置者の欄が読めなかった」。**意味の違うものが、束ねた数だけ独り歩きする。**

    捨てていないことは、`kind` ではなく `unresolved` の欄で伝える。
    升ではないので、市区町村も種別も月も付かない。数だけ。
    """

    def test_kindに不明が出ない(self):
        index = load(os.path.join(PUBLIC, "index.json"))
        for c in index.get("counts_by_city") or []:
            self.assertNotIn("不明", c["kind"])

    def test_不明という段階を持っていない(self):
        import aggregate
        self.assertFalse(hasattr(aggregate, "FUMEI"))
        stages = set(aggregate.FAMILIES.parents) | set(aggregate.FAMILIES.children)
        self.assertNotIn("不明", stages)

    def test_捨てていないことは別の欄で伝える(self):
        index = load(os.path.join(PUBLIC, "index.json"))
        self.assertIn("not_counted", index, "黙って捨てていないことが伝わらない")
        for k in ("unresolved", "undecided"):
            self.assertIsInstance(index["not_counted"][k], int, k)

    def test_kindに取下げが出ない(self):
        """**段階は 予定／公告／結果 の3つ**（正本 9節・2026-09-19）。

        取下げの置き場は、正本でまだ決まっていない。
        """
        index = load(os.path.join(PUBLIC, "index.json"))
        for c in index.get("counts_by_city") or []:
            self.assertNotIn("取下", c["kind"])

    def test_決まらなかった行は記録に出る(self):
        """**升は作らないが、黙ってもいない**（正本 9節）。"""
        kinko.need(self)
        path = os.path.join(HERE, "data", "parse-unknown.md")
        with open(path, encoding="utf-8") as f:
            self.assertIn("段階が決まらなかった行", f.read())


class 親の升(unittest.TestCase):

    def test_monthlyに親の升が無い(self):
        kinko.need(self)
        import aggregate
        doc = load(os.path.join(AGG, "monthly.json"))
        stages = {c["stage"] for c in doc["cells"]}
        got = stages & set(aggregate.FAMILIES.parents)
        self.assertEqual(got, set(),
                         "monthly.json に親（合計）の升がある: %s。"
                         "子を引くと伏せた升が戻る（正本 3.2）" % sorted(got))

    def test_monthlyの兄弟がそろっている(self):
        kinko.need(self)
        import aggregate
        doc = load(os.path.join(AGG, "monthly.json"))
        stages = {c["stage"] for c in doc["cells"]}
        self.assertEqual(aggregate.FAMILIES.missing_siblings(stages), [])
        self.assertEqual(aggregate.FAMILIES.undeclared(stages), [])


class 引き算(unittest.TestCase):
    """index.json の升を、monthly.json の内訳で割れないこと。

    index.json は種別をまとめた粗さ、monthly.json は種別で割った粗さ。
    **両方出すと、index の実数から monthly の伏せた升が決まる。**
    monthly.json を公開しないのはこれが理由なので、
    「なぜ分けたか」をここに残す。
    """

    def test_両方出すと伏せた升が戻ることを確かめておく(self):
        kinko.need(self)
        index = load(os.path.join(PUBLIC, "index.json"))
        monthly = load(os.path.join(AGG, "monthly.json"))
        if not index.get("counts_by_city"):
            self.skipTest("まだ升が無い")

        narrowed, exact = [], []
        for c in index["counts_by_city"]:
            if c.get("count") is None:
                continue
            stage = c["kind"].split("/", 1)[1]
            kids = [x for x in monthly["cells"]
                    if x["city_code"] == c["city_code"]
                    and x["stage"] == stage and x["ym"] == c["period"]]
            hidden = [x for x in kids if x["count"] is None]
            if not hidden:
                continue
            shown = sum(x["count"] for x in kids if x["count"] is not None)
            narrowed.append((c["city"], c["count"] - shown, len(hidden)))
            if len(hidden) == 1:
                # 伏せた升が1つだけ → 引き算でその升の実数がそのまま出る
                exact.append((c["city"], c["count"] - shown))

        self.assertTrue(
            narrowed,
            "index と monthly を並べても何も戻らないなら、"
            "分けている理由を書き直すこと")
        self.assertTrue(
            exact,
            "伏せた升が1つだけの市区町村が無い。"
            "いちばん強い例なので、無くなったら理由を確かめること")

    def test_publicの中だけなら戻らない(self):
        """公開する置き場のファイルだけを並べても、引き算では戻らない。

        **これが本番。** 上の test は「だから分けた」の記録で、
        こちらは「分けた結果、公開側では戻らない」の確認。
        """
        index = load(os.path.join(PUBLIC, "index.json"))
        cells = index.get("counts_by_city") or []
        self.assertEqual(index.get("records"), [],
                         "records は空でなければならない"
                         "（入札中・人が住んでいる建物を含む）")
        # 同じ升が2度出ていないこと。出ていれば粗さが混ざっている
        keys = [(c["city_code"], c["kind"], c["period"]) for c in cells]
        self.assertEqual(len(keys), len(set(keys)),
                         "index.json に同じ3つ組の升が2度出ている")
        # 合計の欄を持たないこと（親が無ければ引き算の起点が無い）
        for name in ("total", "合計", "counts_total"):
            self.assertNotIn(name, index,
                             "index.json に合計の欄「%s」がある" % name)


class 実数はどのファイルにも残さない(unittest.TestCase):
    """`_n` は伏せた升の**真の件数**。1本でも漏れると伏せた意味が消える。

    `aggregate.py` の中で落としているが、**落とす場所は1か所しかない。**
    新しい出力を足した人がそこを通さなければ、そのまま出る。
    だから置き場ではなく、**出来上がったファイル全部**を見る
    （正本 9節「検査は最初の1件で止まらない形にする」）。
    """

    def test_dataの下のjsonに実数が入っていない(self):
        kinko.need(self)
        bad = []
        for path in sorted(glob.glob(os.path.join(HERE, "data", "**", "*.json"),
                                     recursive=True)):
            with io.open(path, encoding="utf-8") as f:
                if '"_n"' in f.read():
                    bad.append(os.path.relpath(path, HERE))
        self.assertEqual(bad, [], "伏せた升の実数が残っているファイル")


class 道具2つが同じ木を見ている(unittest.TestCase):
    """**「公開する木」を、2か所で別々に決めない**（正本 9節・2026-09-19）。

    `scripts/check_copy.py` は評価の語を見張り、
    `scripts/make_public_tree.py` は実際に木を作る。
    片方が `docs/` を見ていて、もう片方は入れていなかった。

    **直せないものを見張っていた。** `docs/letters/` は大阪府と
    国立国会図書館へ送った手紙の写しで、送った文そのもの。
    毎回鳴って、誰も見なくなる形だった。
    """

    def test_check_copyが見る木は公開する木に収まっている(self):
        import check_copy
        try:
            import make_public_tree as tree
        except ImportError:
            # **木を作る道具は金庫にだけ置く**（自分でそう名乗っている）。
            # 公開用の木には行かないので、そこでは比べようがない。
            # 落とすと、公開用の Actions が取りに行く前に止まる
            self.skipTest(
                "make_public_tree.py が無い。公開用の木を素で clone した"
                "ときは、これが正しい（木を作る道具は金庫にだけ置く）")
        見る = {rel for rel, _ in check_copy.walk(check_copy.HERE)}
        出す = set(tree.FILES)
        for top in tree.DIRS:
            for cur, dirs, files in os.walk(os.path.join(HERE, top)):
                rel_dir = os.path.relpath(cur, HERE).replace(os.sep, "/")
                if any(rel_dir == s or rel_dir.startswith(s + "/")
                       for s in tree.DIR_SKIP):
                    dirs[:] = []
                    continue
                dirs[:] = [d for d in dirs if d not in tree.DIR_SKIP]
                for name in files:
                    出す.add("%s/%s" % (rel_dir, name))
        # **workflow の中身は、木に入れないが check_copy が見てよい。**
        # `.github/` と、そこに入る前の控え（`scripts/public-workflow.yml`）。
        # どちらも公開用のリポジトリで動くものなので、3.3 が掛かる。
        # **直せないものではない**ので、鳴っても言い換えられる
        def は_workflowの中身(rel):
            return rel.startswith(".github/") or rel.endswith("-workflow.yml")

        はみ出し = sorted(r for r in 見る - 出す
                       if not は_workflowの中身(r))
        self.assertEqual(
            はみ出し, [],
            "check_copy が、公開用の木に行かないものを見張っている。"
            "**直せないものを見張ると、毎回鳴って誰も見なくなる**:\n"
            + "\n".join(はみ出し))


class 結果の語は落札と不調だけ(unittest.TestCase):
    """正本 6節（2026-09-19）。**「売却」「不売」「売却済み」とは書かない。**

    相手のページに書いてある語は別（`aggregate.SOLD` / `UNSOLD` は
    読むための照合語なので、そのまま残す）。
    ここが見るのは**こちらが書き出したもの**だけ。

    文章の中の語まで機械で見ると、出どころの名前（「BIT 売却スケジュール」）や
    制度の名前（「公有財産の売却」）まで鳴る。**名前として書いたもの**を見る。
    """

    NG = ("売却", "不売", "売却済")

    def test_升の段階に相手の語を使わない(self):
        import aggregate
        for 語 in set(aggregate.FAMILIES.parents) | set(aggregate.FAMILIES.children):
            for ng in self.NG:
                self.assertNotIn(ng, 語, "升の段階が相手の語になっている: %s" % 語)

    def test_書き出したファイルの段階に相手の語が無い(self):
        """**実物を読む。** 語彙を直しても、古い出力が残っていたら出る。"""
        kinko.need(self)
        for path, key in ((os.path.join(AGG, "monthly.json"), "stage"),
                          (os.path.join(PUBLIC, "index.json"), "kind")):
            if not os.path.exists(path):
                continue
            with io.open(path, encoding="utf-8") as f:
                d = json.load(f)
            升 = d.get("cells") or d.get("counts_by_city") or []
            for c in 升:
                for ng in self.NG:
                    self.assertNotIn(ng, c.get(key, ""),
                                     "%s に相手の語が出ている: %r"
                                     % (os.path.basename(path), c.get(key)))

    def test_公開する文章で名前として書いていない(self):
        """バッククォートで囲ったものは**名前**。そこに相手の語を置かない。

        囲っていない地の文は見ない（「BIT 売却スケジュール」のような
        出どころの名前まで鳴らすと、直せないものが鳴る）。
        """
        import re
        bad = []
        for name in ("README.md", "about.md", "DESIGN.md"):
            path = os.path.join(HERE, name)
            if not os.path.exists(path):
                continue
            with io.open(path, encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    for 名 in re.findall(r"`([^`\n]{1,20})`", line):
                        if 名 in ("売却", "不売", "売却済", "売却済み",
                                 "競売/売却", "競売/不売"):
                            bad.append("%s:%d `%s`" % (name, i, 名))
        self.assertEqual(bad, [],
                         "名前として相手の語を書いている（落札／不調に寄せる）:\n"
                         + "\n".join(bad))


if __name__ == "__main__":
    unittest.main()
