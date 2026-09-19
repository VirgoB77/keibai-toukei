#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""個人が特定できる出方をしていないか、公開ファイルを走査して確かめる。

正本 5節の「privacy.py を迂回した出力が1件でもあれば落ちる検査」。
壊れたら、データを取りに行く前に止まる。

    python3 -m unittest discover -s tests
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import make_cross  # noqa: E402
import make_index  # noqa: E402
from common import privacy  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 公開するファイル。ここに出たものは、もう引っ込められないと思って見る
PUBLIC_FILES = (
    os.path.join(ROOT, "data", "public", "index.json"),
    os.path.join(ROOT, "data", "agg", "monthly.json"),
    os.path.join(ROOT, "data", "cross", "atochi.json"),
)


class 法人か個人かを見分ける(unittest.TestCase):

    def test_法人格の語を見つける(self):
        for name in ("株式会社カネカ", "有限会社山田工務店", "合同会社みらい",
                     "相互会社あ", "生活協同組合コープ", "特定目的会社A",
                     "医療法人社団△△会", "公社", "○○機構", "○○公団",
                     "○○事業団", "農業協同組合"):
            self.assertTrue(privacy.is_corp(name), name)

    def test_確かめられないものは個人にする(self):
        # 推測で法人にしない。名前が無いときも個人扱い
        for name in ("山田太郎", "田中", "山田商店", "", None, "   "):
            self.assertFalse(privacy.is_corp(name), name)

    def test_個人の氏名は_個人_と書く(self):
        self.assertEqual(privacy.redact_name("山田太郎"), "個人")
        self.assertEqual(privacy.redact_name(""), "個人")
        self.assertEqual(privacy.redact_name("株式会社あ"), "株式会社あ")

    def test_indexのpartyは法人名だけ_個人は空文字(self):
        # 正本 6節は「個人は空文字」。画面に出す redact_name とは分けてある
        self.assertEqual(privacy.party_for_index("山田太郎"), "")
        self.assertEqual(privacy.party_for_index("株式会社あ"), "株式会社あ")


class 丸めたつもりで丸まっていない(unittest.TestCase):
    """**番地のうしろに何か付いている住所**（2026-09-19）。

    `addr` には建物名や2つ目の地番が残る（`common/addr.py` はわざと残す）。
    そこで丸め方が2つとも開いていた。

        後ろから探していた    町名が建物名にもう一度出ると、切る位置が飛ぶ
        末尾の数字だけ落とす  うしろに文字があると、1つも落ちない

    どちらも**丸めたつもりで地番がそのまま出る**。
    `records` が0件だから出ていないだけで、個票を出す日に効く。
    実データ106行のうち、番地のうしろに何か付いているのは15行。
    """

    def test_町名が建物名にもう一度出ても_前で切る(self):
        self.assertEqual(
            privacy.to_town("大阪市北区梅田1-1-1梅田1館", "梅田1"),
            "大阪市北区梅田1")

    def test_地番が2つ並んでも落ちる(self):
        # 実データの形。「東大阪市吉田6-627-3、627-13」
        self.assertEqual(
            privacy.to_town("東大阪市吉田6-627-3、627-13", "吉田6"),
            "東大阪市吉田6")
        self.assertEqual(
            privacy.to_town("東大阪市吉田6-627-3、627-13", ""),
            "東大阪市吉田")

    def test_建物名と部屋番号が付いていても落ちる(self):
        self.assertEqual(
            privacy.to_town("大阪市北区梅田1-1-1ハイツ101", ""),
            "大阪市北区梅田")

    def test_町丁目がこの住所のものでなければ_きつい側に倒す(self):
        """渡された町丁目が当たらないとき、**切らずに出さない。**"""
        self.assertEqual(
            privacy.to_town("大阪市北区南森町1-1-1ローレルコート本町", "本町"),
            "大阪市北区南森町")

    def test_見つからないときに市区町村名を消さない(self):
        """前は町丁目だけを返していた。**どこの町か分からなくなる。**"""
        self.assertEqual(
            privacy.to_town("西宮市上ケ原2番町3-5", "上ケ原二番町"),
            "西宮市上ケ原2番町")

    def test_町名の中の数字は残す(self):
        for 住所, 町 in (("西宮市甲子園7番町1-2-3", ""),
                         ("西宮市甲子園7番町1-2-3", "甲子園7番町"),
                         ("札幌市北区北12条西1-1-1", "")):
            self.assertIn("甲子園7番町" if "甲子園" in 住所 else "北12条西",
                          privacy.to_town(住所, 町), (住所, 町))

    def test_個票の道でも地番が出ない(self):
        """入口は `redact_addr`。individual のときだけここを通る。"""
        self.assertEqual(
            privacy.redact_addr("大阪市北区梅田1-1-1梅田1館",
                                privacy.INDIVIDUAL, "梅田1"),
            "大阪市北区梅田1")
        # 個人でなければ地番まで出してよい（正本 5節）
        self.assertEqual(
            privacy.redact_addr("大阪市北区梅田1-1-1梅田1館",
                                privacy.CORP, "梅田1"),
            "大阪市北区梅田1-1-1梅田1館")


class 住所を丸める(unittest.TestCase):

    def test_個人のときだけ町丁目に丸める(self):
        # 正本 5節: individual のときだけ丸める。ほかは地番まで
        self.assertEqual(
            privacy.redact_addr("大阪市北区梅田1-1-1", "individual"),
            "大阪市北区梅田")
        for kind in ("corp", "undisclosed", "none"):
            self.assertEqual(
                privacy.redact_addr("大阪市北区梅田1-1-1", kind),
                "大阪市北区梅田1-1-1", kind)

    def test_町名の中の数字は残す(self):
        self.assertEqual(
            privacy.redact_addr("西宮市甲子園7番町1-2", "individual"),
            "西宮市甲子園7番町")

    def test_地番が無ければそのまま(self):
        self.assertEqual(
            privacy.redact_addr("豊岡市城崎町湯島", "individual"),
            "豊岡市城崎町湯島")

    def test_跡地はもっと厳しい(self):
        # 共通仕様の下限より厳しくしてある。厳しいぶんは問題ない
        self.assertEqual(privacy.to_town("大阪市北区梅田1-1-1"), "大阪市北区梅田")

    def test_町丁目を渡せば丁目を落とさない(self):
        # 正規化したあとの文字列では、丁目の数字と番地の数字が同じ形になる。
        # 文字列だけで丸めると丁目まで落ちるので、normalize() が出した
        # 町丁目を渡す（正本 4節「丁目は必ず含める」）
        self.assertEqual(
            privacy.to_town("大阪市北区梅田1-1-1", "梅田1"), "大阪市北区梅田1")
        self.assertEqual(
            privacy.redact_addr("大阪市北区梅田1-1-1", "individual", "梅田1"),
            "大阪市北区梅田1")
        # 丁目が無い住所では、その数字は番地。町丁目に含めない
        self.assertEqual(
            privacy.to_town("大阪市北区角田町3-25", "角田町"), "大阪市北区角田町")

    def test_町丁目を渡さないときは粗いほうに倒す(self):
        # 渡せないときに丁目を推測で足さない。粗いほうがきつい側
        self.assertEqual(privacy.to_town("大阪市北区梅田1-1-1"), "大阪市北区梅田")


class 官公庁と氏名を取り違えない(unittest.TestCase):
    """末尾1字で官公庁を見分けると、ありふれた氏名がそろって法人に化ける。

    法人に化けると、氏名がそのまま index.json に出て、**地番も丸められない**。
    姉妹サイトが個人121件の地番を出した事故と、出口は同じ（正本 3.1）。
    """

    def test_村や町や道で終わる氏名は個人のまま(self):
        for name in ("中村", "西村", "木村", "川村", "山田弘道", "正道",
                     "三国", "山道", "田町", "中村太郎"):
            self.assertFalse(privacy.is_gov(name), name)
            self.assertFalse(privacy.is_corp(name), name)
            self.assertEqual(privacy.party_kind(name), "individual", name)

    def test_氏名は地番まで出さない(self):
        # 法人と取り違えると、ここが丸められなくなる
        self.assertEqual(
            privacy.redact_addr("大阪市北区梅田1-1-1",
                                privacy.party_kind("中村"), "梅田1"),
            "大阪市北区梅田1")

    def test_地方公共団体は法人として扱う(self):
        for name in ("大阪市", "兵庫県", "神戸市", "猪名川町",
                     "大阪市交通局", "猪名川町教育委員会"):
            self.assertTrue(privacy.is_gov(name), name)
            self.assertEqual(privacy.party_kind(name), "corp", name)

    def test_国の側も法人として扱う(self):
        for name in ("国土交通省", "近畿財務局", "大阪国税局", "神戸地方裁判所"):
            self.assertTrue(privacy.is_gov(name), name)

    def test_実在しない自治体名は当たらない(self):
        # 名指しの一覧で見分けるので、一覧に無いものは官公庁にならない
        for name in ("山田市", "架空町", "でたらめ村"):
            self.assertFalse(privacy.is_gov(name), name)

    def test_見張りは氏名を取りこぼさない(self):
        # 「市区町村県府都道」を1字ずつ除くと、ありふれた氏名が網から抜ける
        for name in ("中村花子", "西村健一", "山田弘道", "田中太郎"):
            self.assertTrue(privacy.looks_like_person_name(name), name)
        for name in ("大阪市", "大阪市交通局", "株式会社あ", "個人",
                     "土地", "工場", "近畿財務局"):
            self.assertFalse(privacy.looks_like_person_name(name), name)


class 小さい母数(unittest.TestCase):

    def test_件数は1と2をまとめる(self):
        self.assertEqual(privacy.bucket_count(1), "1-2")
        self.assertEqual(privacy.bucket_count(2), "1-2")
        self.assertEqual(privacy.bucket_count(0), 0)
        self.assertEqual(privacy.bucket_count(3), 3)

    def test_率は人口500人未満か件数が1件か2件で伏せる(self):
        self.assertTrue(privacy.suppress_rate(10, 499))
        self.assertTrue(privacy.suppress_rate(1, 10000))
        self.assertTrue(privacy.suppress_rate(2, 10000))
        self.assertTrue(privacy.suppress_rate(None, None))
        self.assertFalse(privacy.suppress_rate(3, 500))

    def test_0件は率も0を出す(self):
        """**伏せるのは率×人口で件数が戻るから。0件は戻るものが無い**（正本 3.2）。

        前は「2件以下」で書いてあったので 0 も伏せていた。そうすると
        0件の升が率の地図で灰色に落ち、「0件はいちばん薄い階級の色」と
        食い違う。
        """
        self.assertFalse(privacy.suppress_rate(0, 10000))
        # **人口が0なら、0件でも伏せる**（2026-09-19 に足した。3段の1段目）。
        # 率そのものが定義できない。0では割れない。
        # 姉妹サイトは、この1段目が無いまま0件を通してゼロ除算した
        self.assertTrue(privacy.suppress_rate(0, 0))
        self.assertTrue(privacy.suppress_rate(1, 0))
        self.assertTrue(privacy.suppress_rate(0, -1))
        # **人口の小ささも0件には効かない**（2026-09-19 に直した）。
        # 前はここが assertTrue で、**違反のほうを期待値に固定していた。**
        # docstring は「0件は戻るものが無い」と正しく書いてあったのに、
        # すぐ次の行がその逆を固定していた。実装と検査が同じ向きに
        # ずれていると、全部通ったまま何年でも残る
        self.assertFalse(privacy.suppress_rate(0, 400))
        self.assertFalse(privacy.suppress_rate(0, 1))


class 公開ファイルの見張り(unittest.TestCase):
    """出したあとのファイルを、そのまま走査する。"""

    def 読む(self, path):
        if not os.path.exists(path):
            self.skipTest("まだ %s が無い" % os.path.basename(path))
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def 値を全部たどる(self, node, path=""):
        if isinstance(node, dict):
            for k, v in node.items():
                yield from self.値を全部たどる(v, "%s.%s" % (path, k))
        elif isinstance(node, list):
            for i, v in enumerate(node):
                yield from self.値を全部たどる(v, "%s[%d]" % (path, i))
        else:
            yield path, node

    def test_個人名らしき値が残っていない(self):
        # **欄を名指しで選ばない。** 前は .party と .winner_name だけを見ていたが、
        # 列がずれて氏名が addr や title に入ったり、知らないキーに入ったりしたら
        # 素通りする。見張りは「どこに出ても拾う」でなければ意味がない
        for p in PUBLIC_FILES:
            if not os.path.exists(p):
                continue
            for where, value in self.値を全部たどる(self.読む(p)):
                if not isinstance(value, str):
                    continue
                self.assertFalse(
                    privacy.looks_like_person_name(value),
                    "%s の %s に個人名らしき値: %r" % (p, where, value))

    def test_見張りは欄の名前によらず拾う(self):
        # 上の走査が本当に拾えるかを、偽のファイルで確かめる。
        # ここが空振りしていると、見張りがあるのに何も守っていない状態になる
        にせ = {"records": [{"party": "", "addr": "大阪市北区梅田1",
                             "知らない欄": "中村花子"}]}
        当たり = [w for w, v in self.値を全部たどる(にせ)
                  if isinstance(v, str) and privacy.looks_like_person_name(v)]
        self.assertEqual(当たり, [".records[0].知らない欄"])

    def test_件数に1と2が実数で出ていない(self):
        for p in PUBLIC_FILES:
            if not os.path.exists(p):
                continue
            for where, value in self.値を全部たどる(self.読む(p)):
                if where.endswith(".count") or where.endswith(".unsold"):
                    self.assertNotIn(value, (1, 2),
                                     "%s の %s が実数のまま: %r" % (p, where, value))

    def test_跡地は細かいほうの鍵を出していない(self):
        p = os.path.join(ROOT, "data", "cross", "atochi.json")
        if not os.path.exists(p):
            self.skipTest("跡地ファイルはまだ止めてある")
        for where, _ in self.値を全部たどる(self.読む(p)):
            self.assertFalse(where.endswith(".addr_key"), where)


class 迂回していないか(unittest.TestCase):
    """出す値を作っている関数が、privacy.py を通しているか。"""

    def test_indexのpartyはprivacyを通している(self):
        self.assertIs(make_index.corp_name("株式会社あ").__class__, str)
        self.assertEqual(make_index.corp_name("山田太郎"), "")

    def test_跡地の住所はprivacyを通している(self):
        row = {"system": "koyu", "key": "k", "pref": "大阪府",
               "city": "大阪市北区", "address": "中津3丁目1番1号",
               "kind": "土地", "kind_raw": "工場", "zoning": "準工業地域",
               "area_sqm": 800, "status": "売却", "open_date": "2026-08-20",
               "sources": ["x"]}
        rec = make_cross.build([row])["records"][0]
        # 町丁目は「中津3」。丁目は町丁目の一部なので残す（正本 4節）。
        # 落とすのは番地（1番1号）だけ
        self.assertEqual(rec["addr"], "大阪市北区中津3")
        self.assertNotIn("3-1-1", rec["addr"])
        self.assertNotIn("1番1号", rec["addr"])


class 当事者の種類(unittest.TestCase):

    def test_法人はcorp(self):
        self.assertEqual(privacy.party_kind("株式会社あ"), "corp")

    def test_確かめられないものはindividual(self):
        # 名前が公表されていないときも個人扱い（正本 3.1）
        for name in ("山田太郎", "", None, "山田商店"):
            self.assertEqual(privacy.party_kind(name), "individual", name)

    def test_公表されていないものはundisclosed(self):
        # 競売・公売は裁判所も税務署も所有者名を公表していない。
        # 「個人だと分かった」のとは違うので分けて伝える
        self.assertEqual(privacy.party_kind("", disclosed=False), "undisclosed")
        self.assertEqual(privacy.party_kind("株式会社あ", disclosed=False),
                         "undisclosed")

    def test_当事者がいない制度はnone(self):
        # 開札の回の予定表のように、そもそも当事者がいないもの
        self.assertEqual(privacy.NONE, "none")

    def test_件数は2つ組で出す(self):
        # count は機械用、count_label は人用。両方いる（正本 6節）
        self.assertEqual(privacy.count_pair(12), (12, "12"))
        self.assertEqual(privacy.count_pair(2), (None, "1-2"))
        self.assertEqual(privacy.count_pair(1), (None, "1-2"))
        self.assertEqual(privacy.count_pair(0), (0, "0"))

    def test_indexのレコードに入る(self):
        idx = make_index.build([{
            "system": "koyu", "key": "k", "pref": "兵庫県", "city": "西宮市",
            "address": "甲子園町1番1号", "kind": "土地", "kind_raw": "工場",
            "winner_name": "株式会社あ", "sources": ["x"],
            "open_date": "2026-09-01", "last_seen": "2026-09-15",
        }], today="2026-09-15")
        self.assertEqual(idx["records"][0]["party_kind"], "corp")


class 丸囲みと括弧書き(unittest.TestCase):
    """★の4行を落とすと、公報と自治体の一覧表がほとんど読めない。

    大型店日報の実データ（設置者1,003種）では、
    ★を入れないと275種（27%）が「個人」に化けた。
    """

    def test_丸囲み(self):
        for name in ("㈱ライフコーポレーション", "三菱UFJ信託銀行㈱",
                     "㈲山田工務店", "㈳あ", "㈶い", "㈴う", "㈻え", "㈷お"):
            self.assertTrue(privacy.is_corp(name), name)

    def test_括弧書きは半角も全角も(self):
        for name in ("(株)あ", "（株）あ", "(有）山田工務店", "（有)い",
                     "(同)う", "(資)え", "(名)お", "(福)か", "(医)き", "(相)く"):
            self.assertTrue(privacy.is_corp(name), name)

    def test_潰れた表記の株(self):
        # 「株赤ちゃん本舗」。人名に「株」は出てこない
        self.assertTrue(privacy.is_corp("株赤ちゃん本舗"))

    def test_有は単独では法人にしない(self):
        # 有田・有村など姓に出る
        self.assertFalse(privacy.is_corp("有田花子"))
        self.assertFalse(privacy.is_corp("有村太郎"))

    def test_外国法人(self):
        for name in ("ABC Co., Ltd.", "XYZ Inc", "あ LLC", "い Corp",
                     "う K.K.", "え GmbH", "お Pty", "エルエルシーあ",
                     "かリミテッド", "きホールディングス"):
            self.assertTrue(privacy.is_corp(name), name)

    def test_カタカナだけは法人として扱う(self):
        # 戸籍の氏名はこの形にならない
        for name in ("オークワ", "オークワ ほか", "オークワ　ほか",
                     "イオンモール 他2名"):
            self.assertTrue(privacy.is_corp(name), name)

    def test_ローマ字入りは法人として扱う(self):
        self.assertTrue(privacy.is_corp("F.O.B COOP"))

    def test_国と地方公共団体(self):
        for name in ("大阪市", "兵庫県", "大阪市交通局", "西宮市教育委員会",
                     "近畿財務局"):
            self.assertTrue(privacy.is_corp(name), name)


class 個人に化けてはいけないもの(unittest.TestCase):

    def test_名前ではない文言はそのまま出す(self):
        for name in ("未定", "（未定）", "未定3者", "物品販売業を営む店舗", "―"):
            kind, reason = privacy.classify_party(name)
            self.assertEqual(kind, "none", name)
            self.assertEqual(reason, privacy.REASON_BOILERPLATE, name)

    def test_列がずれて住所が入ったものは印をつける(self):
        kind, reason = privacy.classify_party("大阪市北区角田町３番25号")
        self.assertEqual(kind, "individual")
        self.assertEqual(reason, privacy.REASON_ADDRESS)

    def test_切れた法人名を見分ける(self):
        # 同じデータの中の別の名前の先頭になっていたら、切れた法人名
        others = ["三井住友ファイナンス＆リース株式会社",
                  "大和ハウスリアルティマネジメント株式会社"]
        for name in ("三井住友ファイナンス", "大和ハウスリアルティ"):
            kind, reason = privacy.classify_party(name, others)
            self.assertEqual(kind, "individual", name)
            self.assertEqual(reason, privacy.REASON_TRUNCATED, name)

    def test_人名はほかの名前の頭にならない(self):
        others = ["三井住友ファイナンス＆リース株式会社", "山田花子"]
        kind, reason = privacy.classify_party("山田太郎", others)
        self.assertEqual(reason, privacy.REASON_PERSON)

    def test_切れた法人名を置き換えたり消したりしない(self):
        # 消すと「＆リース株式会社」だけが残る
        others = ["三井住友ファイナンス＆リース株式会社"]
        kind, _ = privacy.classify_party("三井住友ファイナンス", others)
        self.assertEqual(privacy.clean_name("三井住友ファイナンス"),
                         "三井住友ファイナンス")


class 正本5節の署名(unittest.TestCase):
    """**呼んでいなくても、署名があるものは置いてそろえる**（正本 5節）。

    使っていない関数のずれは、走らせても気づけない。
    次に使い始めた人が、古い版を使う。
    """

    def test_maskedは機械が持つ値(self):
        """`bucket_count()` は人に見せる文字列、`masked()` は機械が持つ値。"""
        self.assertEqual(privacy.masked(0), 0)
        self.assertIsNone(privacy.masked(1))
        self.assertIsNone(privacy.masked(2))
        self.assertEqual(privacy.masked(3), 3)
        self.assertEqual(privacy.masked(12), 12)
        self.assertIsNone(privacy.masked(None))

    def test_count_pairはmaskedと食い違わない(self):
        """判断は1か所。2か所に置くと、片方だけ直したときに気づけない。"""
        for n in (0, 1, 2, 3, 12, 100):
            count, label = privacy.count_pair(n)
            self.assertEqual(count, privacy.masked(n))
            self.assertEqual(label, str(privacy.bucket_count(n)))

    def test_署名そのものをそろえている(self):
        """**形も正本に合わせる**（2026-09-19、正本 PR #71）。

        中身が同じでも、引数の数が違えば「置いてそろえた」ことにならない。
        次に使い始めた人が、渡すつもりの引数を渡せない。
        """
        import inspect
        期待 = {
            "redact_name": "(name, names=())",
            "is_corp": "(name)",
            "party_for_index": "(name)",
            "redact_addr": "(addr, kind, town='')",
            "suppress_rate": "(count, population)",
            "masked": "(n)",
            "bucket_count": "(n)",
            "is_party_column": "(label)",
        }
        for 名, 形 in sorted(期待.items()):
            got = str(inspect.signature(getattr(privacy, 名)))
            self.assertEqual(got, 形, "%s の署名が正本とちがう" % 名)

    def test_namesは戻り値を1文字も変えない(self):
        """**伏せるかどうかを `names` に頼らせない**（正本 5節・PR #71）。

        頼った瞬間、渡し忘れが穴になる。`names` が変えるのは、
        呼ぶ側が付ける名札（気づくための引数）だけ。
        """
        for 名 in ("山田太郎", "", "株式会社あ", "不明"):
            self.assertEqual(privacy.redact_name(名),
                             privacy.redact_name(名, ("株式会社い", "田中")),
                             名)

    def test_suppress_rateは0件を伏せない(self):
        """伏せるのは率×人口で件数が戻るから。**0件は戻るものが無い。**"""
        self.assertFalse(privacy.suppress_rate(0, 1000))
        self.assertTrue(privacy.suppress_rate(1, 1000))
        self.assertTrue(privacy.suppress_rate(2, 1000))
        self.assertFalse(privacy.suppress_rate(3, 1000))
        # **順番が要る。3段。** 入れ替えると、どれかが逆を向く
        self.assertTrue(privacy.suppress_rate(0, 0))      # 1段目が勝つ
        # **人口が小さくても、0件は伏せない。** 戻る先が無い
        self.assertFalse(privacy.suppress_rate(0, 499))
        # 人口の条件は、件数が1件以上のときだけ効く
        self.assertTrue(privacy.suppress_rate(9, 499))

    def test_当事者の列名を4サイトぶん持っている(self):
        """**落とすと地番が出る側**なので、2サイト目を待たずに足す。"""
        for w in ("氏名", "名義", "代表者", "代表取締役", "届出者", "申請者",
                  "設置者", "小売業者", "事業者", "所有者", "世帯主",
                  "落札者", "落札者名", "契約相手方", "契約の相手方",
                  "買受人", "譲受人"):
            self.assertIn(w, privacy.PARTY_WORDS)
            self.assertTrue(privacy.is_party_column(w), w)

    def test_語を含んでも名前の欄でないものがある(self):
        """名前は列名の**末尾**に来る。「設置者対応」は当事者ではない。"""
        for lab in ("設置者対応", "設置者意見", "届出者数", "事業者区分",
                    "所有者の有無", "物件番号", "種類", ""):
            self.assertFalse(privacy.is_party_column(lab), lab)

    def test_語のうしろが名前なら当たる(self):
        for lab in ("所有者氏名", "落札者名", "契約の相手方"):
            self.assertTrue(privacy.is_party_column(lab), lab)


class 正本5節_residential_reason(unittest.TestCase):
    """人が住んでいるかもしれないか（正本 5節、2026-09-18）。

    3.1「人が住んでいる可能性があるものは個票にしない」を、
    人の判断ではなくコードで守るための層。
    開発系が実装し、こちらが「入札中物件は個票にしない」で同じ判断を
    持っていたので、5節の線3（2サイト目が要ると言ったら上げる）に当たった。
    """

    def test_正本の例(self):
        self.assertEqual(privacy.residential_reason("宅地 居宅 木造・平家建"),
                         "居住用途の建物")
        self.assertEqual(privacy.residential_reason("倉庫"), "")

    def test_並べる順は問わない(self):
        """呼ぶ側が欄をどう並べるかに、判定を依存させない。"""
        parts = ("宅地", "居宅", "木造・平家建")
        self.assertTrue(privacy.residential_reason(*parts))
        self.assertTrue(privacy.residential_reason(*reversed(parts)))
        self.assertTrue(privacy.residential_reason("居宅", None, "", "宅地"))

    def test_4サイトぶんの語を持っている(self):
        for w in ("居宅", "共同住宅", "集合住宅", "住宅", "マンション",
                  "アパート", "長屋", "寄宿舎", "寮", "社宅", "戸建",
                  "テラスハウス", "文化住宅"):
            self.assertTrue(privacy.residential_reason(w), w)

    def test_事業用と混じっても落とすほうを採る(self):
        self.assertTrue(privacy.residential_reason("宅地 店舗兼住宅"))

    def test_迷ったら空文字を返さない(self):
        """何も分からない行は、個票にしない側に倒す（正本 3.1）。"""
        self.assertTrue(privacy.residential_reason(""))
        self.assertTrue(privacy.residential_reason(None))

    def test_住まいでないものは空文字(self):
        for t in ("倉庫", "工場 工業地域", "雑種地", "田", "畑", "山林",
                  "駐車場", "店舗 商業地域"):
            self.assertEqual(privacy.residential_reason(t), "", t)

    def test_区分所有の部屋番号を拾う(self):
        self.assertTrue(privacy.residential_reason("○○市○○町12番13-1406号"))

    def test_落としすぎない(self):
        """**「○番街区」は住居表示の街区であって部屋番号ではない。**

        ここまで落とすと土地が1件も残らなくなる。
        """
        for t in ("○○市○○町5番街区", "○○市○○町3丁目5番地1",
                  "○○市大字○○112番1"):
            self.assertEqual(privacy.residential_reason(t), "", t)

    def test_実物の土地が落ちていないことを測る(self):
        """落としすぎていないかを、実物で測る（正本 5節）。"""
        import glob
        n_land = n_dropped = 0
        for path in glob.glob(os.path.join(ROOT, "data", "rows", "*", "*.json")):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for row in (data if isinstance(data, list) else data.get("rows", [])):
                if (row.get("kind") or "") != "土地":
                    continue
                n_land += 1
                if privacy.lived_in_reason(row):
                    n_dropped += 1
        if not n_land:
            self.skipTest("土地の行がまだ無い")
        self.assertLess(n_dropped, n_land,
                        "土地が1件も残っていない。落としすぎ（正本 5節）")

    def test_理由が残る(self):
        """**行を消さず、落とした理由を残す**（正本 5節）。"""
        row = {"kind": "戸建て", "address": "○○市○○町1番1"}
        self.assertTrue(privacy.is_lived_in(row))
        self.assertEqual(privacy.lived_in_reason(row), "居住用途の建物")
        row2 = {"kind": "土地", "zoning": "第一種低層住居専用地域",
                "address": "○○市○○町1番1"}
        self.assertEqual(privacy.lived_in_reason(row2), "住居系の用途地域")


class 読めなかった語を当事者がいない側に倒さない(unittest.TestCase):
    """正本5節の表の語は、**名前かどうか**と**当事者の扱い**が別（2026-09-19）。

    表に `未詳` `不明` `なし` `無し` が足されたとき、
    `is_boilerplate()`（名前かどうか）だけを見て
    `classify_party()`（当事者の扱い）を追わなかった。

        当てた後  不明 → ('none', …)  ← **地番まで出してよい側**

    `none` は「そもそも当事者を持たない制度のレコード」で、
    `redact_addr()` が住所をそのまま返す。
    「欄はあるが読めていない → individual（町丁目まで）」と逆を向いていた。

    **直したときに、この見張りを付けていなかった。**
    戻っても誰も気づかない形だったので、あとから足した。
    """

    住所 = "大阪市北区中津3-1-1"
    町丁目 = "大阪市北区中津3"

    def test_読めなかった語はindividual(self):
        """**きつい側。** 相手はいる。こちらが読めていないだけ。"""
        for w in privacy._PLACEHOLDER_UNKNOWN:
            kind, why = privacy.classify_party(w)
            self.assertEqual(kind, privacy.INDIVIDUAL,
                             "%s が %s に倒れている" % (w, kind))
            self.assertEqual(why, privacy.REASON_UNREADABLE, w)

    def test_読めなかった語で地番が出ない(self):
        """**これが実害。** 倒れると住所がそのまま出る。"""
        for w in privacy._PLACEHOLDER_UNKNOWN:
            kind, _ = privacy.classify_party(w)
            self.assertEqual(privacy.redact_addr(self.住所, kind, "中津3"),
                             self.町丁目, w)

    def test_当事者がいない語はnoneのまま(self):
        """未定・なし・該当なし は、そこに相手がいない。前と同じ扱い。"""
        for w in privacy._PLACEHOLDER_NONE:
            kind, _ = privacy.classify_party(w)
            self.assertEqual(kind, privacy.NONE, w)

    def test_表の語は全部名前ではない(self):
        """正本5節の表そのもの。**扱いが分かれても、名前でないのは同じ。**"""
        for w in privacy._PLACEHOLDER:
            self.assertTrue(privacy.is_boilerplate(w), w)
            self.assertNotEqual(privacy.redact_name(w), w,
                                "%s がそのまま出ている" % w)

    def test_2つの並びは重ならず表と同じ(self):
        """**片方に足してもう片方から漏れる**のを止める。"""
        self.assertEqual(set(privacy._PLACEHOLDER_NONE)
                         & set(privacy._PLACEHOLDER_UNKNOWN), set())
        self.assertEqual(set(privacy._PLACEHOLDER),
                         set(privacy._PLACEHOLDER_NONE)
                         | set(privacy._PLACEHOLDER_UNKNOWN))

    def test_確認ずみの無しとは別物(self):
        """`無し` と `無し（確認ずみ）` を取り違えない。

        あちらは「名前の欄が**無いと確かめた**」の印で、
        undisclosed（地番まで）を名乗れる唯一の条件。
        """
        self.assertTrue(privacy.is_unreadable("無し"))
        self.assertFalse(privacy.is_unreadable(privacy.NAME_COLUMN_ABSENT))
        self.assertFalse(privacy.is_boilerplate(privacy.NAME_COLUMN_ABSENT))

    def test_確認ずみの印は半角の括弧でも通る(self):
        """**書き方で黙って「未確認」に落ちない。**

        `NAME_COLUMN_ABSENT` は全角の括弧。半角で書かれた同じ意味の文字列が
        `未確認` に落ちると、地番まで出せる出どころが出せなくなる
        （倒れる向きはきつい側なので害は小さいが、確かめた人の仕事が消える）。
        """
        for w in ("無し（確認ずみ）", "無し(確認ずみ)", " 無し（確認ずみ） "):
            self.assertTrue(privacy.name_absent_confirmed(w), repr(w))
        for w in ("無し", "あり", "未確認", ""):
            self.assertFalse(privacy.name_absent_confirmed(w), repr(w))


if __name__ == "__main__":
    unittest.main()
