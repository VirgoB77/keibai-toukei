#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""保存したページからの読み取りを固定する。

日付の読み違いは、あとから気づきにくいわりに全部を狂わせる。
和暦の変換と、列の対応づけをここで縛る。

    python3 -m unittest discover -s tests
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import aggregate  # noqa: E402
import parse  # noqa: E402
from common import kanzen  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# BITの売却スケジュールと同じ形。★の列が「農地」
SCHEDULE_HTML = """<html><body>
<table>
<tr><th>農地</th><th>開札日</th><th>売却実施処分日</th><th>公告日</th>
    <th>閲覧開始日</th><th>入札開始日</th><th>入札終了日</th>
    <th>売却決定日</th><th>確定日</th><th>状態</th></tr>
<tr><td></td><td>R08/09/01</td><td>R08/07/15</td><td>R08/08/03</td>
    <td>R08/08/03</td><td>R08/08/19</td><td>R08/08/26</td>
    <td>R08/09/24</td><td>R08/10/02</td><td>終了</td></tr>
<tr><td>★</td><td>R08/09/01</td><td>R08/04/08</td><td>R08/04/27</td>
    <td>R08/04/27</td><td>R08/08/19</td><td>R08/08/26</td>
    <td>R08/12/15</td><td>R08/12/23</td><td>取消</td></tr>
<tr><td></td><td>R08/10/06</td><td>R08/08/19</td><td>R08/09/07</td>
    <td>R08/09/07</td><td>R08/09/24</td><td>R08/09/30</td>
    <td>R08/10/27</td><td>R08/11/05</td><td>閲覧可能</td></tr>
<tr><td></td><td></td><td></td><td></td><td></td><td></td><td></td>
    <td></td><td></td><td>見出しでも予定でもない行</td></tr>
</table></body></html>"""


class 和暦を直す(unittest.TestCase):

    def test_令和(self):
        # 令和1年が2019年。8年なら2026年
        self.assertEqual(parse.to_date("R08/09/01"), "2026-09-01")
        self.assertEqual(parse.to_date("R09/01/12"), "2027-01-12")
        self.assertEqual(parse.to_date("R1/5/1"), "2019-05-01")

    def test_平成と昭和(self):
        self.assertEqual(parse.to_date("H31/04/30"), "2019-04-30")
        self.assertEqual(parse.to_date("H10/1/1"), "1998-01-01")
        self.assertEqual(parse.to_date("S64/01/07"), "1989-01-07")

    def test_漢字の元号も読む(self):
        # スマホの画面はこの書き方。パソコンは R08/09/07。両方読めないと落ちる
        self.assertEqual(parse.to_date("令和08年09月07日"), "2026-09-07")
        self.assertEqual(parse.to_date("令和8年9月7日"), "2026-09-07")
        self.assertEqual(parse.to_date("平成31年04月30日"), "2019-04-30")

    def test_元年も読む(self):
        self.assertEqual(parse.to_date("令和元年5月1日"), "2019-05-01")

    def test_全角の数字も読む(self):
        self.assertEqual(parse.to_date("令和０８年０９月０７日"), "2026-09-07")

    def test_西暦の書き方も読む(self):
        self.assertEqual(parse.to_date("2026-09-01"), "2026-09-01")
        self.assertEqual(parse.to_date("2026/9/1"), "2026-09-01")
        self.assertEqual(parse.to_date("2026年9月1日"), "2026-09-01")

    def test_読めないものはNoneにする(self):
        for ng in ("", None, "未定", "―", "R08/09"):
            self.assertIsNone(parse.to_date(ng), ng)


class 売却スケジュールを読む(unittest.TestCase):

    def setUp(self):
        self.rows = parse.parse_bit_schedule(SCHEDULE_HTML, "33311")

    def test_予定の行だけ拾う(self):
        # 見出しと、開札日が空の行は入らない
        self.assertEqual(len(self.rows), 3)

    def test_日付がそろっている(self):
        r = self.rows[0]
        self.assertEqual(r["open_date"], "2026-09-01")
        self.assertEqual(r["disposal_date"], "2026-07-15")
        self.assertEqual(r["notice_date"], "2026-08-03")
        self.assertEqual(r["view_start"], "2026-08-03")
        self.assertEqual(r["bid_start"], "2026-08-19")
        self.assertEqual(r["bid_end"], "2026-08-26")
        self.assertEqual(r["decision_date"], "2026-09-24")
        self.assertEqual(r["confirm_date"], "2026-10-02")
        self.assertEqual(r["status"], "終了")

    def test_農地の回を見分ける(self):
        farm = [r for r in self.rows if r["farmland"]]
        self.assertEqual(len(farm), 1)
        self.assertEqual(farm[0]["status"], "取消")

    def test_同じ日に一般と農地があっても別の回になる(self):
        same = [r for r in self.rows if r["open_date"] == "2026-09-01"]
        self.assertEqual(len(same), 2)
        self.assertEqual({r["key"] for r in same},
                         {"33311:2026-09-01:一般", "33311:2026-09-01:農地"})

    def test_裁判所の番号が入る(self):
        for r in self.rows:
            self.assertEqual(r["court_id"], "33311")

    def test_開札日の順に並ぶ(self):
        dates = [r["open_date"] for r in self.rows]
        self.assertEqual(dates, sorted(dates))

    def test_列の並びが変わっても文字で見分ける(self):
        # 位置で決め打ちしていたら、ここで落ちる
        html = SCHEDULE_HTML.replace(
            "<th>農地</th><th>開札日</th>", "<th>開札日</th><th>農地</th>"
        ).replace("<td></td><td>R08/09/01</td>", "<td>R08/09/01</td><td></td>")
        rows = parse.parse_bit_schedule(html, "33311")
        self.assertEqual(rows[0]["open_date"], "2026-09-01")

    def test_同じ回が2度出てきても1つにする(self):
        rows = parse.parse_bit_schedule(SCHEDULE_HTML + SCHEDULE_HTML, "33311")
        self.assertEqual(len(rows), 3)


class 表の読み取り(unittest.TestCase):

    def test_台本の中の文字は拾わない(self):
        html = "<table><tr><td>あ<script>var x='い';</script></td></tr></table>"
        self.assertEqual(parse.tables_of(html), [[["あ"]]])

    def test_空の行は落とす(self):
        html = "<table><tr><td></td><td></td></tr><tr><td>あ</td></tr></table>"
        self.assertEqual(parse.tables_of(html), [[["あ"]]])




class 結合セルを広げる(unittest.TestCase):
    """広げずに読むと、値が空になるのではなく**隣の値が入る**。

    面積や金額が黙って別の数字に化けるので、いちばん怖い種類のずれ。
    """

    def test_横の結合を広げる(self):
        html = ("<table><tr><td colspan='2'>あ</td><td>い</td></tr>"
                "<tr><td>1</td><td>2</td><td>3</td></tr></table>")
        self.assertEqual(parse.tables_of(html),
                         [[["あ", "あ", "い"], ["1", "2", "3"]]])

    def test_縦の結合を広げる(self):
        html = ("<table><tr><td rowspan='2'>あ</td><td>1</td></tr>"
                "<tr><td>2</td></tr></table>")
        self.assertEqual(parse.tables_of(html),
                         [[["あ", "1"], ["あ", "2"]]])

    def test_広げないと隣の値が入ってしまう(self):
        # 1行目に縦結合があると、2行目の「面積」の位置に「価格」が来る
        html = ("<table>"
                "<tr><th>裁判所</th><th>面積</th><th>価格</th></tr>"
                "<tr><td rowspan='2'>神戸</td><td>100</td><td>500</td></tr>"
                "<tr><td>200</td><td>600</td></tr>"
                "</table>")
        t = parse.tables_of(html)[0]
        self.assertEqual(t[1], ["神戸", "100", "500"])
        self.assertEqual(t[2], ["神戸", "200", "600"])   # 面積が200のまま

    def test_縦と横が混ざっても広げる(self):
        html = ("<table>"
                "<tr><td rowspan='2' colspan='2'>あ</td><td>1</td></tr>"
                "<tr><td>2</td></tr></table>")
        self.assertEqual(parse.tables_of(html),
                         [[["あ", "あ", "1"], ["あ", "あ", "2"]]])

    def test_おかしな数は1として扱う(self):
        html = "<table><tr><td rowspan='abc' colspan='-5'>あ</td></tr></table>"
        self.assertEqual(parse.tables_of(html), [[["あ"]]])


# 2026-09-16 に実物の写真で確認したカードの形。スマホ表示（ラベルと値が上下に積む）。
# パソコンでは横2列になるが、ラベル→値の順番は同じ。
CARD_HTML = """<html><body>
<h2>競売物件検索結果一覧</h2>
<p>41件中　1-10　件</p>
<div class="card">
  <span class="badge">土地</span>
  <a href="/app/detail/pd001/h04?courtId=33111">大阪地方裁判所本庁　令和06年(ケ)第414号</a>
  <button>お問い合わせ</button>
  <p>期間入札</p>
  <table>
    <tr><th>閲覧開始日</th></tr><tr><td>令和08年08月12日</td></tr>
    <tr><th>入札期間</th></tr><tr><td>令和08年10月21日〜令和08年10月29日</td></tr>
    <tr><th>開札期日</th></tr><tr><td>令和08年11月05日</td></tr>
    <tr><th>特別売却期間</th></tr><tr><td>実施しておりません。</td></tr>
  </table>
  <p>売却基準価額 <span>1,710,000円</span></p>
  <p>買受申出保証金 <span>342,000円</span></p>
  <p>茨木市大字安元１１２番1</p>
  <p>阪急京都本線　茨木市駅　北西方　道路距離　約１１．３ｋｍ</p>
  <table>
    <tr><th>物件番号．種別</th></tr>
    <tr><td>1．土地（農地） 2．土地（農地）</td></tr>
    <tr><th>地目</th></tr><tr><td>田</td></tr>
    <tr><th>用途地域</th></tr><tr><td>市街化調整区域</td></tr>
    <tr><th>床面積</th></tr><tr><td>－</td></tr>
    <tr><th>間取り</th></tr><tr><td>－</td></tr>
  </table>
</div>
<div class="card">
  <span class="badge">戸建て</span>
  <a href="/app/detail/pd001/h04?courtId=33111">大阪地方裁判所本庁　令和08年(ケ)第165号</a>
  <p>期間入札</p>
  <table>
    <tr><th>閲覧開始日</th></tr><tr><td>令和08年09月02日</td></tr>
    <tr><th>入札期間</th></tr><tr><td>令和08年09月16日〜令和08年09月25日</td></tr>
    <tr><th>開札期日</th></tr><tr><td>令和08年10月02日</td></tr>
    <tr><th>特別売却期間</th></tr><tr><td>実施しておりません。</td></tr>
  </table>
  <p>売却基準価額 <span>－円</span></p>
  <p>買受申出保証金 <span>－円</span></p>
  <table>
    <tr><th>物件番号．種別</th></tr>
    <tr><td>1．土地 2．建物（所有権）</td></tr>
    <tr><th>用途地域</th></tr><tr><td>－</td></tr>
    <tr><th>床面積</th></tr><tr><td>－</td></tr>
    <tr><th>間取り</th></tr><tr><td>－</td></tr>
    <tr><th>中止情報</th></tr><tr><td>取下</td></tr>
  </table>
</div>
</body></html>"""


class カードの一覧を読む(unittest.TestCase):
    """BITの一覧は表ではなくカードだった（実物の写真で確認）。"""

    def setUp(self):
        self.rows, self.unknown = parse.parse_bit_list(
            CARD_HTML, "33111", "https://example/x", "2026-09-16")

    def test_事件が2つ_物件は4つになる(self):
        # 1つの事件に物件が複数ぶら下がる。行データは物件ごとに作る
        self.assertEqual(len(self.rows), 4)
        self.assertEqual(len({r["case_no"] for r in self.rows}), 2)

    def test_見出しから裁判所名と事件番号を取る(self):
        r = [x for x in self.rows if x["case_no"] == "令和06年(ケ)第414号"][0]
        self.assertEqual(r["court_name"], "大阪地方裁判所本庁")
        self.assertEqual(r["court_id"], "33111")

    def test_日付と入札期間(self):
        r = [x for x in self.rows if x["case_no"] == "令和06年(ケ)第414号"][0]
        self.assertEqual(r["view_start"], "2026-08-12")
        self.assertEqual(r["bid_start"], "2026-10-21")
        self.assertEqual(r["bid_end"], "2026-10-29")
        self.assertEqual(r["open_date"], "2026-11-05")

    def test_値段(self):
        r = [x for x in self.rows if x["case_no"] == "令和06年(ケ)第414号"][0]
        self.assertEqual(r["base_price"], 1710000)
        self.assertEqual(r["deposit"], 342000)

    def test_取下げ済みは値段が空になる(self):
        # 「－円」と出る。0円ではない
        r = [x for x in self.rows if x["case_no"] == "令和08年(ケ)第165号"][0]
        self.assertIsNone(r["base_price"])

    def test_中止情報から取下げを拾う(self):
        r = [x for x in self.rows if x["case_no"] == "令和08年(ケ)第165号"][0]
        self.assertEqual(r["status"], "取下げ")

    def test_中止情報が無ければ状態は空(self):
        r = [x for x in self.rows if x["case_no"] == "令和06年(ケ)第414号"][0]
        self.assertEqual(r["status"], "")

    def test_所在地と市区町村(self):
        r = [x for x in self.rows if x["case_no"] == "令和06年(ケ)第414号"][0]
        self.assertEqual(r["address"], "茨木市大字安元１１２番1")
        self.assertEqual((r["pref"], r["city"]), ("大阪府", "茨木市"))

    def test_地目と用途地域(self):
        r = [x for x in self.rows if x["case_no"] == "令和06年(ケ)第414号"][0]
        self.assertEqual(r["chimoku"], "田")
        self.assertEqual(r["zoning"], "市街化調整区域")

    def test_物件番号ごとに種別を持つ(self):
        r = sorted([x for x in self.rows
                    if x["case_no"] == "令和08年(ケ)第165号"],
                   key=lambda x: x["item_no"])
        self.assertEqual([x["item_no"] for x in r], ["1", "2"])
        self.assertEqual(r[0]["kind_raw"], "土地")
        self.assertEqual(r[1]["kind_raw"], "建物（所有権）")

    def test_種別を4つに寄せる(self):
        r = [x for x in self.rows if x["case_no"] == "令和06年(ケ)第414号"][0]
        self.assertEqual(r["kind"], "土地")      # 「土地（農地）」→ 土地

    def test_鍵は事件番号と物件番号と回(self):
        r = [x for x in self.rows if x["case_no"] == "令和06年(ケ)第414号"][0]
        self.assertEqual(r["property_key"], "33111:令和06年(ケ)第414号:1")
        self.assertEqual(r["key"], "33111:令和06年(ケ)第414号:1:2026-11-05")

    def test_名前の列が無いことを報告する(self):
        # 欄が無いのか読めていないのか分からない。決めつけずに知らせる
        self.assertTrue(any("名前らしき列" in u for u in self.unknown))

    def test_出典と取得日が全部に入る(self):
        for r in self.rows:
            self.assertEqual(r["source_url"], "https://example/x")
            self.assertEqual(r["fetched_on"], "2026-09-16")


class 物件番号の分け方(unittest.TestCase):

    def test_複数の物件を分ける(self):
        self.assertEqual(parse.split_items("1．土地（農地） 2．土地（農地）"),
                         [("1", "土地（農地）"), ("2", "土地（農地）")])
        self.assertEqual(parse.split_items("1．土地 2．建物（所有権）"),
                         [("1", "土地"), ("2", "建物（所有権）")])

    def test_1つだけのときも読む(self):
        self.assertEqual(parse.split_items("1．マンション"),
                         [("1", "マンション")])

    def test_空なら空(self):
        self.assertEqual(parse.split_items(""), [])


class 種別が隣のカードとずれない(unittest.TestCase):
    """種別のバッジはカードの見出しより**手前**に出る。

    見出しを見てから拾うと1枚ずれて、隣のカードの種別が入る。
    ずれ方が「空になる」ではなく「隣の値が入る」ので気づきにくい（正本 9節）。
    """

    def 一覧(self, 種別):
        return "".join(
            "<div><p>%s</p><p>大阪地方裁判所本庁　令和06年(ケ)第%d号</p>"
            "<dl><dt>開札期日</dt><dd>令和08年11月05日</dd></dl>"
            "<p>茨木市大字安元%d番1</p></div>" % (b, 400 + i, i + 1)
            for i, b in enumerate(種別))

    def test_カードごとの種別が合っている(self):
        rows, _ = parse.parse_bit_list(
            self.一覧(["土地", "マンション", "戸建て"]), "33111")
        self.assertEqual([(r["case_no"][-4:], r["kind"]) for r in rows],
                         [("400号", "土地"), ("401号", "マンション"),
                          ("402号", "戸建て")])

    def test_最初のカードの種別が捨てられない(self):
        rows, _ = parse.parse_bit_list(self.一覧(["マンション", "土地"]), "33111")
        self.assertEqual(rows[0]["kind"], "マンション")

    def test_最後のカードの種別が空にならない(self):
        rows, _ = parse.parse_bit_list(self.一覧(["土地", "戸建て"]), "33111")
        self.assertEqual(rows[-1]["kind"], "戸建て")


class 知らない見出しを黙って捨てない(unittest.TestCase):
    """正本 9節「知らないものを黙って捨てない」。

    知っている語だけを見出しとして扱うと、**知らない見出しは永久に見つからない**。
    見つからなければ parse-unknown.md には何も出ず、様式が変わったことに
    何年も気づかないまま歯抜けのデータが積み上がる。
    """

    カード = ("<div><p>大阪地方裁判所本庁　令和06年(ケ)第414号</p><dl>"
              "<dt>開札期日</dt><dd>令和08年11月05日</dd>"
              "<dt>売却基準価額</dt><dd>1,710,000円</dd>"
              "<dt>見たことのない見出し</dt><dd>とても大事な値</dd>"
              "</dl><p>茨木市大字安元１１２番1</p></div>")

    def test_知らない見出しを見つける(self):
        _rows, unknown = parse.parse_bit_list(self.カード, "33111")
        self.assertIn("見たことのない見出し", unknown)

    def test_知らない見出しの値を残す(self):
        # 見出しの名前だけ控えて値を捨てると、あとから取り直しになる
        rows, _ = parse.parse_bit_list(self.カード, "33111")
        self.assertEqual(rows[0]["extra"],
                         {"見たことのない見出し": "とても大事な値"})

    def test_知っている見出しはこれまでどおり読む(self):
        rows, _ = parse.parse_bit_list(self.カード, "33111")
        self.assertEqual(rows[0]["open_date"], "2026-11-05")
        self.assertEqual(rows[0]["base_price"], 1710000)

    def test_知っている見出しだけのときextraは空(self):
        html = ("<div><p>大阪地方裁判所本庁　令和06年(ケ)第414号</p><dl>"
                "<dt>開札期日</dt><dd>令和08年11月05日</dd></dl>"
                "<p>茨木市大字安元１１２番1</p></div>")
        rows, _ = parse.parse_bit_list(html, "33111")
        self.assertEqual(rows[0]["extra"], {})


class BITの検索結果の組み方(unittest.TestCase):
    """実物（大阪地裁本庁41件・2026-09-16）で分かった組み方を固定する。

    見出しは dt/th ではなく `<div class="bit__result_InfoHeader">`。
    値が空の欄（マンションの用途地域は中身が `<br>` だけ）があり、
    そこを見ないと1つずつずれて隣の欄の値が入る。
    住所は本物を使わない。組み方だけ写す。
    """

    カード = (
        '<div><div class="bit__result_kindBadge">マンション</div>'
        '<p>大阪地方裁判所本庁　令和06年(ケ)第1号</p>'
        '<div class="bit__result_InfoHeader">開札期日</div><div>令和08年10月02日</div>'
        '<div class="bit__result_InfoHeader">売却基準価額</div><div>13,090,000円</div>'
        '<div class="bit__result_InfoHeader">物件番号．種別</div>'
        '<div>1 ．区分所有建物（所有権）</div>'
        '<div class="bit__result_InfoHeader">種類</div><div>居宅</div>'
        '<div class="bit__result_InfoHeader">用途地域</div><div><br></div>'
        '<div class="bit__result_InfoHeader">専有面積</div><div>23.28m<sup>2</sup></div>'
        '<div class="bit__result_InfoHeader">中止情報</div><div><br></div>'
        '<p>大阪市西区９９９番9</p></div>'
        '<div><div class="bit__result_kindBadge">土地</div>'
        '<p>大阪地方裁判所本庁　令和06年(ケ)第2号</p>'
        '<div class="bit__result_InfoHeader">開札期日</div><div>令和08年10月02日</div>'
        '<div class="bit__result_InfoHeader">物件番号．種別</div><div>1 ．土地</div>'
        '<p>豊中市９９９番9</p></div>'
    )

    def setUp(self):
        self.rows, self.unknown = parse.parse_bit_list(self.カード, "33111")

    def test_見出しはdivのclassで決まる(self):
        # dt/th だけを見ていたころは、種類も専有面積も丸ごと落ちていた
        self.assertEqual(self.rows[0]["shurui"], "居宅")
        self.assertEqual(self.rows[0]["floor_sqm"], 23.28)

    def test_値が空の欄でずれない(self):
        # 用途地域の中身は <br> だけ。次に来るのは「専有面積」という見出し。
        # ここを見ないと 用途地域＝"専有面積" になる
        self.assertEqual(self.rows[0].get("zoning") or "", "")

    def test_最後の欄が次のカードのバッジを食わない(self):
        # 中止情報が空のとき、次のカードの「土地」を値として拾っていた
        self.assertEqual(self.rows[0].get("status") or "", "")

    def test_種別はバッジで決まる(self):
        # 「物件番号．種別」は登記上の分類。実物41件のうち22件が
        # バッジ「戸建て」／種別「土地」だった
        self.assertEqual([r["kind"] for r in self.rows], ["マンション", "土地"])

    def test_知らない見出しは無かった(self):
        # 名前の欄が無いという報告だけが残る（下のテスト）。列の取りこぼしは0
        self.assertEqual([u for u in self.unknown if "名前" not in u], [])

    def test_名前の欄が無いことを報告する(self):
        # 物件一覧は「これから売るもの」の一覧なので、買受人の欄が無い。
        # **無いことを確かめずに undisclosed を名乗ると、地番が出る**（正本 3.1）。
        # 欄が見つからなかったことを人に知らせて、個人（町丁目まで）に倒したままにする
        self.assertTrue(any("名前" in u for u in self.unknown), self.unknown)
        for r in self.rows:
            self.assertEqual(r["name_column"], "未確認")

    def test_名前の欄の有無はカードの見出しだけで見る(self):
        # 実物のページには検索条件に「占有者が債務者・所有者」という文言があり、
        # ページ中の文字を全部見ていたころは、これが当たって警告が消えていた。
        # 警告が消えると、欄が無いことを人が確かめる機会がなくなる（正本 3.1）
        まぎらわしい = ('<div><p>占有者が債務者・所有者</p>' + self.カード + '</div>')
        _rows, unknown = parse.parse_bit_list(まぎらわしい, "33111")
        self.assertTrue(any("名前" in u for u in unknown), unknown)

    def test_本当に買受人の欄があれば警告しない(self):
        あり = self.カード.replace(
            '<div class="bit__result_InfoHeader">種類</div><div>居宅</div>',
            '<div class="bit__result_InfoHeader">買受人</div>'
            '<div>株式会社ほげ</div>', 1)
        rows, unknown = parse.parse_bit_list(あり, "33111")
        self.assertFalse(any("名前" in u for u in unknown), unknown)
        self.assertEqual(rows[0]["winner_name"], "株式会社ほげ")

    def test_住所から市区町村を引く(self):
        self.assertEqual([r["city"] for r in self.rows],
                         ["大阪市西区", "豊中市"])


class 置き場所を間違えても混ざらない(unittest.TestCase):
    """振り分けはフォルダ名ではなく、カードに書いてある裁判所名で決める。

    人が置き場所を間違えても、別の庁の物件が混ざらない。
    置く人に正しいフォルダを覚えさせるより、こちらが読んで決めるほうが確か。
    """

    def test_名前をそろえて引ける(self):
        self.assertEqual(parse.court_name_key("BIT 売却スケジュール 神戸地裁 尼崎支部"),
                         "神戸地方裁判所尼崎支部")
        self.assertEqual(parse.court_name_key("大阪地裁 姫路支部（court_id 推定）"),
                         "大阪地方裁判所姫路支部")
        self.assertEqual(parse.court_name_key("大阪地方裁判所 本庁"),
                         "大阪地方裁判所本庁")

    def test_sources_jsonの全庁を引ける(self):
        import json as _json
        with open(os.path.join(ROOT, "sources.json"), encoding="utf-8") as f:
            sources = _json.load(f)["sources"]
        m = parse.court_map(sources)
        for src in sources:
            if src.get("kind") == "bit-schedule" and src.get("court_id"):
                self.assertIn(parse.court_name_key(src["name"]), m)

    def test_カードの裁判所名で振り分ける(self):
        import json as _json
        with open(os.path.join(ROOT, "sources.json"), encoding="utf-8") as f:
            m = parse.court_map(_json.load(f)["sources"])
        # 実物のカードに出る形
        for name, want in (("神戸地方裁判所本庁", "33311"),
                           ("神戸地方裁判所尼崎支部", "33331"),
                           ("神戸地方裁判所姫路支部", "33332"),
                           ("大阪地方裁判所本庁", "33111")):
            self.assertEqual(m.get(parse.court_name_key(name)), want, name)


class 頼まない裁判所(unittest.TestCase):
    """閲覧可能・入札期間中の回が無い庁は、開いても一覧が空になる。

    無いものを頼むと、人は開いて「なかった」と確かめる手間だけ使う
    （正本 3.4「人に渡すのは該当するURLだけ」）。
    """

    def setUp(self):
        import shutil
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.keep = parse.SCHEDULE_DIR
        self.addCleanup(setattr, parse, "SCHEDULE_DIR", self.keep)
        parse.SCHEDULE_DIR = self.tmp

    def 置く(self, court_id, statuses):
        import json as _json
        rows = [{"open_date": "2026-10-0%d" % (i + 1), "status": st,
                 "bid_end": "2026-09-30"} for i, st in enumerate(statuses)]
        with open(os.path.join(self.tmp, "%s.json" % court_id), "w",
                  encoding="utf-8") as f:
            _json.dump({"court_id": court_id, "rows": rows}, f,
                       ensure_ascii=False)

    def test_閲覧可能な回があれば頼む(self):
        self.置く("33311", ["終了", "閲覧可能"])
        self.assertTrue(parse.live_rounds("33311"))

    def test_入札期間中の回があれば頼む(self):
        self.置く("33111", ["入札期間中"])
        self.assertTrue(parse.live_rounds("33111"))

    def test_終了と取消しか無ければ頼まない(self):
        self.置く("33131", ["終了", "取消", ""])
        self.assertEqual(parse.live_rounds("33131"), [])

    def test_予定表が無ければ頼まない(self):
        self.assertEqual(parse.live_rounds("99999"), [])


class 置いてもらったものが読めたか(unittest.TestCase):
    """人が手で保存したページが読めなかったとき、黙って捨てない（正本 3.4・9節）。

    実際にここで詰まった。検索する前の画面が置かれ、0件になり、
    それでも台帳は「取り込み済み」と書いた。置いた人には何も届かなかった。
    """

    def test_検索する前の画面を見分ける(self):
        画面 = "ブロックから探す 地域から探す 沿線から探す 裁判所から探す 検索条件"
        why = parse.diagnose_list(画面, [])
        self.assertIn("検索する前の画面", why)

    def test_読めたときは何も言わない(self):
        self.assertEqual(parse.diagnose_list("ブロックから探す 裁判所から探す",
                                             [{"key": "x"}]), "")

    def test_形が変わったときは別の言い方をする(self):
        # 検索はしたのにカードが0枚。保存し直しても直らないので、そう言う
        why = parse.diagnose_list("大阪地方裁判所本庁 令和06年(ケ)第414号", [])
        self.assertNotIn("検索する前の画面", why)
        self.assertIn("読み取り", why)

    def test_読み取りが無い種類は頼まない(self):
        # 頼んで置いてもらっても捨てるだけになり、しかも催促が止まる
        self.assertEqual(tuple(parse.INBOX_READABLE), ("list",))
        for kind in ("result", "withdrawn"):
            self.assertIn(kind, parse.INBOX_WANTED)
            self.assertNotIn(kind, parse.INBOX_READABLE)

    def test_一覧は物件検索のページから頼む(self):
        # 売却スケジュールのページには物件が1件も載っていない。
        # そちらのURLを渡すと、人は物件のいない画面を保存することになる
        self.assertIn("court/ps004", parse.BIT_LIST_URL)
        self.assertNotIn("schedule", parse.BIT_LIST_URL)


class 台帳は中身が取れたものだけ(unittest.TestCase):
    """「取り込み済み」は、置いてあることではなく**中身が取れたこと**。

    置いてあるだけで取り込み済みにすると、1件も入っていないのに
    二度と催促されなくなる（正本 3.4）。
    """

    def setUp(self):
        import contextlib
        import io as _io
        import json
        import shutil
        import tempfile
        # chase_inbox は人に向けて1行出す。テストの画面を汚さないように伏せる
        _quiet = contextlib.redirect_stdout(_io.StringIO())
        _quiet.__enter__()
        self.addCleanup(_quiet.__exit__, None, None, None)
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.json = json
        self.keep = {k: getattr(parse, k)
                     for k in ("HERE", "INBOX_DIR", "LEDGER", "TODO",
                               "ROWS_DIR", "SCHEDULE_DIR", "FOCUS_COURT")}
        parse.HERE = self.tmp
        parse.INBOX_DIR = os.path.join(self.tmp, "inbox")
        parse.LEDGER = os.path.join(self.tmp, "inbox-ledger.json")
        parse.TODO = os.path.join(self.tmp, "inbox-todo.md")
        parse.ROWS_DIR = os.path.join(self.tmp, "rows")
        parse.SCHEDULE_DIR = os.path.join(self.tmp, "schedule")
        os.makedirs(parse.SCHEDULE_DIR)
        self.addCleanup(lambda: [setattr(parse, k, v)
                                 for k, v in self.keep.items()])

    def 置く(self, court_id, kind, day="2026-09-15"):
        d = os.path.join(parse.INBOX_DIR, "keibai", court_id)
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, "%s-%s.html" % (day, kind))
        with open(path, "w", encoding="utf-8") as f:
            f.write("<html></html>")
        return "inbox/keibai/%s/%s-%s.html" % (court_id, day, kind)

    def 台帳(self):
        with open(parse.LEDGER, encoding="utf-8") as f:
            return self.json.load(f)["取り込み済み"]

    def test_中身が取れなければ台帳に入らない(self):
        rel = self.置く("33311", "list")
        parse.FOCUS_COURT = "33111"
        parse.chase_inbox([("33111", "大阪地裁本庁"), ("33311", "神戸地裁本庁")],
                          ingested=[], troubles={rel: "検索する前の画面でした"})
        self.assertEqual(self.台帳(), [])

    def test_中身が取れたら台帳に入る(self):
        rel = self.置く("33311", "list")
        parse.FOCUS_COURT = ""
        parse.chase_inbox([("33311", "神戸地裁本庁")], ingested=[rel])
        self.assertEqual(self.台帳(), [rel])

    def test_取れていないのに取り込み済みだった分は落ちる(self):
        # 前のやり方で入ってしまった分を、そのままにしない
        rel = self.置く("33311", "list")
        with open(parse.LEDGER, "w", encoding="utf-8") as f:
            self.json.dump({"取り込み済み": [rel]}, f)
        parse.FOCUS_COURT = ""
        parse.chase_inbox([("33311", "神戸地裁本庁")],
                          ingested=[], troubles={rel: "検索する前の画面でした"})
        self.assertEqual(self.台帳(), [])

    def test_片づけて消えたものは取り込み済みのまま(self):
        # inbox/done/ に移したものを、もう一度頼まない
        with open(parse.LEDGER, "w", encoding="utf-8") as f:
            self.json.dump({"取り込み済み": ["inbox/keibai/33311/2026-01-01-list.html"]}, f)
        parse.FOCUS_COURT = ""
        parse.chase_inbox([("33311", "神戸地裁本庁")], ingested=[])
        self.assertEqual(self.台帳(),
                         ["inbox/keibai/33311/2026-01-01-list.html"])

    def test_置いてくれた裁判所は1庁に絞っても隠さない(self):
        # ここを外すと、置いたのに「検索する前の画面でした」が届かない
        rel = self.置く("33311", "list")
        parse.FOCUS_COURT = "33111"
        parse.chase_inbox([("33111", "大阪地裁本庁"), ("33311", "神戸地裁本庁")],
                          ingested=[], troubles={rel: "検索する前の画面でした"})
        with open(parse.TODO, encoding="utf-8") as f:
            todo = f.read()
        self.assertIn("33311", todo)
        self.assertIn("検索する前の画面", todo)

    def test_読み取りが無い種類は催促の紙に出さない(self):
        self.置く("33111", "result")
        parse.FOCUS_COURT = ""
        parse.chase_inbox([("33111", "大阪地裁本庁")], ingested=[])
        with open(parse.TODO, encoding="utf-8") as f:
            todo = f.read()
        self.assertNotIn("-result.html", todo)
        self.assertEqual(self.台帳(), [])


# BITのページ送り。**目に見えない文字**が実物と同じ形で入っている。
# 最後のカードの「中止情報」が空のまま終わり、そのすぐ後ろにこれが来る。
PAGER_HTML = """<html><body>
<h2>競売物件検索結果一覧</h2>
<div class="card">
  <span class="badge">マンション</span>
  <a href="/app/detail/pd001/h03?courtId=33332">神戸地裁姫路支部　令和08年(ケ)第99号</a>
  <p>期間入札</p>
  <table>
    <tr><th>閲覧開始日</th></tr><tr><td>令和08年08月12日</td></tr>
    <tr><th>入札期間</th></tr><tr><td>令和08年10月21日〜令和08年10月29日</td></tr>
    <tr><th>開札期日</th></tr><tr><td>令和08年11月05日</td></tr>
  </table>
  <p>売却基準価額 <span>1,710,000円</span></p>
  <p>買受申出保証金 <span>342,000円</span></p>
  <p>姫路市安元１１２番1</p>
  <ul>
    <li><div class="bit__result_InfoHeader p-2">物件番号．種別</div>
        <div class="px-2 py-3">1．マンション</div></li>
    <li><div class="bit__result_InfoHeader p-2">中止情報</div>
        <div class="px-2 py-3"><span class="bit__text_red"></span></div></li>
  </ul>
</div>
<nav class="bit__pager" aria-label="Page navigation">
  <div class="pagination">
    <div class="page-item disabled">
      <a class="page-link" href="#" onclick="getData(1);" aria-label="first">
        <span class="bit__pager_first" aria-hidden="true"></span>
        <span class="sr-only">first</span>
      </a>
    </div>
    <div class="page-item">
      <a class="page-link" href="#" onclick="getData(2);" aria-label="last">
        <span class="bit__pager_last" aria-hidden="true"></span>
        <span class="sr-only">last</span>
      </a>
    </div>
  </div>
</nav>
</body></html>"""


class 画面読み上げ用の文字を値にしない(unittest.TestCase):
    """ページ送りの `<span class="sr-only">first</span>` は欄の値ではない。

    実物で 106行のうち6行の「中止情報」が `first` になっていた
    （1ページにつき1行、最後のカード。ページ数と同じ6）。

    `first` は中止情報の語ではないので段階は動かない。**そこが怖い。**
    値が入っているので誰も空だと気づかず、
    **その6行の本当の中止情報は読めていない**まま通る。
    取下げは中止情報の欄にしか出ないので、取下げを見落とす形になる。

    語の一覧では守れない（`first` `last` `Next` … を並べても次の語で漏れる）。
    **目に見えない文字だ、という形のほうで弾く。**
    """

    def setUp(self):
        self.rows, self.unknown = parse.parse_bit_list(
            PAGER_HTML, "33332", "https://example/x", "2026-09-17")

    def test_中止情報が空のまま終わっても次の文字が入らない(self):
        self.assertEqual(len(self.rows), 1)
        self.assertEqual(self.rows[0]["status_raw"], "")
        self.assertEqual(self.rows[0]["status"], "")

    def test_ページ送りの文字がどの欄にも入らない(self):
        # 中止情報だけを見張ると、次に別の欄が待っていたときに漏れる
        for r in self.rows:
            for k, v in r.items():
                if isinstance(v, str):
                    self.assertNotIn("first", v, k)
                    self.assertNotIn("last", v, k)

    def test_ページ送りは知らない見出しとしても出さない(self):
        # 「読めなかった」ではなく「読む対象ではない」。催促の紙を鳴らし続けない
        self.assertFalse([u for u in self.unknown if "first" in u or "last" in u])


class 決めたあとで答えを変えない(unittest.TestCase):
    """**基準が、あとから来たデータで動く**（2026-09-19）。

    `mark_saishutsu()` は「その物件で、こちらが知っているいちばん早い回」を
    基準に新規／再公告を決める。基準は**いま持っているデータ**で決まる。

        いま      11月の回だけ見えている        → 新規
        あとから  8月の回（過去データ）が入る  → 11月の回が**再公告に裏返る**

    裏返っても**親（公告）の合計は変わらない**ので、`kazu_ga_au()` は通る。
    **公開した升が黙って入れ替わる形**だった。

    過去データ（3年分）を入れる日に、まとまって起きる。
    """

    def 行(self, pk, open_date, first_seen="2026-09-17"):
        return {"property_key": pk, "key": "%s:%s" % (pk, open_date),
                "open_date": open_date, "first_seen": first_seen}

    def test_あとから早い回が来ても裏返らない(self):
        m = {}
        一 = self.行("A", "2026-11-05")
        m[一["key"]] = 一
        parse.mark_saishutsu(m)
        self.assertFalse(m["A:2026-11-05"]["saishutsu"])

        m["A:2026-08-01"] = self.行("A", "2026-08-01", "2026-10-05")
        _, 裏返り = parse.mark_saishutsu(m)
        self.assertFalse(m["A:2026-11-05"]["saishutsu"],
                         "決めた値が動いた。公開した升が黙って入れ替わる")
        self.assertEqual(len(裏返り), 1, "動かさなかったことを控えていない")
        self.assertEqual(裏返り[0][0], "A:2026-11-05")
        self.assertEqual(裏返り[0][1:], (False, True))

    def test_まだ決まっていない行は決める(self):
        """**止めるのは「決め直し」だけ。** 新しい行は決められること。"""
        m = {}
        m["B:2026-08-01"] = self.行("B", "2026-08-01")
        m["B:2026-11-05"] = self.行("B", "2026-11-05")
        parse.mark_saishutsu(m)
        self.assertFalse(m["B:2026-08-01"]["saishutsu"])
        self.assertTrue(m["B:2026-11-05"]["saishutsu"])

    def test_重ねるときに持ち越す(self):
        """`first_seen` と同じ扱い。持ち越さないと毎回いちから決め直す。"""
        merged = {}
        parse.merge_snapshot(merged, [self.行("C", "2026-11-05")], "2026-09-17")
        parse.mark_saishutsu(merged)
        self.assertIn("saishutsu", merged["C:2026-11-05"])
        # 次の日、同じ物件がまた一覧に出る（読み取りは saishutsu を持たない）
        新 = self.行("C", "2026-11-05")
        self.assertNotIn("saishutsu", 新)
        parse.merge_snapshot(merged, [新], "2026-09-18")
        self.assertIn("saishutsu", merged["C:2026-11-05"],
                      "重ねたときに決めた値が落ちている")

    def test_親の合計は変わらないので足し算では気づけない(self):
        """**なぜ別の見張りが要るか**を、ここで1回見せておく。"""
        import aggregate
        from collections import Counter

        def 升(m):
            c = Counter()
            for r in m.values():
                rr = dict(r)
                rr.setdefault("status", "")
                rr.setdefault("system", "keibai")
                for ev in aggregate.events(rr):
                    c[ev] += 1
            return c

        前 = {}
        前["D:2026-11-05"] = self.行("D", "2026-11-05")
        parse.mark_saishutsu(前)
        後 = {"D:2026-11-05": self.行("D", "2026-11-05"),
              "D:2026-08-01": self.行("D", "2026-08-01", "2026-10-05")}
        parse.mark_saishutsu(後)
        # 親（公告）の 2026-09 は、どちらも 1 のまま
        self.assertEqual(升(前)[("公告", "2026-09")], 1)
        self.assertEqual(升(後)[("公告", "2026-09")], 1)
        # なのに子は入れ替わっている
        self.assertEqual(升(前)[("公告-初出", "2026-09")], 1)
        self.assertEqual(升(後)[("公告-再出", "2026-09")], 1)


class あとから答えが変わった行の控え(unittest.TestCase):
    """**黙って捨てるのでも、黙って直すのでもない**（正本 9節）。"""

    def setUp(self):
        import tempfile
        self.keep = parse.URAGAERI
        parse.URAGAERI = os.path.join(tempfile.mkdtemp(), "uragaeri.md")

    def tearDown(self):
        parse.URAGAERI = self.keep

    def 書かせる(self, 裏返り):
        import io as _io
        import sys as _sys
        out = _io.StringIO()
        k = _sys.stdout
        _sys.stdout = out
        try:
            parse.write_uragaeri(裏返り)
        finally:
            _sys.stdout = k
        文 = ""
        if os.path.exists(parse.URAGAERI):
            with open(parse.URAGAERI, encoding="utf-8") as f:
                文 = f.read()
        return 文, out.getvalue()

    def test_あったら控えて鳴る(self):
        文, 画面 = self.書かせる([("33111", "A:2026-11-05", False, True)])
        self.assertIn("33111", 文)
        self.assertIn("A:2026-11-05", 文)
        self.assertIn("新規", 文)
        self.assertIn("再公告", 文)
        self.assertIn("::error::", 画面, "黙って控えるだけでは気づけない")

    def test_公開しないと書いてある(self):
        """走らせた記録。伏せる前の値が入りうる（正本 9節）。"""
        文, _ = self.書かせる([("33111", "A:2026-11-05", False, True)])
        self.assertIn("公開しない", 文)

    def test_無ければ紙を残さない(self):
        """**前の日の紙が残ると、直ったのに鳴りつづける。**"""
        self.書かせる([("33111", "A:2026-11-05", False, True)])
        self.assertTrue(os.path.exists(parse.URAGAERI))
        文, 画面 = self.書かせる([])
        self.assertFalse(os.path.exists(parse.URAGAERI))
        self.assertNotIn("::error::", 画面)


class 平米と名乗る欄に平米だけを入れる(unittest.TestCase):
    """`area_sqm` / `floor_sqm` は**平米だと名乗っている**（2026-09-20）。

    前の `to_area` は「文字列に出てくる最初の数」を返していた。

        築40年   → 40.0     年を面積にしていた
        3階建    → 3.0      階を面積にしていた
        600坪    → 600.0    本当は 1,983㎡。**3.3倍ずれる**

    どれも検査が1本も無かった。読めない欄は None にして、
    **読めなかったことを残す**（正本 9節）。

    **材料は、単位の違うものを渡さないと見分けられない。**
    数だけを渡すと、単位を見ていても見ていなくても同じ値が出る。
    """

    def test_平米はそのまま(self):
        self.assertEqual(parse.to_area("1,234㎡"), 1234.0)
        self.assertEqual(parse.to_area("約120㎡"), 120.0)
        self.assertEqual(parse.to_area("1234.5m2"), 1234.5)

    def test_BITの欠けたmも面積として読む(self):
        """BIT は `m<sup>2</sup>`。読むと 2 が別のかたまりになって落ちる。

        実測（2026-09-20）: 33111 の一覧で面積はすべて `1332.00m` の形。
        ここを落とすと **105行の床面積が丸ごと消える**（実測）。
        """
        self.assertEqual(parse.to_area("1332.00m"), 1332.0)

    def test_単位が無い欄は数だけ読む(self):
        """見出しに「（平方メートル）」と書いてある表。堺市がこの形。"""
        self.assertEqual(parse.to_area("1591.58"), 1591.58)

    def test_坪は平米に直す(self):
        self.assertEqual(parse.to_area("600坪"), 1983.47)
        self.assertEqual(parse.to_area("1坪"), 3.31)

    def test_面積でないものを面積にしない(self):
        for t in ("築40年", "3階建", "3階建て", "昭和55年建築", "令和6年", "5室"):
            self.assertIsNone(parse.to_area(t),
                              "%s を面積として読んでいる" % t)

    def test_読めないものはNone(self):
        for t in ("-", "不明", "", None):
            self.assertIsNone(parse.to_area(t))


# ---------------------------------------------------------------- 完全観測の印
#
# BITのページ送り（pager）の形だけをまねた作りもの。
# **実物の住所・事件番号などは1文字も写さない**（依頼文の「絶対に守ること」）。
# 実物で確かめた特徴だけ再現する：
#   - いまのページ番号の <a> には onclick が無い（もう押せないので）
#   - ほかのページ番号には onclick="getData(番号)" が付く
#   - 「末尾」（aria-label="last"）の onclick の番号が、最後のページ番号になる
def pager_html(genzai, saigo, honbun_owaru=True):
    ban = []
    for n in range(1, saigo + 1):
        if n == genzai:
            ban.append('<div class="page-item disabled">'
                       '<a class="page-link" href="#">%d</a></div>' % n)
        else:
            ban.append('<div class="page-item">'
                       '<a class="page-link" href="#" onclick="getData(%d);">'
                       '%d</a></div>' % (n, n))
    last_disabled = " disabled" if genzai == saigo else ""
    ban.append('<div class="page-item%s"><a class="page-link" href="#" '
              'onclick="getData(%d);" aria-label="last">'
              '<span></span></a></div>' % (last_disabled, saigo))
    body = ('<html><body><nav class="bit__pager"><div class="pagination">'
           + "".join(ban) + "</div></nav></body></html>")
    return body if honbun_owaru else body + "\n<!-- 保存が途中で切れた -->"


class ページ送りを読む(unittest.TestCase):
    """`parse.pager_info()`。実物の保存ページの形（page-item・aria-label）から、
    「今のページ番号」と「最後のページ番号」を読む（spec/kanzen_keibai.md 2）。
    """

    def test_1ページだけの一覧(self):
        self.assertEqual(parse.pager_info(pager_html(1, 1)), (1, 1))

    def test_2ページの1枚目(self):
        self.assertEqual(parse.pager_info(pager_html(1, 2)), (1, 2))

    def test_2ページの2枚目(self):
        self.assertEqual(parse.pager_info(pager_html(2, 2)), (2, 2))

    def test_pagerが見当たらなければNone(self):
        self.assertIsNone(parse.pager_info("<html><body>物件は無い</body></html>"))

    def test_空文字もNone(self):
        self.assertIsNone(parse.pager_info(""))


class 観測の基本の印(unittest.TestCase):
    """`parse.kansoku_kihon_shirushi()`。入口に届いた・必要本文を受け取った・
    ページ送りを最後まで受け取った の3つ（spec/kanzen_keibai.md 2）。
    """

    def test_2ページとも揃っていればぜんぶはい(self):
        s = parse.kansoku_kihon_shirushi([pager_html(1, 2), pager_html(2, 2)])
        self.assertEqual(s["入口に届いた"], kanzen.HAI)
        self.assertEqual(s["必要本文を受け取った"], kanzen.HAI)
        self.assertEqual(s["ページ送りを最後まで受け取った"], kanzen.HAI)

    def test_2枚目が置かれていない(self):
        """**人が2枚目を保存し忘れた形。** 欠けている→いいえ。"""
        s = parse.kansoku_kihon_shirushi([pager_html(1, 2)])
        self.assertEqual(s["ページ送りを最後まで受け取った"], kanzen.IIE)

    def test_pagerがどのページにも無い(self):
        s = parse.kansoku_kihon_shirushi(["<html><body>物件0件</body></html>"])
        self.assertEqual(s["ページ送りを最後まで受け取った"], kanzen.WAKARANAI)

    def test_途中で切れた保存は本文いいえ(self):
        s = parse.kansoku_kihon_shirushi([pager_html(1, 1, honbun_owaru=False)])
        self.assertEqual(s["必要本文を受け取った"], kanzen.IIE)
        # 本文が切れていても、ファイル自体は読めている
        self.assertEqual(s["入口に届いた"], kanzen.HAI)

    def test_読めなかったファイルがある(self):
        """入口に届いていないので、後ろの2つも確かめようがない。"""
        s = parse.kansoku_kihon_shirushi([pager_html(1, 2), None])
        self.assertEqual(s["入口に届いた"], kanzen.IIE)
        self.assertEqual(s["必要本文を受け取った"], kanzen.WAKARANAI)
        self.assertEqual(s["ページ送りを最後まで受け取った"], kanzen.WAKARANAI)

    def test_ページが1枚も無い(self):
        s = parse.kansoku_kihon_shirushi([])
        self.assertEqual(s["入口に届いた"], kanzen.IIE)


class 解析できたの印(unittest.TestCase):
    """`parse.kansoku_kaiseki_shirushi()`。0件のとき・急減のときは
    「消えた」「読めなかった」と決めつけず、分からないへ倒す。
    """

    def test_行が読めていればはい(self):
        kaiseki, why = parse.kansoku_kaiseki_shirushi("<html></html>",
                                                       [{"key": "A"}], 0, set(), {"A"})
        self.assertEqual(kaiseki, kanzen.HAI)
        self.assertEqual(why, "")

    def test_0件で前も0件なら読めなかった扱い(self):
        """はじめての観測、または前から0件。原典の0件表示を確かめていないので、
        いいえ（読めなかった）に倒す。**分からないへ逃げない**（zero_gyouの規則）。
        """
        kaiseki, why = parse.kansoku_kaiseki_shirushi("物件は0件", [], 0, set(), set())
        self.assertEqual(kaiseki, kanzen.IIE)
        self.assertNotEqual(why, "")

    def test_前は件数があって今回0件は分からない(self):
        """**消えたと決めつけない。** 保存し忘れ・様式変わりかもしれない。"""
        kaiseki, _why = parse.kansoku_kaiseki_shirushi(
            "物件は0件", [], 5, {"A", "B", "C", "D", "E"}, set())
        self.assertEqual(kaiseki, kanzen.WAKARANAI)

    def test_半分以上が一度に消えたら分からない(self):
        mae_kagi = {"A", "B", "C", "D"}
        ima_kagi = {"A"}                    # 4件のうち3件（75%）が消えた
        kaiseki, _why = parse.kansoku_kaiseki_shirushi(
            "<html></html>", [{"key": "A"}], len(mae_kagi), mae_kagi, ima_kagi)
        self.assertEqual(kaiseki, kanzen.WAKARANAI)


class private保存成功の印(unittest.TestCase):
    """`parse.kansoku_hozon_shirushi()`。ファイルの実体が金庫（KINKO_DIR）の中か。"""

    def setUp(self):
        self.kinko = tempfile.mkdtemp()
        self.soto = tempfile.mkdtemp()
        self.f = os.path.join(self.kinko, "a.html")
        with open(self.f, "w", encoding="utf-8") as fp:
            fp.write("x")

    def test_KINKO_DIRが無ければ分からない(self):
        self.assertEqual(parse.kansoku_hozon_shirushi([self.f], {}), kanzen.WAKARANAI)

    def test_金庫の中ならはい(self):
        got = parse.kansoku_hozon_shirushi([self.f], {"KINKO_DIR": self.kinko})
        self.assertEqual(got, kanzen.HAI)

    def test_金庫の外ならいいえ(self):
        got = parse.kansoku_hozon_shirushi([self.f], {"KINKO_DIR": self.soto})
        self.assertEqual(got, kanzen.IIE)


class 完全観測どうしの比較でだけ消えたを付ける(unittest.TestCase):
    """`parse.merge_snapshot()` の `kanzen_flag` / `mae_kanzen_hi`。

    spec/kanzen.md「消えた」は、直前の完全観測と今回の完全観測の比較だけで付ける。
    不完全な回は、消失判定の時点（`kakunin_saigo`）を進めない。
    """

    def 行(self, key, **kw):
        d = {"key": key, "property_key": key, "open_date": "2026-11-05"}
        d.update(kw)
        return d

    def test_完全観測ならkakunin_saigoが進む(self):
        merged = {}
        parse.merge_snapshot(merged, [self.行("A")], "2026-09-17",
                             kanzen_flag=True)
        self.assertEqual(merged["A"]["kakunin_saigo"], "2026-09-17")

    def test_不完全観測は進めない(self):
        merged = {}
        parse.merge_snapshot(merged, [self.行("A")], "2026-09-17",
                             kanzen_flag=False)
        self.assertIsNone(merged["A"].get("kakunin_saigo"))

    def test_直前の完全観測に無ければ消えたを付けない(self):
        """今回は完全観測でも、比べる直前の完全観測（`mae_kanzen_hi`）が
        渡されなければ、1件も「消えた」を付けない（止まる側に倒す）。
        """
        merged = {}
        parse.merge_snapshot(merged, [self.行("A"), self.行("B")],
                             "2026-09-17", kanzen_flag=True)
        # Bがいなくなった。ただし比べる相手を渡していない
        parse.merge_snapshot(merged, [self.行("A")], "2026-09-24",
                             kanzen_flag=True, mae_kanzen_hi=None)
        self.assertNotIn("gone_on", merged["B"])

    def test_完全観測どうしなら消えたを付ける(self):
        merged = {}
        parse.merge_snapshot(merged, [self.行("A"), self.行("B")],
                             "2026-09-17", kanzen_flag=True)
        parse.merge_snapshot(merged, [self.行("A")], "2026-09-24",
                             kanzen_flag=True, mae_kanzen_hi="2026-09-17")
        self.assertEqual(merged["B"]["gone_on"], "2026-09-24")
        self.assertEqual(merged["B"]["gone_kansoku"],
                         ["2026-09-17", "2026-09-24"])
        self.assertEqual(merged["B"]["status"], aggregate.GONE)

    def test_不完全観測では消えたを付けない(self):
        """今回が完全観測でなければ、直前の完全観測が分かっていても付けない
        （不完全な回のうちに「消えた」と言わない）。
        """
        merged = {}
        parse.merge_snapshot(merged, [self.行("A"), self.行("B")],
                             "2026-09-17", kanzen_flag=True)
        parse.merge_snapshot(merged, [self.行("A")], "2026-09-24",
                             kanzen_flag=False, mae_kanzen_hi="2026-09-17")
        self.assertNotIn("gone_on", merged["B"])
        # 不完全観測なので、消失判定の時点も進めない
        self.assertEqual(merged["A"]["kakunin_saigo"], "2026-09-17")

    def test_再登場したら消えたが取り消される(self):
        merged = {}
        parse.merge_snapshot(merged, [self.行("A"), self.行("B")],
                             "2026-09-17", kanzen_flag=True)
        parse.merge_snapshot(merged, [self.行("A")], "2026-09-24",
                             kanzen_flag=True, mae_kanzen_hi="2026-09-17")
        self.assertIn("gone_on", merged["B"])
        # Bがまた一覧に出た
        parse.merge_snapshot(merged, [self.行("A"), self.行("B")],
                             "2026-10-01", kanzen_flag=True,
                             mae_kanzen_hi="2026-09-24")
        self.assertNotIn("gone_on", merged["B"],
                         "また見えたのに消えたが残っている")

    def test_直前の完全観測で見えていない行には付けない(self):
        """不完全観測の日にだけ現れた行は `kakunin_saigo` を持たない。
        消えても「直前の完全観測との比較」とは言えないので、消えたを付けない。
        """
        merged = {}
        parse.merge_snapshot(merged, [self.行("A")], "2026-09-17",
                             kanzen_flag=True)
        # Cは不完全観測の日にだけ現れた（kakunin_saigoを持たない）
        parse.merge_snapshot(merged, [self.行("A"), self.行("C")],
                             "2026-09-20", kanzen_flag=False)
        # 次の完全観測でCがいなくなった
        parse.merge_snapshot(merged, [self.行("A")], "2026-09-24",
                             kanzen_flag=True, mae_kanzen_hi="2026-09-17")
        self.assertNotIn("gone_on", merged["C"])


if __name__ == "__main__":
    unittest.main()
