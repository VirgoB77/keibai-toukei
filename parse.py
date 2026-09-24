#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""保存したページから、中身を取り出す。

    python3 parse.py

いま読めるもの:

    bit-schedule … BITの売却スケジュール（裁判所ごと）
                   → data/schedule/<court_id>.json

売却スケジュールは、物件そのものではなく**開札の回**の予定表。
「いつ公告して、いつからいつまで札を入れて、いつ開けるか」が並んでいる。
これが競売のコホート（同じ回にまとめた物件の集まり）の定義になる。
物件の一覧や結果はフォーム遷移の先にあるので、そちらは inbox 運用で後から足す。

読む先は data/raw と inbox の**どちらでも同じ関数**で読む（DESIGN 9章）。
出どころが違うだけで、ページの形は同じだから。

新しく取りに行かない。recon.py が保存した分を読むだけ。
Python 3 の標準ライブラリだけで動く。
"""

import json
import os
import re
import sys
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from datetime import date  # noqa: E402

import aggregate  # noqa: E402  段階の語彙は aggregate が持つ
import recon  # noqa: E402  文字コードの判定を借りる
from common import kanzen  # noqa: E402  完全観測の印は共通の物差しで持つ
from common import privacy  # noqa: E402
from common import report  # noqa: E402
from common.jst import today as jst_today  # noqa: E402

RAW_DIR = os.path.join(HERE, "data", "raw")
INBOX_DIR = os.path.join(HERE, "inbox")
SCHEDULE_DIR = os.path.join(HERE, "data", "schedule")
ROWS_DIR = os.path.join(HERE, "data", "rows", "keibai")
UNKNOWN = os.path.join(HERE, "data", "parse-unknown.md")


# ---------------------------------------------------------------- 和暦

# 全角の数字を半角にする。役所の画面は全角のことがある
_TO_HAN = str.maketrans("０１２３４５６７８９", "0123456789")

# R08/09/01 のような書き方。元号1文字＋年/月/日
WAREKI = re.compile(r"^([RHS])\s*(\d{1,2})[/／\.](\d{1,2})[/／\.](\d{1,2})$")

# 令和08年09月07日 という書き方。**スマホの画面はこちら**。
# パソコンの画面は R08/09/07 なので、両方を読めないと片方が落ちる。
# 実物の写真を見て気づいた（2026-09-16）
WAREKI_KANJI = re.compile(
    r"^(令和|平成|昭和)\s*(\d{1,2}|元)\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?$")

GENGO_START = {"R": 2018, "H": 1988, "S": 1925,      # 元年の前年を足す
               "令和": 2018, "平成": 1988, "昭和": 1925}


def to_date(text):
    """R08/09/01 → 2026-09-01。読めなければ None。

    令和1年が2019年なので、令和の年に2018を足す。
    平成・昭和の書き方も来るかもしれないので、いっしょに見る
    （過去データの照会では平成の回が出る）。
    """
    s = (text or "").strip().replace("　", "")
    s = s.translate(_TO_HAN)          # 全角の数字を半角に
    m = WAREKI.match(s) or WAREKI_KANJI.match(s)
    if m:
        g = m.group(1)
        y = 1 if m.group(2) == "元" else int(m.group(2))
        mo, d = int(m.group(3)), int(m.group(4))
        return "%04d-%02d-%02d" % (GENGO_START[g] + y, mo, d)
    m = re.match(r"^(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?$", s)
    if m:
        return "%04d-%02d-%02d" % (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


# ---------------------------------------------------------------- 表を読む

def _span(attrs, name):
    """rowspan / colspan の数。おかしな値は1にする。"""
    try:
        n = int(dict(attrs).get(name, 1))
    except (TypeError, ValueError):
        return 1
    return n if 1 <= n <= 100 else 1


def expand(rows):
    """結合セル（rowspan / colspan）を広げて、四角い表にする。

    役所の一覧表は結合セルだらけ。広げずに読むと**列がずれる**。
    しかも、ずれ方が「値が空になる」ではなく「**隣の列の値が入る**」なので、
    面積や金額が黙って別の数字に化ける。気づきにくいので最初から広げる。

    rows は [(文字, rowspan, colspan), ...] の並びの並び。
    """
    out, carry = [], {}       # carry: 列番号 → [文字, 残りの行数]
    for row in rows:
        line, col = [], 0
        it = iter(row)
        while True:
            # 上の行から降りてきているものを先に置く
            while col in carry:
                text, left = carry[col]
                line.append(text)
                left -= 1
                if left <= 0:
                    del carry[col]
                else:
                    carry[col] = [text, left]
                col += 1
            try:
                text, rs, cs = next(it)
            except StopIteration:
                break
            for _ in range(cs):
                line.append(text)
                if rs > 1:
                    carry[col] = [text, rs - 1]
                col += 1
        # 行が尽きたあとも、降りてきているものがあれば置く
        while col in carry:
            text, left = carry[col]
            line.append(text)
            left -= 1
            if left <= 0:
                del carry[col]
            else:
                carry[col] = [text, left]
            col += 1
        if any(c for c in line):
            out.append(line)
    return out


class Tables(HTMLParser):
    """ページの中の表を、行と升の文字として取り出す。

    結合セルは expand() で広げてから返す。
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self._stack = []       # 入れ子の表に耐える
        self._row = None
        self._cell = None
        self._span = (1, 1)
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        elif tag == "table":
            self._stack.append([])
        elif tag == "tr" and self._stack:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []
            self._span = (_span(attrs, "rowspan"), _span(attrs, "colspan"))

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag in ("td", "th") and self._cell is not None:
            text = re.sub(r"\s+", " ", "".join(self._cell)).strip()
            self._row.append((text, self._span[0], self._span[1]))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._stack:
                self._stack[-1].append(self._row)
            self._row = None
        elif tag == "table" and self._stack:
            self.tables.append(expand(self._stack.pop()))

    def handle_data(self, data):
        if self._skip:
            return
        if self._cell is not None:
            self._cell.append(data)


def tables_of(text):
    """HTMLの文字列から、表の一覧を返す。"""
    t = Tables()
    try:
        t.feed(text)
    except Exception:
        pass
    return t.tables


def read_page(path):
    """保存したページを読む。data/raw でも inbox でも同じ読み方。"""
    with open(path, "rb") as f:
        raw = f.read()
    text, _ = recon.to_text(raw, "")
    return text


# ---------------------------------------------------------------- 売却スケジュール

# 表の見出しに出る言葉 → こちらの項目名
SCHEDULE_COLS = {
    "開札日": "open_date",
    "売却実施処分日": "disposal_date",
    "公告日": "notice_date",
    "閲覧開始日": "view_start",
    "入札開始日": "bid_start",
    "入札終了日": "bid_end",
    "売却決定日": "decision_date",
    "確定日": "confirm_date",
    "状態": "status",
    "農地": "farmland",
}


def parse_bit_schedule(text, court_id, source_url="", fetched_on=""):
    """BITの売却スケジュールを読む。

    表の見出しは「農地／開札日／売却実施処分日／公告日／閲覧開始日／
    入札開始日／入札終了日／売却決定日／確定日／状態」。
    見出しの並びは裁判所によって変わるかもしれないので、
    **位置ではなく見出しの文字で**どの列かを決める。
    """
    header, rows = None, []
    for table in tables_of(text):
        for row in table:
            hit = [c for c in row if c in SCHEDULE_COLS]
            if len(hit) >= 4:              # 見出しらしい行
                header = [SCHEDULE_COLS.get(c) for c in row]
                continue
            if header is None:
                continue
            if len(row) != len(header):
                continue
            item = {}
            for name, cell in zip(header, row):
                if not name:
                    continue
                if name == "status":
                    item[name] = cell or ""
                elif name == "farmland":
                    item[name] = bool(cell)
                else:
                    item[name] = to_date(cell)
            if not item.get("open_date"):
                continue               # 開札日が読めない行は予定表ではない
            item["court_id"] = court_id
            item["key"] = "%s:%s:%s" % (court_id, item["open_date"],
                                        "農地" if item.get("farmland") else "一般")
            # 出典と取得日は全レコードに付ける。例外なし（正本 3.5）
            item["source_url"] = source_url or ""
            item["fetched_on"] = fetched_on or ""
            rows.append(item)

    # 同じ回が2度出てきたら、あとに出たほうを採る
    uniq = {}
    for r in rows:
        uniq[r["key"]] = r
    return sorted(uniq.values(), key=lambda r: (r["open_date"], r["key"]))


# ---------------------------------------------------------------- 物件の一覧


# 一覧の見出し（ラベル）→ こちらの項目名。
#
# BITの一覧は**表ではなくカード**だった（2026-09-16、実物の写真で確認）。
# 1件が1枚のカードで、中はラベルと値の組み合わせが並ぶ。
# パソコンでは横2列、スマホでは上下に積む。どちらも順番は同じなので、
# 「ラベルを見たら次の文字が値」として読む。
LIST_COLS = {
    "閲覧開始日": "view_start",
    "入札期間": "bid_period",
    "開札期日": "open_date",
    "開札日": "open_date",
    "特別売却期間": "special_period",
    "売却基準価額": "base_price",
    "買受申出保証金": "deposit",
    "買受可能価額": "min_price",
    "物件番号．種別": "items_raw",
    "物件番号. 種別": "items_raw",
    "種類": "shurui",          # 居宅／区分所有建物（所有権）／田／畑 など
    "地目": "chimoku",
    "用途地域": "zoning",
    "床面積": "floor_sqm",
    "専有面積": "floor_sqm",
    "土地面積": "area_sqm",
    "間取り": "madori",
    "構造": "kouzou",
    "中止情報": "status_raw",
    "備考": "note",
    "特記事項": "note",
    # 当事者の名前らしきラベル。**読み落とすと undisclosed に化けて地番が出る**
    "買受人": "winner_name",
    "落札者": "winner_name",
    "契約相手方": "winner_name",
    "相手方": "winner_name",
    "買受申出人": "winner_name",
    "所有者": "owner_name",
}

# 名前らしきラベルの目印。見つからなかったことを報告するために使う。
# **語は common/privacy.py の PARTY_WORDS（4サイトぶん）から来る。**
# ここで持つと、ほかのサイトが足した語がこちらに届かない（正本 5節）。
# 「名称」だけはこのサイト固有（物件の名称の欄があるため）

# カードの見出し。「大阪地方裁判所本庁　令和06年(ケ)第414号」
CASE_HEAD = re.compile(
    r"(?P<court>[^\s]*(?:地方裁判所|地裁)[^\s]*)\s+"
    r"(?P<case>(?:令和|平成)\s*\d{1,2}\s*年\s*[(（][^)）]{1,3}[)）]\s*第?\s*\d+\s*号)")

# 見出しの入れ物。ここに入っている文字は、知らない語でも見出しとして扱う。
# BITのカードは dt/th ではなく **div の class** で見出しを書いている
# （`<div class="bit__result_InfoHeader">用途地域</div>`）。実物で確認した
LABEL_TAGS = ("dt", "th")
LABEL_CLASSES = ("InfoHeader",)

# 種別のバッジ。カードの左上に出る
KIND_BADGE = ("土地", "戸建て", "マンション", "その他")

# 中止情報に入る言葉。赤字で「取下」と出る
STATUS_WORDS = ("取下", "取消", "停止", "中止", "変更", "延期", "不売", "売却")
STATUS_MAP = {"取下": "取下げ", "取消": "取消", "停止": "中止",
              "中止": "中止", "変更": "変更", "延期": "変更"}

# 種別を4つにそろえる。原文は kind_raw に残す（DESIGN 6章）
KIND_MAP = (
    ("マンション", "マンション"), ("区分所有", "マンション"),
    ("一戸建", "戸建て"), ("戸建", "戸建て"), ("居宅", "戸建て"),
    ("土地", "土地"), ("宅地", "土地"), ("畑", "土地"), ("田", "土地"),
    ("山林", "土地"), ("雑種地", "土地"), ("農地", "土地"),
)


def to_kind(raw):
    """種別を 土地／戸建て／マンション／その他 に寄せる。"""
    s = (raw or "")
    for word, kind in KIND_MAP:
        if word in s:
            return kind
    return "その他"


def to_money(text):
    """「1,710,000円」→ 1710000。読めなければ None。

    取下げ済みの物件は「－円」と出る。そこは None になる。
    """
    s = re.sub(r"[,，\s円]", "", (text or ""))
    m = re.search(r"\d+", s)
    return int(m.group()) if m else None


# 1坪 = 400/121 平方メートル（計量法。割り切れない）
_TSUBO_M2 = 400.0 / 121.0
# **BIT は `m<sup>2</sup>` と書く。** 読むときに `<sup>` の中身が別の
# かたまりになるので、面積の欄に届くのは `1332.00m` で、2 が落ちている。
# 実測（2026-09-20）: 33111 の一覧で、面積はすべて `…m` の形だった。
# だから末尾の `m` も面積の単位として受ける（面積の列に来た `m`）。
_AREA_UNIT = re.compile(
    r"(\d+(?:\.\d+)?)(㎡|[mｍ][2２²]?|平方メートル|平方米|平米|坪)")
_AREA_BARE = re.compile(r"^\d+(?:\.\d+)?$")


def to_area(text):
    """「123.45m2」→ 123.45。**必ず平米で返す。** 読めなければ None。

    前は「文字列に出てくる最初の数」を返していた。
    `area_sqm`・`floor_sqm` と**平米だと名乗っているのに、
    平米とはかぎらなかった。**

        築40年   → 40.0     年を面積にしていた
        3階建    → 3.0      階を面積にしていた
        600坪    → 600.0    本当は 1,983㎡。**3.3倍ずれる**

    いまは、数のうしろに面積の単位が付いているか、
    **文字列が数だけ**のときにしか返さない。
    坪は平米に直す（切り捨てない。名乗りを合わせるのが先）。

    実データ（2026-09-20）には坪の面積は1つも無い。
    「坪」が出てくる3ファイルは、どれも地名の中の字だった。
    **いま効いていなくても、入る日はいちばん急いでいる日になる。**
    """
    s = re.sub(r"[,，\s]", "", (text or ""))
    m = _AREA_UNIT.search(s)
    if m:
        n = float(m.group(1))
        return round(n * _TSUBO_M2, 2) if m.group(2) == "坪" else n
    # 単位が1つも書いていない欄（見出しで平米と分かっている列）はそのまま
    return float(s) if _AREA_BARE.match(s) else None


def split_period(text):
    """「令和08年10月21日〜令和08年10月29日」→ 2つの日付。"""
    parts = re.split(r"[~〜～]", (text or ""))
    if len(parts) >= 2:
        return to_date(parts[0].strip()), to_date(parts[-1].strip())
    return to_date(text), None


def split_items(text):
    """「1．土地（農地） 2．土地（農地）」→ [("1","土地（農地）"), ...]

    1つの事件に物件が複数ぶら下がる。番号と種別の組で返す。
    """
    out = []
    for m in re.finditer(r"(\d+)\s*[.．]\s*(.+?)(?=\s*\d+\s*[.．]|$)",
                         (text or "").strip()):
        kind = m.group(2).strip()
        if kind:
            out.append((m.group(1), kind))
    return out


class Cards(HTMLParser):
    """カード1枚ずつに、見出し・ラベル・値・住所を集める。

    BITの一覧は表ではなくカード。ラベルと値が交互に並ぶだけなので、
    「ラベルを見たら次の文字が値」として拾う。
    パソコンとスマホで並び方（横2列／上下）が違っても、順番は同じ。
    """

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.cards = []
        self.texts = []
        self._card = None
        self._label = None
        self._skip = 0
        self._tag = ""
        self._in_label = False  # いま見出しの入れ物の中にいるか
        self._sr_only = False   # いま画面読み上げ用の文字の中にいるか
        self._badge = ""        # 見出しの**手前**に出る種別のバッジ

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        self._tag = tag
        cls = ""
        for k, v in attrs:
            if k == "class":
                cls = v or ""
        self._in_label = any(c in cls for c in LABEL_CLASSES)
        # **画面読み上げ用の文字は、欄の値ではない**（2026-09-19）。
        # BITのページ送りは `<span class="sr-only">first</span>` で、
        # 目には見えないが文字としては出てくる。
        # **待っている見出しがあると、その値として入る。**
        #
        # 実物で 106行のうち6行の「中止情報」が `first` になっていた。
        # `first` は中止情報の語ではないので段階は動かないが、
        # **その6行の本当の中止情報は読めていない。**
        # 取下げは中止情報の欄にしか出ないので、**取下げを見落とす形**。
        #
        # 語の一覧で弾かない（`first` `last` … を並べても、次の語で漏れる）。
        # **見えない文字だ、という形のほうで弾く。**
        self._sr_only = "sr-only" in cls

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        self._tag = ""
        self._in_label = False
        self._sr_only = False

    def handle_data(self, data):
        if self._skip:
            return
        text = re.sub(r"[\s　]+", " ", data).strip()
        if not text:
            return
        if self._sr_only:
            # **待っている見出しは、値が空だったということ。**
            # 黙って捨てるのではなく、空だと決めて閉じる。
            # 閉じないと、次に来た文字がその欄の値になる
            if self._card is not None and self._label is not None:
                self._card["pairs"].append((self._label, ""))
                self._label = None
            return
        self.texts.append(text)

        m = CASE_HEAD.search(text)
        if m:
            # **バッジはカードの見出しより手前に出る。**
            # 見出しを見てから拾おうとすると、1枚ずれて隣のカードの種別が入る。
            # ずれ方が「空になる」ではなく「隣の値が入る」ので気づきにくい（正本 9節）
            self._card = {"court_name": m.group("court"),
                          "case_no": re.sub(r"\s+", "", m.group("case")),
                          "badge": self._badge,
                          "pairs": [], "texts": []}
            self.cards.append(self._card)
            self._badge = ""
            self._label = None
            return
        if text in KIND_BADGE:
            # バッジは次のカードの先頭。**前のカードの欄の値ではない。**
            # 待っている見出しがあれば、その値は空だったということ。
            # ここを見ないと、最後の欄（中止情報）に次のカードの種別が入る
            if self._card is not None and self._label is not None:
                self._card["pairs"].append((self._label, ""))
                self._label = None
            self._badge = text
        if self._card is None:
            return
        self._card["texts"].append(text)

        # 見出しの入れ物（dt / th / class に InfoHeader）に入っている文字は、
        # 知らない語でも見出しとして扱う。
        # **知っている語だけを見出しにすると、知らない見出しは永久に見つからない。**
        # 見つからなければ parse-unknown.md には何も出ず、様式が変わったことに
        # 何年も気づかないまま歯抜けのデータが積み上がる（正本 9節）
        is_label = (text in LIST_COLS or self._tag in LABEL_TAGS
                    or self._in_label)

        if self._label is not None:
            if is_label:
                # **値が空の欄がある**（実物の「用途地域」は中身が <br> だけ）。
                # 次に来たのが見出しなら、前の見出しの値は空だったということ。
                # ここを見ないと1つずつずれて、隣の欄の値が入る。
                # ずれ方が「空になる」ではなく「隣の値が入る」ので気づきにくい（正本 9節）
                self._card["pairs"].append((self._label, ""))
                self._label = text
            else:
                self._card["pairs"].append((self._label, text))
                self._label = None
        elif is_label:
            self._label = text


def parse_bit_list(text, court_id, source_url="", fetched_on="",
                   name_column="未確認"):
    """BITの物件一覧（カード）を読む。人が inbox に保存したページから。

    1枚のカード＝1つの事件。事件の中に物件が複数ぶら下がることがある
    （「1．土地（農地） 2．土地（農地）」）。行データは**物件ごと**に作る。

    住所は取ったまま行データに持つ（生データは全部残す・正本 9節）。
    公開するときに落とすのは、出す側の仕事。
    """
    from common.addr import to_city

    p = Cards()
    try:
        p.feed(text)
    except Exception:
        pass

    out, unknown = [], set()
    # **カードの見出しだけを見る。** 前はページ中の文字を全部見ていたので、
    # 検索条件の「占有者が債務者・所有者」という文言が当たって、
    # 「名前の欄が見つからなかった」という警告が消えていた（実物で確認）。
    # ここが消えると、欄が無いことを人が確かめる機会がなくなる。
    # 確かめずに undisclosed を名乗ると、そのまま地番が出る（正本 3.1）
    saw_name_header = any(privacy.is_party_column(lab) or "名称" in lab
                          for card in p.cards for lab, _v in card["pairs"])

    for card in p.cards:
        item, extra = {}, {}
        for label, value in card["pairs"]:
            name = LIST_COLS.get(label)
            if not name:
                # 知らない見出しは**値ごと**残す（正本 9節）。
                # 見出しの名前だけ控えて値を捨てると、様式が変わったことに
                # 気づいたときには、その間のぶんが取り直しになる
                unknown.add(label)
                extra[label] = value
                continue
            if name in ("base_price", "min_price", "deposit"):
                item[name] = to_money(value)
            elif name in ("area_sqm", "floor_sqm"):
                item[name] = to_area(value)
            elif name in ("open_date", "view_start"):
                item[name] = to_date(value)
            elif name == "bid_period":
                item["bid_start"], item["bid_end"] = split_period(value)
            else:
                item[name] = value

        # 種別のバッジは見出しの手前にあるので Cards が控えてある。
        # 所在地はカードの地の文にある
        kind_raw, address = card.get("badge") or "", ""
        for t in card["texts"]:
            if not address and re.search(r"\d|番|丁目", t):
                pref, city = to_city(t)
                if city:
                    address = t

        status = ""
        for word in STATUS_WORDS:
            if word in (item.get("status_raw") or ""):
                status = word
                break
        item["status"] = STATUS_MAP.get(status, status)

        pref, city = to_city(address)
        items = split_items(item.get("items_raw") or "") or [("1", kind_raw)]

        # 1つの事件に物件が複数ある。行データは物件ごとに作る
        for no, raw in items:
            row = dict(item)
            row.update({
                "system": "keibai",
                "court_id": court_id,
                "court_name": card["court_name"],
                "case_no": card["case_no"],
                "item_no": no,
                # **種別はカードのバッジを使う。**
                # 「物件番号．種別」は登記上の分類で、戸建ての売り出しでも
                # その物件番号が土地なら「土地」と書いてある。実物41件のうち
                # 22件がバッジ「戸建て」／種別「土地」だった。
                # 「西宮市で今月 戸建て12件」と数えたいのはバッジのほう
                "kind_raw": raw or kind_raw,
                "kind": to_kind(kind_raw or raw),
                "address": address,
                "pref": pref,
                "city": city,
                "source_url": source_url or "",
                "fetched_on": fetched_on or "",
                # 読み方を決めていない見出しは、捨てずにここへ入れておく
                "extra": dict(extra),
                # 「名前の欄が無い」と確かめた出どころだけが undisclosed を名乗れる
                "name_column": name_column,
            })
            row["property_key"] = "%s:%s:%s" % (court_id, row["case_no"], no)
            row["key"] = "%s:%s" % (row["property_key"],
                                    row.get("open_date") or "回不明")
            out.append(row)

    if out and not saw_name_header:
        # 欄が無いのか、こちらが読めていないのか分からない。
        # 分からないうちはきつい側（individual）に倒したまま、人に知らせる
        unknown.add("＜当事者の名前らしき列が1つも見つからなかった＞")

    uniq = {r["key"]: r for r in out}
    return sorted(uniq.values(), key=lambda r: r["key"]), sorted(unknown)


# ---------------------------------------------------------------- 束ねる

def newest_file(directory):
    """その収集先の、いちばん新しい控え。辿った先のページ（--つき）は見ない。"""
    if not os.path.isdir(directory):
        return None
    names = sorted(n for n in os.listdir(directory)
                   if n.endswith(".html") and "--" not in n)
    return os.path.join(directory, names[-1]) if names else None


def inbox_files(system, ident, kind):
    """人が手で置いたページ。`<日付>-<kind>.html` の形。

    **一覧は1ページに収まらない。** 実物の大阪地裁本庁は41件あって、
    表示件数を30にしても2ページになった。2枚目以降は
    `<日付>-<kind>-2.html` のように後ろに何か付けて置いてよい。
    日付は先頭10文字で読むので、同じ日の分としてまとめて重なる。
    """
    d = os.path.join(INBOX_DIR, system, ident)
    if not os.path.isdir(d):
        return []
    return [os.path.join(d, n) for n in sorted(os.listdir(d))
            if n.endswith(".html") and ("-%s" % kind) in n]


# 人に保存してもらうもの。機械が毎回催促する（正本 3.4）。
# 人は必ず忘れるので、覚えておくのは機械の仕事。
INBOX_WANTED = {
    "list": "入札中・閲覧中の物件一覧",
    "result": "開札結果",
    "withdrawn": "取下げ等",
}
# いま読み取りが書けているのは一覧だけ。
# 読めないものを頼むと、人が手を動かしたぶんがそのまま捨てられる。しかも
# 置かれた時点で催促が止まるので、**その升は永久に空のまま**になる。
# 読み取りを書いてから、ここに足す（正本 3.4「人に渡すのは該当するURLだけ」）。
INBOX_READABLE = ("list",)

# 検索する**前**の画面にだけ出るタブ。検索したあとの一覧には出ない。
# 実物（inbox/keibai/33311/2026-09-15-list.html）で確かめた
SEARCH_FORM_MARKS = ("ブロックから探す", "裁判所から探す", "沿線から探す")


# ページ自身が名乗っている日時。「2026年09月17日 06 時現在」
PAGE_DATE = re.compile(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日[^。]{0,12}現在")


def page_date(text, fallback=""):
    """そのページが「いつ現在」のものかを、ページ自身から読む。

    **ファイル名に日付を入れてもらわなくて済む。**
    置く人にファイル名の決まりを覚えさせるより、こちらが中身を読むほうが確か。
    読めなければファイル名の先頭10文字、それも駄目なら今日にする。
    """
    m = PAGE_DATE.search(re.sub(r"<[^>]+>", " ", text[:200000]))
    if m:
        return "%04d-%02d-%02d" % (int(m.group(1)), int(m.group(2)),
                                   int(m.group(3)))
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", fallback or ""):
        return fallback
    return jst_today().isoformat()


def diagnose_list(text, rows):
    """一覧が読めなかった理由を、人の言葉で返す。読めていれば空文字。

    「0件でした」とだけ言われても、人は次に何をすればいいか分からない。
    保存し直せば済むのか、こちらの読み取りがまずいのかを先に言う。
    ここを黙ると、置いた人は「置いたのに何も起きない」としか分からない。
    """
    if rows:
        return ""
    if sum(1 for m in SEARCH_FORM_MARKS if m in text) >= 2:
        return ("**検索する前の画面**でした"
                "（裁判所を選んで「検索」を押す前のページ）。"
                "検索して物件が並んだ画面を保存し直してください")
    return ("物件のカードが1枚も見つかりませんでした。"
            "一覧の形が変わったのかもしれないので、こちらで読み取りを見直します")


BIT_SCHEDULE_URL = "https://www.bit.courts.go.jp/app/schedule/pr005/h01?courtId=%s"

# 物件一覧は**売却スケジュールとは別のページ**から探す。
# スケジュール（pr005/h01）は開札の回の予定表で、物件は1件も載っていない。
# 物件は「競売物件検索 → 裁判所から探す」（court/ps004/h04）で、
# 裁判所を選んで検索したあとに出る。URL に courtId は付かない（画面で選ぶ）。
# 2026-09-16、人が保存した実物（saved from url=…/app/court/ps004/h04）で確認した
BIT_LIST_URL = "https://www.bit.courts.go.jp/app/court/ps004/h04"
LEDGER = os.path.join(HERE, "data", "inbox-ledger.json")
PARTY_AUDIT = os.path.join(HERE, "data", "party-audit.md")
URAGAERI = os.path.join(HERE, "data", "uragaeri.md")

# **1庁だけ頼む。** 列の名前を決めるのに要るのは1枚だから。
# 6庁ぶんを並べると「6枚やるのか」と見えて、人は手が止まる。
# ここの1枚が読めて列名が固まったら、FOCUS を空にして残りを頼む。
FOCUS_COURT = "33111"       # 大阪地方裁判所 本庁（物件が41件あった）
TODO = os.path.join(HERE, "data", "inbox-todo.md")


# いま物件が出ている回の状態。これ以外の庁は一覧そのものが空になる
LIVE_STATUS = ("閲覧可能", "入札期間中")


def live_rounds(court_id):
    """その裁判所に、いま閲覧可能・入札期間中の回があるか。

    無ければ一覧は空になるので、**その庁は頼まない**。
    無いものを頼むと、人は開いて「なかった」と確かめる手間だけ使う
    （正本 3.4「人に渡すのは該当するURLだけ。全件を人に見せない」）。
    """
    path = os.path.join(SCHEDULE_DIR, "%s.json" % court_id)
    try:
        with open(path, encoding="utf-8") as f:
            rows = json.load(f)["rows"]
    except (OSError, ValueError, KeyError):
        return []
    return [r for r in rows if (r.get("status") or "") in LIVE_STATUS]


def court_name_key(name):
    """裁判所名を突き合わせ用にそろえる。「神戸地裁 尼崎支部」→「神戸地方裁判所尼崎支部」。"""
    s = re.sub(r"（[^）]*）|\([^)]*\)", "", name or "")
    s = s.replace("BIT 売却スケジュール ", "").replace("地裁", "地方裁判所")
    return re.sub(r"[\s　]+", "", s)


def court_map(sources):
    """カードに出る裁判所名から court_id を引く表。

    **どのフォルダに置いてあっても、中身の裁判所名で振り分ける。**
    置き場所を間違えても、別の庁の物件が混ざらない。
    """
    out = {}
    for src in sources:
        if src.get("kind") == "bit-schedule" and src.get("court_id"):
            out[court_name_key(src["name"])] = src["court_id"]
    return out


def deadlines(court_id, days=21):
    """その裁判所で、まもなく見られなくなる回を返す。

    競売の一覧は入札が終わると消える。過ぎてから頼んでも、もう取れない。
    だから「あと何日で消えるか」を機械が先に言う。
    """
    path = os.path.join(SCHEDULE_DIR, "%s.json" % court_id)
    try:
        with open(path, encoding="utf-8") as f:
            rows = json.load(f)["rows"]
    except (OSError, ValueError, KeyError):
        return []
    today = jst_today()
    out = []
    for r in rows:
        end = r.get("bid_end") or r.get("open_date")
        if not end:
            continue
        try:
            y, m, d = (int(x) for x in end.split("-"))
        except ValueError:
            continue
        # 取消・終了の回は保存しなくてよい。急かさない
        if (r.get("status") or "") in ("取消", "終了", "中止"):
            continue
        left = (date(y, m, d) - today).days
        if 0 <= left <= days:
            out.append((left, r.get("open_date"), r.get("status") or ""))
    return sorted(out)


def court_name(name):
    """催促の紙に出す、短い裁判所名。"""
    s = name.replace("BIT 売却スケジュール ", "")
    return re.sub(r"（[^）]*）", "", s).strip()


def audit_parties(rows):
    """当事者の名前を数えて、法人と個人の分かれ方を見る。

    **個人が1割を超えたら、法人格の語が足りていない。**
    大型店日報では、丸囲みの ㈱ ㈲ を入れ忘れて27%が個人に化けた。
    こちらでも同じことが起きていないか、毎回見えるようにしておく。
    """
    from common import privacy

    names = [r.get("winner_name") for r in rows if r.get("winner_name")]
    uniq = sorted(set(privacy.clean_name(n) for n in names if n))
    tally, samples = {}, {}
    for n in uniq:
        _kind, reason = privacy.classify_party(n, uniq)
        tally[reason] = tally.get(reason, 0) + 1
        samples.setdefault(reason, []).append(n)

    total = len(uniq)
    corp = sum(v for k, v in tally.items()
               if k in (privacy.REASON_CORP, privacy.REASON_GOV))
    person = tally.get(privacy.REASON_PERSON, 0)
    lines = [report.not_public("当事者の見分け方の点検")]
    if not total:
        lines += ["当事者の名前がまだ1件も読めていない。", ""]
    else:
        ratio = person * 100.0 / total
        lines += [
            "| 数えたもの | 数 |",
            "| --- | --- |",
            "| 当事者のユニーク数 | %d 種 |" % total,
            "| 法人と判定 | %d 種 |" % corp,
            "| 個人と判定 | %d 種（%.1f%%） |" % (person, ratio),
            "",
        ]
        if ratio > 10:
            lines += [
                "> **個人が1割を超えている。法人格の語が足りていない可能性が高い。**",
                "> `common/privacy.py` の `CORP_WORDS` を見直す。",
                "> 大型店日報では、丸囲みの ㈱ ㈲ を入れ忘れて27%が個人に化けた。",
                "",
            ]
        lines += ["## 内訳", ""]
        for reason in sorted(tally, key=lambda r: -tally[reason] if False else r):
            lines.append("- **%s**: %d 種 … 例: %s"
                         % (reason, tally[reason],
                            " / ".join(samples[reason][:3])))
        lines.append("")
    with open(PARTY_AUDIT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return total, corp, person


def has_rows(court_id):
    """その裁判所の物件が1件でも読めているか。"""
    path = os.path.join(ROWS_DIR, "%s.json" % court_id)
    try:
        with open(path, encoding="utf-8") as f:
            return bool(json.load(f).get("rows"))
    except (OSError, ValueError, KeyError):
        return False


def has_inbox(court_id):
    """その裁判所に、人が何かを置いてくれているか。"""
    return any(inbox_files("keibai", court_id, k) for k in INBOX_WANTED)


def chase_inbox(courts, ingested=(), troubles=None):
    """まだ置かれていないものを数えて、催促の紙を作る。

    渡すのは**該当するURLだけ**。全件を人に見せない。
    まもなく消えるものは警告する。
    取り込み済みは台帳に書いて、二度と催促しない。

    `ingested` は**中身が1件以上取れた**ファイル。台帳に入れてよいのはこれだけ。
    置いてあるだけのものを取り込み済みにすると、人が手を動かしたのに何も入って
    いない状態で催促が止まる（実際に33311で起きた）。
    `troubles` は「置いてあるのに読めなかった」ファイルと、その理由。
    黙って捨てず、必ず紙に出す（正本 9節）。
    """
    troubles = troubles or {}
    try:
        with open(LEDGER, encoding="utf-8") as f:
            ledger = json.load(f)
    except (OSError, ValueError):
        ledger = {"取り込み済み": []}
    was_done = set(ledger.get("取り込み済み", []))

    # 台帳は「中身が取れた」ものの控え。毎回、実際に取れたもので作り直す。
    # 片づけて inbox から消えたものは、取れた実績として残す。
    # こうすると、取れていないのに取り込み済みになっていた分が自然に落ちる
    done = set(ingested) | {r for r in was_done
                            if not os.path.exists(os.path.join(HERE, r))}
    found = sorted(set(ingested) - was_done)

    # まだ1件も読めていないうちは、1庁だけ頼む。
    # ただし**人がもう置いてくれた裁判所は、必ず見る**。
    # ここを外すと、置いたのに「検索前の画面でした」も期限も届かない
    got_rows = any(has_rows(c) for c, _ in courts)
    if FOCUS_COURT and not got_rows:
        keep = [(c, n) for c, n in courts
                if c == FOCUS_COURT or has_inbox(c)]
        courts = keep or courts

    missing, quiet = [], []
    for court_id, name in courts:
        # いま閲覧可能・入札期間中の回が1つも無ければ、一覧は空になる。
        # 無いものを頼むと、人は開いて「なかった」と確かめる手間だけ使う
        if not live_rounds(court_id):
            quiet.append(court_name(name))
            continue
        # 人に渡すのは、その裁判所のページ1本だけ。全件を見せない
        for kind, label in INBOX_WANTED.items():
            # 一覧は物件検索のページから。スケジュールのページには物件が無い
            url = BIT_LIST_URL if kind == "list" else BIT_SCHEDULE_URL % court_id
            # 読み取りがまだ無いものは頼まない。頼むと捨てるだけになる
            if kind not in INBOX_READABLE:
                continue
            files = inbox_files("keibai", court_id, kind)
            # 「置いてある」だけでは足りない。**中身が取れていること**で見る
            files = [f for f in files
                     if os.path.relpath(f, HERE).replace(os.sep, "/") in done]

            if not files:
                note = label
                bad = [troubles.get(os.path.relpath(f, HERE).replace(os.sep, "/"))
                       for f in inbox_files("keibai", court_id, kind)]
                if any(b for b in bad):
                    note += "（**置き直しが要ります**。上の節を見てください）"
                missing.append((court_id, name, kind, note, url))

    lines = [report.not_public("まだ置かれていないもの（%d 件）"
                              % len(missing))]

    # **置いてあるのに読めなかったものを、いちばん先に言う。**
    # 人はもう手を動かしている。「まだ置かれていない」とだけ書くと、
    # 置いたはずなのに催促され続けることになって、どこでつまずいたのか分からない
    if troubles:
        lines += ["## 置いてくださったのに、読めなかったもの", ""]
        for rel in sorted(troubles):
            lines.append("- `%s`" % rel)
            lines.append("  - %s" % troubles[rel])
        lines += [
            "",
            "読めなかったので、この分はまだ数に入っていません。",
            "下の手順で保存し直してください。",
            "",
        ]

    if FOCUS_COURT and not got_rows:
        lines += [
            "**いまお願いしたいのは1枚だけです。**",
            "列の名前が分かれば読み取りを直せるので、まず1庁ぶんで足ります。",
            "これが読めたら、残りの裁判所をお願いします。",
            "",
        ]

    # まもなく消えるものを先に出す。過ぎてから頼んでも、もう取れない
    warn = []
    want = {c for c, _n, _k, _l, _u in missing}
    for court_id, name in courts:
        if court_id not in want:
            continue                 # もう置いてもらった庁は急かさない
        for left, open_date, status in deadlines(court_id):
            warn.append((left, court_id, court_name(name), open_date, status))
    if warn:
        lines += ["## 急ぐもの", ""]
        for left, court_id, name, open_date, status in sorted(warn):
            lines.append("- **%s の %s 開札の回は、あと %d 日で入札が終わります。**"
                         "そのあと一覧から消えます（状態: %s）"
                         % (name, open_date, left, status or "公告前"))
        lines.append("")

    if missing:
        lines += [
            "## 保存してほしいもの",
            "",
            "BITの物件一覧は、検索した**あと**の画面にしか出ない。",
            "検索結果のURLは控えても開き直せないので、人の手で保存してもらう",
            "（2026-09-15 確認）。中身が取れたら次回から催促しない。",
            "",
            "1. 下のURL（競売物件検索・裁判所から探す）を開く",
            "2. 裁判所を選ぶ（URLには裁判所が入らない。画面で選ぶ）",
            "3. **「検索」を押す**（ここを飛ばすと検索前の画面が保存される）",
            "4. **右上の「表示件数」を「30件」にする**（30が最大）",
            "   はじめは「10件」。30にしても31件以上あればページが分かれる",
            "5. Ctrl+S（Mac は Command+S）で保存",
            "   「ファイルの種類」は「ウェブページ、HTMLのみ」",
            "   Safari は「完全」しか選べないことがあるので、その場合は Chrome か Edge で",
            "6. ページが分かれていたら、次のページでも 5 をくり返す",
            "",
            "**保存する前に、画面に物件が並んでいることを見てください。**",
            "「大阪地方裁判所本庁 令和06年(ケ)第414号」のような事件番号が",
            "並んでいれば当たりです。検索条件の入力欄しか無ければ、まだ3が済んでいません。",
            "",
            "### ファイル名と置き場所",
            "",
            "**名前は気にしなくてよい。** 決まりは1つだけ。",
            "",
            "- 名前のどこかに `-list` が入っていること",
            "",
            "日付はページ自身に「○年○月○日 ○時現在」と書いてあるので、そこから読む。",
            "どの裁判所かもカードに書いてあるので、そこから読む。",
            "**フォルダを間違えても、別の庁に混ざらない。**",
            "ページが2枚に分かれたら、`-list` さえ入っていれば",
            "`あ-list.html` `い-list.html` でも `1-list.html` `2-list.html` でもよい。",
            "",
            "### 保存を楽にする",
            "",
            "- ブラウザの保存先を `inbox/keibai/` にしておくと、毎回選ばなくてよい",
            "- 「ファイルの種類」は一度「HTMLのみ」にすると次から覚えている",
            "- Chrome なら保存のあと「ダウンロード」バーから名前を直せる",
            "- 同じ日に何度も保存しても害はない。**同じ物件は上書きされるだけ**",
            "",
            "| 裁判所 | ほしいもの | 開くURL | 置く場所 |",
            "| --- | --- | --- | --- |",
        ]
        for court_id, name, kind, label, url in missing:
            lines.append("| %s | %s | %s | `inbox/keibai/%s/<日付>-%s.html` |"
                         % (court_name(name), label, url or "—",
                            court_id, kind))
    else:
        lines.append("ぜんぶ置かれている。")
    lines.append("")
    if quiet:
        lines += [
            "## いまは頼まない裁判所",
            "",
            "閲覧可能・入札期間中の回が1つも無いので、開いても一覧は空になる。",
            "回が立ったら、またここに出てくる。",
            "",
        ]
        for n in quiet:
            lines.append("- %s" % n)
        lines.append("")
    if found:
        lines.append("今回あたらしく取り込んだもの: %s" % " / ".join(found))
        lines.append("")

    with open(TODO, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    ledger["取り込み済み"] = sorted(done)
    with open(LEDGER, "w", encoding="utf-8") as f:
        json.dump(ledger, f, ensure_ascii=False, indent=1)
        f.write("\n")

    gh = os.environ.get("GITHUB_STEP_SUMMARY")
    if gh:
        with open(gh, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    print("まだ置かれていない保存ページ: %d 件（data/inbox-todo.md）" % len(missing))


def load_rows(court_id):
    """いままでの行データを読む。無ければ空。"""
    path = os.path.join(ROWS_DIR, "%s.json" % court_id)
    try:
        with open(path, encoding="utf-8") as f:
            return {r["key"]: r for r in json.load(f)["rows"]}
    except (OSError, ValueError, KeyError):
        return {}


def mark_saishutsu(merged):
    """**こちらが前にも見ている回**に印をつける。

    競売には「9月 公告 → 10月 開札 → 不調 → 11月 また公告」という流れがある。
    （相手のページには「不売」と出る。こちらが書く語は「不調」。正本 6節）
    合計だけを見ていると、不調が続く不況期に件数が勝手に増えて、
    「市場が活発になった」と逆に読めてしまう。これがいちばんこわい間違い。
    だから、初めて見た回と、前にも見ている回を分けられるようにしておく。

    **「再公告」ではなく「再出」**（2026-09-19 に名前を直した）。
    こちらが分かるのは「こちらが前にも見たか」だけ。
    相手が2回目の公告を出したのかどうかは、こちらが見る前を知らないので
    分からない。**持っていない知識を名乗らない。**
    """
    first = {}
    for r in merged.values():
        pk = r.get("property_key")
        if not pk:
            continue
        d = r.get("open_date") or ""
        if pk not in first or d < first[pk]:
            first[pk] = d
    裏返り = []
    for r in merged.values():
        pk = r.get("property_key")
        いま = bool(pk and (r.get("open_date") or "") != first.get(pk))
        前 = r.get("saishutsu")
        if 前 is None:
            r["saishutsu"] = いま
        elif bool(前) != いま:
            # **決めた値は動かさない。** 動かすと、公開した升が黙って入れ替わる
            裏返り.append((r.get("key"), bool(前), いま))
    return merged, 裏返り


def write_uragaeri(裏返り):
    """**決めたあとに答えが変わった行**を控える（2026-09-19）。

    `mark_saishutsu()` は「その物件で、こちらが知っているいちばん早い回」を
    基準に新規／再公告を決める。**基準が、あとから来たデータで動く。**

        いま      11月の回だけ見えている        → 新規
        あとから  8月の回（過去データ）が入る  → 11月の回が**再公告に裏返る**

    裏返っても親（公告）の合計は変わらないので、`kazu_ga_au()` は通る。
    **公開した升が黙って入れ替わる形**だった。

    だから決めた値は動かさない。**動かさなかったことを、ここに控える。**
    黙って捨てるのでも、黙って直すのでもない（正本 9節）。

    過去データ（3年分）を入れる日に、まとまって出るはず。
    そのとき「いままでの新規は、こちらが見る前の回を知らなかっただけ」
    という判断が要る。**機械が勝手に決めてよいことではない。**
    """
    if not 裏返り:
        if os.path.exists(URAGAERI):
            os.remove(URAGAERI)
        return
    lines = [report.not_public("あとから答えが変わった行（%d 件）" % len(裏返り))]
    lines.append("")
    lines.append("`saishutsu`（初出か再出か）を決めたあとで、"
                 "より早い回のデータが入った。")
    lines.append("**決めた値は動かしていない。** 公開した升が黙って"
                 "入れ替わらないようにするため。")
    lines.append("")
    lines.append("| 裁判所 | 鍵 | いまの値 | あとから来た答え |")
    lines.append("| --- | --- | --- | --- |")
    for cid, key, 前, いま in sorted(裏返り):
        lines.append("| %s | `%s` | %s | %s |"
                     % (cid, key,
                        "再公告" if 前 else "新規",
                        "再公告" if いま else "新規"))
    with open(URAGAERI, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("::error::**あとから答えが変わった行が %d 件**（data/uragaeri.md）。"
          % len(裏返り))
    print("決めた値は動かしていない。どちらを採るかは人が決める")


# ---------------------------------------------------------------- 完全観測の印
#
# 完全観測かどうかを、生データが在ることや HTTP 200 から推し量らない
# （common/kanzen.py）。取得段（ここ）が、確かめたことだけを印にする。
# この置き場が必要とする印は5つ（spec/kanzen_keibai.md 2）。
KANZEN_HITSUYOU = ("入口に届いた", "必要本文を受け取った",
                   "ページ送りを最後まで受け取った", "解析できた",
                   "private保存成功")

# 取得方式・観測元は、この置き場では固定（人が保存した一覧を、裁判所ごとに読む）。
# 観測元は「物件が載っているページ」ではなく、行データの `source_url` と
# 同じ式（BIT_SCHEDULE_URL % 裁判所）にそろえる。実物のURLと違っても、
# 観測の同一性を見分ける識別子として使う（spec/kanzen_keibai.md 2）
KANZEN_HOUSHIKI = "人が保存した一覧"

# ページ送り（BITのpager）の中の、いまのページ番号の1つ。
# 選べる（=まだ行っていない）ページ番号には onclick="getData(N)" が付き、
# いまのページ番号だけ付かない（実物の保存ページで確認。押す先が無いので）。
_PAGE_GENZAI = re.compile(
    r'<div class="page-item disabled">\s*'
    r'<a class="page-link" href="[^"]*">(\d+)</a>')
# 「末尾」（aria-label="last"）の onclick の番号が、そのまま最後のページ番号になる
_PAGE_SAIGO = re.compile(r'onclick="getData\((\d+)\);"[^>]*aria-label="last"')


def pager_info(text):
    """保存した1枚のページから、「今のページ番号」と「最後のページ番号」を読む。

    読めなければ None（分からない）。**同じページに pager が2つ（上と下）
    出ることがあるが、同じ値のはず。値が食い違ったら確かめられなかった扱いにする**
    （確かめられなかった側に倒す。推し量って片方を採らない）。
    """
    genzai = set(int(m.group(1)) for m in _PAGE_GENZAI.finditer(text or ""))
    saigo = set(int(m.group(1)) for m in _PAGE_SAIGO.finditer(text or ""))
    if len(genzai) != 1 or len(saigo) != 1:
        return None
    return next(iter(genzai)), next(iter(saigo))


def kansoku_kihon_shirushi(texts):
    """入口に届いた・必要本文を受け取った・ページ送りを最後まで受け取った の3つ。

    texts は、その(裁判所, 日)に置かれた全ページの中身（読めなかった分は None）。
    """
    if not texts or any(t is None for t in texts):
        return {"入口に届いた": kanzen.IIE,
                "必要本文を受け取った": kanzen.WAKARANAI,
                "ページ送りを最後まで受け取った": kanzen.WAKARANAI}
    honbun = (kanzen.HAI if all(t.rstrip().lower().endswith("</html>") for t in texts)
             else kanzen.IIE)
    yomi = [pager_info(t) for t in texts]
    if any(y is None for y in yomi):
        pager = kanzen.WAKARANAI
    else:
        saigo_atsumari = {y[1] for y in yomi}
        if len(saigo_atsumari) != 1:
            pager = kanzen.WAKARANAI          # ページによって最後の番号が食い違う
        else:
            saigo = next(iter(saigo_atsumari))
            genzai_atsumari = {y[0] for y in yomi}
            pager = (kanzen.HAI if genzai_atsumari == set(range(1, saigo + 1))
                     else kanzen.IIE)
    return {"入口に届いた": kanzen.HAI, "必要本文を受け取った": honbun,
           "ページ送りを最後まで受け取った": pager}


def kansoku_kaiseki_shirushi(text_for_diag, rows, mae_kensu, mae_kagi, ima_kagi):
    """解析できた の印。

    0件のとき・半分以上が一度に消えたときは、消えた／読めなかったと決めつけず
    「分からない」へ倒す（`kanzen.zero_gyou` `kanzen.kyugen`。spec/kanzen.md）。
    戻り値は (印, 読めなかった理由。読めていれば空文字)。
    """
    if not rows:
        why = diagnose_list(text_for_diag, rows)
        base = kanzen.zero_gyou(mae_kensu, 0, False)
        return (base, why) if base == kanzen.WAKARANAI else (kanzen.IIE, why)
    if kanzen.kyugen(mae_kagi, ima_kagi):
        return kanzen.WAKARANAI, ""
    return kanzen.HAI, ""


def kansoku_hozon_shirushi(paths, env=None):
    """private保存成功 の印。ファイルの実体（realpath）が金庫（KINKO_DIR）の中か。"""
    env = os.environ if env is None else env
    d = env.get("KINKO_DIR") or ""
    if not d or not os.path.isdir(d):
        return kanzen.WAKARANAI            # 金庫の場所が渡されていない
    kinko = os.path.realpath(d)
    for p in paths:
        real = os.path.realpath(p)
        if real != kinko and not real.startswith(kinko + os.sep):
            return kanzen.IIE
    return kanzen.HAI


def kansoku_kaku(cid, day, file_names, shirushi, kanzen_flag, riyuu):
    """その(裁判所, 日)の観測の印を、置いたページの隣（金庫の中）に小さなJSONで書く。"""
    out_dir = os.path.join(INBOX_DIR, "keibai", cid)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "%s-kanzen.json" % day)
    body = {
        "対象": "keibai:%s" % cid,
        "裁判所": cid,
        "日": day,
        "印": shirushi,
        "完全観測": kanzen_flag,
        "理由": riyuu,
        "取得方式": KANZEN_HOUSHIKI,
        "観測元": BIT_SCHEDULE_URL % cid,
        "ファイル": sorted(file_names),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(body, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    return path


def merge_snapshot(merged, rows, day, kanzen_flag=None, mae_kanzen_hi=None):
    """その日の一覧を、いままでの行データに重ねる。

    一覧は上書きされる。だから「その日に見えたもの」を毎回重ねて、
    **いつ初めて出たか（first_seen）**と**いつまで見えていたか（last_seen）**を作る。
    first_seen が無いと、その月に新しく出た件数（フロー）が数えられず、
    いま出ている件数（ストック）しか出せない。それだと同じ物件を翌月また数えてしまう。

    kanzen_flag … 今回の(裁判所, 日)観測が完全観測かどうか（True/False/None）。
                  True のときだけ、見えた行の `kakunin_saigo`（完全観測の日のうち、
                  見えた最後の日）をこの日に進める。**不完全な回は進めない**
                  （spec/kanzen.md「不完全な回は、消失判定の時点を進めない」）。
    mae_kanzen_hi … 直前の完全観測の日。呼ぶ側が
                    `kanzen.sabun_dashite_yoi()` で「出してよい」と決めたときだけ渡す。
                    無ければ None（＝この重ねでは「消えた」を1件も付けない）。
    """
    for r in rows:
        old = merged.get(r["key"])
        if old:
            r["first_seen"] = old.get("first_seen") or day
            # 前に見たときの状態も残す。消えたことに気づくため
            history = list(old.get("seen", []))
            if day not in history:
                history.append(day)
            r["seen"] = sorted(history)
        else:
            r["first_seen"] = day
            r["seen"] = [day]
        # **一度決めた「新規か再公告か」を持ち越す**（2026-09-19）。
        # `first_seen` と同じ扱い。持ち越さないと `mark_saishutsu()` が
        # 毎回いちから決め直し、**あとから早い回が入った日に過去が裏返る**
        if old:
            # `re_notice` は 2026-09-19 まで使っていた名前。
            # **名前を直しても、決めた値は失わない。**
            # 保存済みの行が書き直されたら、この渡りは要らなくなる
            前 = old.get("saishutsu", old.get("re_notice"))
            if 前 is not None:
                r["saishutsu"] = 前
            r["kakunin_saigo"] = old.get("kakunin_saigo")
        if kanzen_flag:
            r["kakunin_saigo"] = day
        r["last_seen"] = day
        merged[r["key"]] = r

    # その日の一覧に出てこなかった行。**「消えた」を付けるのは、今回が完全観測で、
    # 直前の完全観測でも見えていた（kakunin_saigo が直前の完全観測の日と同じ）ときだけ**
    # （spec/kanzen_keibai.md 3）。それ以外は何もしない。あとで完全観測がそろったときに
    # 決める（不完全な回のうちに「消えた」と言わない。止まる側に倒す）
    if not (kanzen_flag and mae_kanzen_hi):
        return merged
    today_keys = {r["key"] for r in rows}
    for key, old in merged.items():
        if key in today_keys:
            continue
        if old.get("last_seen", "") >= day or old.get("gone_on"):
            continue
        if old.get("kakunin_saigo") != mae_kanzen_hi:
            continue                         # 直前の完全観測で見えていたとは言えない
        old["gone_on"] = day
        old["gone_kansoku"] = [mae_kanzen_hi, day]
        old.setdefault("status", aggregate.GONE)
    return merged


def main():
    with open(os.path.join(HERE, "sources.json"), encoding="utf-8") as f:
        sources = json.load(f)["sources"]

    os.makedirs(SCHEDULE_DIR, exist_ok=True)
    total, courts = 0, 0
    court_list = []
    name_col = {}

    for src in sources:
        if src.get("kind") != "bit-schedule" or src.get("handoff"):
            continue
        court_id = src.get("court_id")
        if not court_id:
            continue
        court_list.append((court_id, src["name"]))
        # name_column は**その裁判所の**収集先のものを使う。
        # ここで控えないと、下のループで最後の src のものが混ざる
        name_col[court_id] = src.get("name_column", "未確認")

        paths = []
        newest = newest_file(os.path.join(RAW_DIR, src["id"]))
        if newest:
            paths.append(newest)
        paths += inbox_files("keibai", court_id, "schedule")
        if not paths:
            continue

        rows = []
        for path in paths:
            # ファイル名の頭が取得日（2026-09-14.html / 2026-09-14-schedule.html）
            fetched_on = os.path.basename(path)[:10]
            rows += parse_bit_schedule(read_page(path), court_id,
                                       src.get("url") or "", fetched_on)
        uniq = {r["key"]: r for r in rows}
        rows = sorted(uniq.values(), key=lambda r: r["open_date"])

        out = {
            "court_id": court_id,
            "name": src["name"],
            "何これ": "開札の回の予定表。競売のコホートの定義になる",
            "rows": rows,
        }
        with open(os.path.join(SCHEDULE_DIR, "%s.json" % court_id), "w",
                  encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
            f.write("\n")
        print("%s … 開札の回 %d 件" % (src["name"], len(rows)))
        total += len(rows)
        courts += 1

    print("裁判所 %d 庁 / 開札の回 %d 件を data/schedule/ に置いた" % (courts, total))

    # 人が inbox に置いた物件一覧を読む。
    # 保存した日ごとに1枚（スナップショット）あるので、古い順に重ねて
    # 「いつ初めて見たか」「いつまで見えていたか」を作る。
    # 一覧は上書きされるので、これが無いとフロー（その月に新しく出た件数）が数えられない。
    os.makedirs(ROWS_DIR, exist_ok=True)
    rows_total, unknown = 0, set()
    ingested, troubles = [], {}
    any_card = False          # 一覧を1枚でも読めたか。読めていないなら何も確かめていない
    # 一覧のファイルを全部集める。**どのフォルダに置いてあっても構わない。**
    # 振り分けはファイル名ではなく、カードに書いてある裁判所名で決める。
    # 置き場所を間違えても、別の庁の物件が混ざらない
    by_court = court_map(sources)
    names = dict(court_list)
    paths = []
    for court_id, _name in court_list:
        paths += inbox_files("keibai", court_id, "list")
    paths += inbox_files("keibai", "", "list")       # 直下に置かれたもの
    paths = sorted(set(paths))

    merged = {c: load_rows(c) for c, _n in court_list}
    known_courts = {c for c, _n in court_list}

    # 1st pass … ファイルごとに読み、行データと、寄せる先の裁判所・日付を決める。
    # **一覧は1ページに収まらないことがある**（大阪地裁本庁は41件で2ページになった）。
    # 2枚目以降は「(裁判所, 日付)」が同じなので、ここではまだ重ねない
    per_file = []             # [(path, day, text_or_None, rows, court_id_or_None)]
    for path in paths:
        rel = os.path.relpath(path, HERE).replace(os.sep, "/")
        # フォルダ名からの当て推量は、中身で決まらなかったときの控えにだけ使う
        folder = os.path.basename(os.path.dirname(path))
        try:
            text = read_page(path)
        except OSError:
            troubles[rel] = "ファイルが読めませんでした（保存し直してください）"
            fname_day = os.path.basename(path)[:10]
            day = fname_day if re.fullmatch(r"\d{4}-\d{2}-\d{2}", fname_day) else None
            per_file.append((path, day, None, [],
                             folder if folder in known_courts else None))
            continue
        # 日付はページ自身から読む。ファイル名は控えにしか使わない
        day = page_date(text, os.path.basename(path)[:10])
        got, unk = parse_bit_list(text, folder,
                                  BIT_SCHEDULE_URL % folder, day,
                                  name_column=name_col.get(folder, "未確認"))
        unknown.update(unk)
        if not got:
            # 読めなかった理由を控えて、催促の紙に出す。黙って捨てない
            troubles[rel] = diagnose_list(text, got)
            per_file.append((path, day, text, [],
                             folder if folder in known_courts else None))
            continue
        ingested.append(rel)
        any_card = True
        # カードごとに、書いてある裁判所へ振り分ける
        groups = {}
        for r in got:
            cid = by_court.get(court_name_key(r.get("court_name")), folder)
            if cid != r["court_id"]:
                r["court_id"] = cid
                r["property_key"] = "%s:%s:%s" % (cid, r["case_no"],
                                                  r["item_no"])
                r["key"] = "%s:%s" % (r["property_key"],
                                      r.get("open_date") or "回不明")
                r["source_url"] = BIT_SCHEDULE_URL % cid
            groups.setdefault(cid, []).append(r)
        # 1枚のページが複数の裁判所にまたがることは、ふつう無い。
        # ページそのものの出来（本文がそろっているか等）は、寄せた先どの裁判所にも同じく効く
        for cid, rows in groups.items():
            per_file.append((path, day, text, rows, cid))

    # 2nd pass … (裁判所, 日付) ごとにページをまとめ、古い日から重ねる
    by_court_day = {}
    for path, day, text, rows, cid in per_file:
        if cid is None or day is None:
            continue
        by_court_day.setdefault((cid, day), []).append((path, text, rows))

    kanzen_kensa = []          # 報告用（(裁判所, 日, 完全観測, 理由)）
    for cid in sorted({c for c, _d in by_court_day} | set(merged)):
        m = merged.setdefault(cid, {})
        hizuke = sorted({d for c, d in by_court_day if c == cid})
        for day in hizuke:
            pages = by_court_day[(cid, day)]
            day_rows = []
            for _p, _t, rws in pages:
                day_rows += rws

            # 直前の完全観測（このコートの、いま持っている行データから逆算する。
            # `kakunin_saigo` は完全観測の日にだけ進むので、その最大値がそのまま
            # 「直前の完全観測の日」になる）
            mae_hi = max((v.get("kakunin_saigo") for v in m.values()
                         if v.get("kakunin_saigo")), default=None)
            mae_kagi = ({k for k, v in m.items() if v.get("kakunin_saigo") == mae_hi}
                       if mae_hi else set())
            ima_kagi = {r["key"] for r in day_rows}

            shirushi = kansoku_kihon_shirushi([t for _p, t, _r in pages])
            shirushi["private保存成功"] = kansoku_hozon_shirushi(
                [p for p, _t, _r in pages])
            # 読めなかった理由（診断文）は、ファイルごとに1st passで
            # 既に `troubles` へ控えてある（day_rows が空なら、寄せた全ファイルが
            # 空だったということ）。ここでは完全観測の印にだけ使う
            kaiseki, _why = kansoku_kaiseki_shirushi(
                "".join(t or "" for _p, t, _r in pages), day_rows,
                len(mae_kagi), mae_kagi, ima_kagi)
            shirushi["解析できた"] = kaiseki

            kanzen_flag, riyuu = kanzen.kimeru(shirushi, KANZEN_HITSUYOU)
            ima_kansoku = {"kanzen": kanzen_flag, "moto": BIT_SCHEDULE_URL % cid,
                          "houshiki": KANZEN_HOUSHIKI}
            mae_kansoku = ({"kanzen": True, "moto": BIT_SCHEDULE_URL % cid,
                           "houshiki": KANZEN_HOUSHIKI} if mae_hi else None)
            dashite_yoi, _ = kanzen.sabun_dashite_yoi(mae_kansoku, ima_kansoku)

            merge_snapshot(m, day_rows, day, kanzen_flag=kanzen_flag,
                           mae_kanzen_hi=mae_hi if dashite_yoi else None)
            kansoku_kaku(cid, day, [os.path.basename(p) for p, _t, _r in pages],
                        shirushi, kanzen_flag, riyuu)
            kanzen_kensa.append((cid, day, kanzen_flag, riyuu))

    if kanzen_kensa:
        kanzen_su = sum(1 for _c, _d, k, _r in kanzen_kensa if k is True)
        print("観測 %d 件のうち、完全観測は %d 件（印は inbox/keibai/<庁>/ に置いた）"
             % (len(kanzen_kensa), kanzen_su))

    uragaeri = []
    for court_id in sorted(merged):
        if not merged[court_id]:
            continue
        _, 裏返り = mark_saishutsu(merged[court_id])
        uragaeri += [(court_id,) + x for x in 裏返り]
        rows = sorted(merged[court_id].values(), key=lambda r: r["key"])
        name = names.get(court_id, court_id)
        with open(os.path.join(ROWS_DIR, "%s.json" % court_id), "w",
                  encoding="utf-8") as f:
            json.dump({"court_id": court_id, "name": name, "rows": rows},
                      f, ensure_ascii=False, indent=1)
            f.write("\n")
        print("%s … 物件 %d 件" % (court_name(name), len(rows)))
        rows_total += len(rows)
    if rows_total:
        print("物件 %d 件を data/rows/keibai/ に置いた" % rows_total)
    write_uragaeri(uragaeri)
    all_rows = []
    for court_id, _ in court_list:
        try:
            with open(os.path.join(ROWS_DIR, "%s.json" % court_id),
                      encoding="utf-8") as f:
                all_rows += json.load(f).get("rows", [])
        except (OSError, ValueError):
            pass
    total, corp, person = audit_parties(all_rows)
    print("当事者 %d 種（法人 %d / 個人 %d）" % (total, corp, person))

    # 知らない見出しは捨てずに報告する。次はここを見て LIST_COLS に足す
    lines = [report.not_public("まだ読み方を決めていない見出し")]
    if any("名前らしき列" in u for u in unknown):
        lines += [
            "## 当事者の名前の列が見つからなかった",
            "",
            "**欄が無いのか、こちらが読めていないのか分からない。**",
            "分からないうちはきつい側（individual・町丁目まで）に倒してある。",
            "実物を見て、名前の欄が本当に無いと確かめたら、",
            "`sources.json` の `name_column` を「無し（確認ずみ）」に書き換える。",
            "そこを書き換えるまで、地番は出ない。",
            "",
        ]
    cols = sorted(u for u in unknown if "名前らしき列" not in u)
    if cols:
        lines.append("物件一覧に、こちらが知らない列があった。")
        lines.append("parse.py の LIST_COLS に足すと、中身が取り出せるようになる。")
        lines.append("いまは捨てずに各行の `extra` に入れてある。")
        lines.append("")
        for u in cols:
            lines.append("- `%s`" % u)
    elif any_card:
        lines.append("知らない見出しは無かった。")
    elif unknown:
        pass                      # 名前の欄の報告だけ。上の節に出してある
    else:
        lines.append("物件一覧をまだ1枚も読めていないので、**まだ何も確かめていない**。")
        lines.append("「知らない見出しが無い」ではなく「見に行けていない」。")
    lines.append("")
    # **ファイルごと上書きしない。** この記録には aggregate.py も章を足す
    # （「段階が決まらなかった行」）。上書きすると、走らせる順番で片方が消える。
    # 消えても動くので、走らせても気づけない。put_chapter は同じ見出しの章を
    # 入れ替えるので、何回どの順で動かしても同じ形になる
    report.put_head(UNKNOWN, "\n".join(lines))

    # 同じ庁の、あとの日付の分がちゃんと読めていれば、古い失敗はもう催促しない。
    # 済んだことを言い続けると、本当に手が要るものが埋もれる
    newest = {}
    for rel in ingested:
        d = os.path.dirname(rel)
        newest[d] = max(newest.get(d, ""), os.path.basename(rel)[:10])
    troubles = {rel: why for rel, why in troubles.items()
                if os.path.basename(rel)[:10] >= newest.get(
                    os.path.dirname(rel), "")}
    for rel, why in sorted(troubles.items()):
        print("読めなかった: %s … %s" % (rel, re.sub(r"\*\*", "", why)))
    chase_inbox(court_list, ingested, troubles)


if __name__ == "__main__":
    main()
