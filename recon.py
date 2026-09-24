#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""役所が土地を売っているページを偵察する。

いきなり全部を集めようとすると、たいてい最初のページで詰まる。
なので先に「そのページが機械で読める形かどうか」だけを確かめる。
shutten（大店立地法ウォッチ）の recon.py を写して、競売と公売の2段に合わせた。
国有財産・公有財産は制度が別なので姉妹サイト側に置く（README「棚は2段」）。

やること
  1. robots.txt を見て、取りに行ってよいか確かめる（中身も控えに残す）
  2. ページを取得して data/raw/<id>/<日付>.html に残す
  3. 中身が「HTMLの表」か「PDFの並び」かを判定して、レポートに書く
  4. DESIGN 13章の「未確認のこと」に答えを入れるための手がかりを拾う

判定の見方
  表        … HTMLの表がある。いちばん楽。すぐ自動化できる
  Excel     … xlsx/xls が置いてある。実はいちばん楽なこともある
  PDF       … PDFのリンクが並んでいる。中を読むのに一手間かかる
  リンク集   … よそのサイトへの入口。取り込まず、人が sources.json に足す種にする
  わからない … 自分の目で見に行く必要がある

いちばん大事な決まり（DESIGN 1章）
  BIT（bit.courts.go.jp）からは3点セットを絶対に取らない。
  ここでは二重に守る。
    - BIT のページからはリンクを1本も辿らない（何が置いてあるかを報告するだけ）
    - BIT から application/pdf が返ってきたら、中身を捨ててレポートに出す
  この2つは tests/test_recon.py で固定してある。壊したらテストが落ちる。

レポートの本文は data/recon-report.md にだけ書く（公開しない）。
公開される Actions のログと要約には、決まった形の数行だけを出す（下の「公開ログ」）。

Python 3 の標準ライブラリだけで動く。GitHub Actions でそのまま動く。
"""

import hashlib
import html
import json
import os
import re
import socket
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import warnings
from html.parser import HTMLParser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import kado  # noqa: E402  取得の門はここ1か所（門の無い通信は閉じる）
from common import site  # noqa: E402  名乗りは1か所から配る
from common import report  # noqa: E402
from common import torikata  # noqa: E402  取得元の4語（一覧・kiwadoi の表示に使う）
from common.jst import today_str  # noqa: E402  日付は日本時間で決める
from common.jst import today as jst_today  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

# 名乗りの形は姉妹サイト共通（正本 3.4）。誰が来ているかと、
# どこへ言えば止まるかが、ログを見るだけで分かるようにする。
# URLは common/site.json の1か所にだけ書く。404になるURLは入れない
UA = site.user_agent()

WAIT = 5          # 同じ相手に続けて出すときに空ける秒数（正本 3.4 で5秒以上）
TIMEOUT = 40

# この応答が返ったら、その回は中止する。押し込まない（正本 3.4）
BACK_OFF = (429, 503)

# 相手が黙ったときに永久に待たないよう、ソケット側でも縛っておく
# （個々の urlopen に timeout= を渡し忘れても、ここが最後の網になる）。
socket.setdefaulttimeout(TIMEOUT)

# 段の呼び名（レポートの見出しに使う）
SYSTEM_NAME = {
    "keibai": "競売（裁判所）",
    "kobai": "公売（税の差押え）",
    "kokuyu": "国有財産（財務局）— 姉妹サイト送り",
    "koyu": "公有財産（自治体）— 姉妹サイト送り",
}


# ---------------------------------------------------------------- BITの門番

BIT_HOST = "bit.courts.go.jp"

# 3点セットに向かうリンクの目印。リンク文字でも href でも見る。
# 「ダウンロード」だけの素っ気ないリンクが3点セットだった、ということがあり得るので
# 語そのものを弾く（DESIGN 5.1）。
SANTEN = re.compile(
    r"3\s*点セット|３点セット|物件明細|現況調査|評価書|ダウンロード", re.I)

# リンク文字が「詳細」のように素っ気なくても、行き先のファイル名で分かることがある。
# 役所のふつうのPDF（/download/ の下に置かれた案内など）まで巻き込まないよう、
# 3点セットを指す綴りだけに絞ってある。
SANTEN_HREF = re.compile(r"santen|sannten|3ten|3tensetto", re.I)

# **辿らなかった数を、辿らない側で数える。**
# 報告は「（辿った数: 0 本）」と 0 を直接書いていた。
# **数えていない 0 は、数えた 0 と見分けられない。**
# 実測（2026-09-20）: 辿るようにしても 0 のままだった。
SANTEN_SKIPPED = [0]


def is_bit(url):
    """BIT（不動産競売物件情報サイト）のページか。"""
    host = urllib.parse.urlparse(url or "").netloc.lower()
    return host == BIT_HOST or host.endswith("." + BIT_HOST)


def is_santen_link(href, label):
    """3点セットに向かうリンクか。迷ったら「そうだ」と答える側に倒す。"""
    return bool(SANTEN.search(label or "") or SANTEN.search(href or "")
                or SANTEN_HREF.search(href or ""))


def blocked_pdf(url, content_type):
    """BIT から PDF が返ってきたか。返ってきたら中身は捨てる。"""
    return is_bit(url) and "application/pdf" in (content_type or "").lower()


# ---------------------------------------------------------------- 文字コード

def decide_charset(raw, content_type):
    """Content-Type と meta タグから文字コードを決める。

    役所のページは UTF-8 のことが多いが、古いものは Shift_JIS が残っている。
    """
    m = re.search(r"charset=([\w\-]+)", content_type or "", re.I)
    if m:
        return m.group(1)
    head = raw[:4096].decode("ascii", "ignore")
    m = re.search(r'charset=["\']?([\w\-]+)', head, re.I)
    if m:
        return m.group(1)
    return "utf-8"


# 圧縮されたまま返ってきた本文を、**文字として読まない**（2026-09-19）。
#
# `urllib` は `Accept-Encoding` を自分からは付けないし、付いていても
# **中身をほどかない**。相手が勝手に圧縮して返すと `r.read()` は圧縮のバイトになる。
# それを `to_text()` に通すと、どの文字コードでも読めないので
# 最後の `decode("utf-8", "replace")` に落ちて**全部が置換文字になる。**
#
# バイトを残してあれば後から戻せる。**先に文字にしてしまうと戻せない。**
# 姉妹サイトが実物で踏んだ（wayback から取るところだけ文字にしていて、
# gzip の回の5枚が戻らない形で壊れた）。
_ATSUSHUKU = (
    (b"\x1f\x8b", "gzip"),
    (b"BZh", "bzip2"),
    (b"PK\x03\x04", "zip"),
    (b"\xfd7zXZ", "xz"),
    (b"(\xb5/\xfd", "zstd"),
    (b"\x04\x22\x4d\x18", "lz4"),
)


def atsushuku(raw, header=""):
    """圧縮されたまま返ってきたなら名前を返す。そうでなければ空文字。

    **見出しと中身の両方を見る。** 見出しだけだと、付け忘れて返す
    サーバーを見逃す。中身だけだと、知らない圧縮の形を見逃す。
    """
    h = (header or "").strip().lower()
    if h and h != "identity":
        return h
    for magic, name in _ATSUSHUKU:
        if (raw or b"").startswith(magic):
            return name
    return ""


def to_text(raw, content_type):
    cs = decide_charset(raw, content_type)
    for enc in (cs, "utf-8", "cp932", "euc_jp"):
        try:
            return raw.decode(enc), enc
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", "replace"), "utf-8(replace)"


# ---------------------------------------------------------------- HTML を読む

class Scanner(HTMLParser):
    """表とリンクだけを拾う。中身の意味までは見ない。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []          # 表ごとの {rows, cols, header}
        self.links = []           # (href, 文字列)
        self.text = []            # 画面に出る文字（裁判所名などを探す用）
        self._tstack = []
        self._row_cells = 0
        self._cell_buf = None
        self._href = None
        self._atext = []
        self._skip = 0            # script / style の中は読まない

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag in ("script", "style"):
            self._skip += 1
        elif tag == "table":
            self._tstack.append({"rows": 0, "cols": 0, "header": []})
        elif tag == "tr" and self._tstack:
            self._row_cells = 0
        elif tag in ("td", "th") and self._tstack:
            self._row_cells += 1
            self._cell_buf = []
        elif tag == "a":
            self._href = d.get("href")
            self._atext = []

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = max(0, self._skip - 1)
        elif tag == "table" and self._tstack:
            self.tables.append(self._tstack.pop())
        elif tag == "tr" and self._tstack:
            t = self._tstack[-1]
            t["rows"] += 1
            t["cols"] = max(t["cols"], self._row_cells)
        elif tag in ("td", "th") and self._tstack and self._cell_buf is not None:
            t = self._tstack[-1]
            text = "".join(self._cell_buf).strip()
            if t["rows"] == 0 and len(t["header"]) < 12:
                t["header"].append(text[:24])
            self._cell_buf = None
        elif tag == "a" and self._href is not None:
            self.links.append((self._href, "".join(self._atext).strip()[:60]))
            self._href = None

    def handle_data(self, data):
        if self._skip:
            return
        if self._cell_buf is not None:
            self._cell_buf.append(data)
        if self._href is not None:
            self._atext.append(data)
        self.text.append(data)


# ---------------------------------------------------------------- 取りに行く

# 目次ページから「その先」を選ぶ言葉。売却だけを追う（DESIGN 1.11）。
FOLLOW_TEXT = re.compile(r"売却|売払|売り払|売払い|公売|入札|処分|譲渡|先着")
FOLLOW_TOPIC = re.compile(
    r"土地|物件|不動産|市有|県有|府有|国有|公有|財産|地|結果|一覧|予定|"
    r"年度|令和|第\s*\d+\s*回")
# 借りる話・様式・問い合わせには逃げない。KSI へも出ていかない（DESIGN 1.10）
FOLLOW_SKIP = re.compile(
    r"貸付|賃貸|定期借地|サウンディング|意見|様式|手引|要綱|申請書|案内図|"
    r"お問い合わせ|よくある|電子申請|ダウンロード|\.doc|\.xls|\.zip|"
    r"官公庁オークション|KSI")
FOLLOW_MAX = 10          # 1つの目次から辿る数の上限。相手に迷惑をかけないため
FOLLOW_MAX_2 = 4         # 2階層目はさらに絞る
FOLLOW_BUDGET = 20       # 1つの収集先で辿る総数の上限


def follow_links(page, base_url):
    """目次ページから、年度別ページなど「その先」のリンクを選ぶ。

    BIT からは1本も辿らない。3点セットへ近づかないための一番外側の壁。
    """
    if is_bit(base_url):
        return []

    out, seen = [], set()
    for m in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
                         page, re.S | re.I):
        label = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(2))).strip()
        if not label or len(label) > 60:
            continue
        href = html.unescape(m.group(1))
        if is_santen_link(href, label):
            SANTEN_SKIPPED[0] += 1
            continue
        if FOLLOW_SKIP.search(label):
            continue
        if not (FOLLOW_TEXT.search(label) and FOLLOW_TOPIC.search(label)):
            continue
        url = urllib.parse.urljoin(base_url, href)
        if not url.startswith("http") or url in seen or url == base_url:
            continue
        # 同じサイトの中だけ辿る。よそへ出ていかない
        if urllib.parse.urlparse(url).netloc != urllib.parse.urlparse(base_url).netloc:
            continue
        # 念のため。BIT へ渡る道は塞ぐ
        if is_bit(url):
            continue
        seen.add(url)
        out.append((url, label))
    return out


def slug_of(url):
    """辿った先を保存するときのファイル名の一部。

    **クエリも入れる。** 自治体の一覧は `?page=2` `?id=123` のように
    クエリだけが違うページが並ぶ。パスだけで名前を作ると、
    取った何本もが同じ名前になって、最後の1本以外は黙って消える。
    長いクエリはそのままだと名前にならないので、短い指紋にして足す。
    """
    p = urllib.parse.urlparse(url)
    name = re.sub(r"[^A-Za-z0-9._-]", "_", p.path.strip("/").replace("/", "-"))
    name = (name or "page")[-60:]
    if p.query:
        tag = hashlib.sha1(p.query.encode("utf-8")).hexdigest()[:8]
        q = re.sub(r"[^A-Za-z0-9._-]", "_", p.query)[:24]
        name = "%s-%s-%s" % (name, q, tag)
    return name


class BackOff(Exception):
    """相手が「いまは待って」と言っている。その回は中止する。"""


ROBOTS_KYOHI = "robots.txt で拒否されている"
ROBOTS_FUMEI = "robots.txt が読めなかった（分からないときは取らない）"


def check_robots(url):
    """robots.txt で禁じられていないか確かめる。**分からないときは取らない。**

    robots.txt の取得・解釈・キャッシュ・404/410 の判定・redirect の扱いは、
    ぜんぶ `common/kado.py` の `Kado.robots_kekka()` へ寄せた（門は1か所）。
    ここは、その答え `(True/False/None, 理由)` を、
    既存の呼び出し側（recon_one・辿る先）に合わせて `(ok, why, 本文)` の
    形へ直すだけ。**セッションの中（`with K.sesshon(...):`）でだけ呼べる**
    （門の外で呼ぶと `robots_kekka` が「カードの門を通っていない」を返す＝
    読めなかった扱いになる）。

    **None（確かめられなかった・混んでいる）を許可に変えない**
    （2026-09-24 からの決まり。正本の共通指示書「門のつなぎ込み」）。

    本文はもう返らない（`common/kado.py` は robots.txt の生バイトを控えに
    残さない。読む側もこれまで誰も本文を使っていなかった）。形だけ
    合わせて空文字を返す。
    """
    ok, why = kado.genzai().robots_kekka(url)
    if ok is None:
        return False, why or ROBOTS_FUMEI, ""
    return ok, why or ("許可" if ok else ROBOTS_KYOHI), ""


def fetch(url):
    """1本取ってくる。名乗りは偽らない（DESIGN 10章・正本 3.4）。"""
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "ja",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            # **Content-Encoding も持って帰る。** urllib は中身をほどかない。
            # 圧縮されたまま返ってきたことに、呼ぶ側が気づけるようにする
            return (r.status, r.headers.get("Content-Type", ""), r.read(),
                    r.headers.get("Content-Encoding", ""))
    except urllib.error.HTTPError as e:
        if e.code in BACK_OFF:
            # リトライで突破しない。今日はここまでにして、明日また来る
            raise BackOff("HTTP %s（混んでいる。今日は打ち切る）" % e.code)
        raise


# ---------------------------------------------------------------- 判定する

KEYWORDS = ["売却", "売払", "公売", "入札", "開札", "先着順", "最低売却価格",
            "見積価額", "売却基準価額", "落札", "予定価格", "申込"]

# 裁判所名を拾う。court_id の推定が合っているかの答え合わせに使う（DESIGN 13章）
COURT = re.compile(r"(大阪|神戸|京都|奈良|大津|和歌山)地方裁判所\s*([^\s<（(]{0,6}支部)?")


def analyze(text, base_url, src):
    s = Scanner()
    try:
        s.feed(text)
    except Exception as e:
        return {"error": "HTMLの解析に失敗: %s" % e}

    # 中身のある表だけを見る（2行2列以上）
    real = [t for t in s.tables if t["rows"] >= 2 and t["cols"] >= 2]
    real.sort(key=lambda t: t["rows"] * t["cols"], reverse=True)

    pdfs, excels, santen, outside = [], [], [], []
    base_host = urllib.parse.urlparse(base_url).netloc
    for href, label in s.links:
        low = href.lower()
        full = urllib.parse.urljoin(base_url, href)
        if is_santen_link(href, label):
            santen.append((full, label))
            continue
        if low.endswith(".pdf"):
            pdfs.append((full, label))
        elif low.endswith((".xlsx", ".xls", ".csv")):
            excels.append((full, label))
        elif full.startswith("http") and \
                urllib.parse.urlparse(full).netloc != base_host:
            outside.append((full, label))

    body = "".join(s.text)
    found = [k for k in KEYWORDS if k in body]
    years = sorted(set(re.findall(r"(?:令和|平成)\s*\d{1,2}\s*年", body)))[:8]

    courts = []
    for m in COURT.finditer(body):
        name = m.group(1) + "地方裁判所" + (m.group(2) or "")
        if name not in courts:
            courts.append(name)

    # 行数だけで切ると、中身のある小さい表を見落とす。
    # 見出しに売却らしい項目が並んでいるかも見る。
    header_is_real = bool(real) and any(
        re.search(r"物件|所在|面積|価格|価額|入札|開札|期間|売却|番号", h)
        for h in real[0]["header"])

    if src.get("kind") == "seed":
        verdict = "リンク集"
    elif real and (real[0]["rows"] >= 3 or
                   (real[0]["rows"] >= 2 and header_is_real)):
        verdict = "表"
    elif excels:
        verdict = "Excel"
    elif len(pdfs) >= 3:
        verdict = "PDF"
    else:
        verdict = "わからない"

    return {
        "verdict": verdict,
        "tables": len(real),
        "biggest": real[0] if real else None,
        "pdf_count": len(pdfs),
        "pdf_sample": pdfs[:6],
        "excel_count": len(excels),
        "excel_sample": excels[:5],
        "santen_count": len(santen),
        "santen_sample": [lb or "(名前なし)" for _, lb in santen[:5]],
        "outside_count": len(outside),
        "outside_sample": outside[:20],
        "keywords": found,
        "years": years,
        "courts": courts[:4],
        "links_total": len(s.links),
    }


# ---------------------------------------------------------------- レポート

def report_one(src, res):
    out = []
    out.append("### %s" % src["name"])
    out.append("")
    out.append("- id: `%s` / kind: `%s`" % (src["id"], src.get("kind", "-")))
    out.append("- URL: %s" % (src.get("url") or "（未確認）"))
    if src.get("note"):
        out.append("- メモ: %s" % src["note"])

    if res.get("skipped"):
        out.append("- **結果: 取りに行かなかった（%s）**" % res["skipped"])
        out.append("")
        return "\n".join(out)

    if res.get("fetch_error"):
        out.append("- **結果: 取得できなかった — %s**" % res["fetch_error"])
        out.append("")
        return "\n".join(out)

    out.append("- robots.txt: %s" % res["robots"])
    out.append("- HTTP %s / %s / %s バイト"
               % (res["status"], res["encoding"], format(res["bytes"], ",")))

    a = res["analysis"]
    if a.get("error"):
        out.append("- **%s**" % a["error"])
        out.append("")
        return "\n".join(out)

    out.append("- **判定: %s**" % a["verdict"])
    out.append("- 表 %d 個 / PDFリンク %d 本 / Excel %d 本 / リンク合計 %d 本"
               % (a["tables"], a["pdf_count"], a["excel_count"], a["links_total"]))

    if a["biggest"]:
        b = a["biggest"]
        out.append("- いちばん大きい表: %d 行 × %d 列" % (b["rows"], b["cols"]))
        if b["header"]:
            out.append("  - 見出しらしき行: %s"
                       % " | ".join(x for x in b["header"] if x))

    if a["courts"]:
        out.append("- ページに出てきた裁判所名: %s" % " / ".join(a["courts"]))
        if src.get("court_id"):
            out.append("  - この収集先の court_id は `%s`。上の名前と食い違っていたら直す"
                       % src["court_id"])

    if a["santen_count"]:
        out.append("- **3点セットらしきリンク %d 本を見つけたが、1本も辿っていない**"
                   % a["santen_count"])
        out.append("  - 例: %s" % " / ".join(a["santen_sample"]))

    for label, items in (("PDF", a["pdf_sample"]), ("Excel", a["excel_sample"])):
        for url, text in items:
            out.append("  - %s: %s → %s" % (label, text or "(名前なし)", url))

    if src.get("kind") == "seed" and a["outside_sample"]:
        out.append("- **よそのサイトへのリンク %d 本（sources.json に足す種）**"
                   % a["outside_count"])
        for url, text in a["outside_sample"]:
            out.append("  - %s → %s" % (text or "(名前なし)", url))

    if a["keywords"]:
        out.append("- 出てきた言葉: %s" % " / ".join(a["keywords"]))
    if a["years"]:
        out.append("- 年度らしき表記: %s" % " / ".join(a["years"]))

    if res.get("followed"):
        cap = res.get("follow_capped")
        note = "（%d本見つかったが上限%d本まで）" % cap if cap else ""
        out.append("- **この先を辿った: %d本** %s" % (len(res["followed"]), note))
        for label, a2, depth, err in res["followed"]:
            mark = "  " * depth
            if err:
                out.append("  -%s%s … 取れなかった（%s）" % (mark, label[:34], err))
            else:
                extra = (" %d行×%d列" % (a2["biggest"]["rows"], a2["biggest"]["cols"])
                         if a2.get("biggest") else "")
                pdf = " PDF%d本" % a2["pdf_count"] if a2.get("pdf_count") else ""
                out.append("  -%s%s … **%s**%s%s"
                           % (mark, label[:34], a2["verdict"], extra, pdf))
        if res.get("budget_hit"):
            b, left = res["budget_hit"]
            out.append("  - （上限%d本に達した。まだ%d本残っている）" % (b, left))
    out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------- 本体

def wanted(src, only):
    """引数での絞り込み。id / system / area のどれでも効く。"""
    if not only:
        return True
    return only in (src["id"], src.get("system"), src.get("area"))


# 今日はもう行かないと決めたホスト。429/503 を受けたら入れる。
# 正本 3.4「429 / 503 / 待機列が返ったら、押し込まずにその回は中止して次回に回す」。
# 「その回」を**そのホストへの取得全部**と読む。相手が「いまは待って」と
# 言っているのは、その1本についてではなく、そのサーバーについてだから。
_BUSY_HOSTS = set()


def host_of(url):
    return urllib.parse.urlparse(url or "").netloc


def recon_one(src, today, raw_dir, counts, blocked):
    """1つの収集先を見る。戻り値はレポートに渡す dict。"""
    res = {}

    if src.get("handoff"):
        res["skipped"] = "%s送り（制度が別なので、ここでは扱わない）" % src["handoff"]
        res["handoff"] = src["handoff"]
        return res
    hozon_saki = os.path.join(raw_dir, src["id"])
    K = kado.genzai()
    # **通信の前に、カードの門を見る**（common/kado.py 1か所に集めた判定）。
    # 前はここで torikata.naze_toranai(src) を見ていた（sources.json の4語欄）。
    # いまはカード＋運営者承認から導いた正式状態が効く（common/torikata.py の
    # docstring・common/kado.py の Kado.seishiki）。止める理由があれば、
    # この収集先のためには1本も通信しない（robots.txt も）
    門で止めた = K.card_mon(src["id"], hozon_saki=hozon_saki)
    if 門で止めた:
        res["skipped"] = "門で止めた：" + "／".join(門で止めた)
        return res
    if src.get("fetch_every") == "月2回" and jst_today().day not in (1, 15):
        # 中身がめったに変わらないものを毎日叩かない（正本 3.4）
        res["skipped"] = "月2回の収集先（1日と15日だけ見に行く）"
        return res
    if src.get("manual"):
        res["skipped"] = "人が inbox に保存する収集先（Actions では取りに行かない）"
        return res
    if not src.get("url"):
        res["skipped"] = "URL未確認"
        return res

    host = host_of(src.get("url"))
    if host and host in _BUSY_HOSTS:
        why = "同じサーバーが先に「いまは待って」と返したので、今日はここまで"
        res["skipped"] = why
        res["back_off"] = True
        counts["打ち切り"] = counts.get("打ち切り", 0) + 1
        return res

    # **通過したら、この収集先の通信を全部セッションの中で行う**
    # （robots の確認・本体・辿る先・PDF まで）。`kado.Tomeru` で止まったら
    # 「門で止めた」として扱い、次の取得先へ進む（通信は1本も出ていない）
    try:
        with K.sesshon(src["id"], hozon_saki=hozon_saki):
            try:
                ok, why, _ = check_robots(src["url"])
            except BackOff as e:
                # robots.txt すら読めないほど混んでいる。押し込まない（正本 3.4）
                res["robots"] = str(e)
                res["skipped"] = str(e)
                res["back_off"] = True
                if host:
                    _BUSY_HOSTS.add(host)
                counts["打ち切り"] = counts.get("打ち切り", 0) + 1
                return res
            res["robots"] = why
            if not ok:
                res["skipped"] = why
                # **「拒否された」と「読めなかった」を混ぜない。** どちらも取らないが、減らす手が違う
                k = "拒否" if why == ROBOTS_KYOHI else "robots不明"
                counts[k] = counts.get(k, 0) + 1
                return res

            try:
                status, ctype, raw, cenc = fetch(src["url"])
            except kado.Tomeru:
                # **門で止めた。** urlopen() の中で url_mon() が止めたもの
                # （URL範囲の外・robots が途中で変わった等）。下の
                # `except Exception` に飲まれると「取得できなかった」に
                # 化けるので、ここで先に受けて外側（with の外）へ渡す
                raise
            except BackOff as e:
                res["fetch_error"] = str(e)
                res["back_off"] = True
                # そのサーバーへは今日もう行かない。押し込まない（正本 3.4）
                if host:
                    _BUSY_HOSTS.add(host)
                counts["打ち切り"] = counts.get("打ち切り", 0) + 1
                time.sleep(WAIT)
                return res
            except urllib.error.HTTPError as e:
                res["fetch_error"] = "HTTP %s" % e.code
                counts["失敗"] = counts.get("失敗", 0) + 1
                time.sleep(WAIT)
                return res
            except Exception as e:
                res["fetch_error"] = "%s: %s" % (type(e).__name__, e)
                counts["失敗"] = counts.get("失敗", 0) + 1
                time.sleep(WAIT)
                return res

            # BIT から PDF が返ってきたら中身を捨てる。保存もしない
            if blocked_pdf(src["url"], ctype):
                blocked["bit_pdf"] += 1
                res["fetch_error"] = "BITからPDFが返ってきたので捨てた（3点セットは取らない）"
                time.sleep(WAIT)
                return res

            # **読む前にしまう**（正本 3.5「取り直せないものが先」・2026-09-19）。
            # 前は `analyze()` のあとに書いていた。その朝のページは取り直せないのに、
            # **読み取りで例外が出たら1枚も残らない**形だった。
            # 生のまま残す。これがアーカイブの最初の1枚になる（再公開はしない）
            d = os.path.join(raw_dir, src["id"])
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, "%s.html" % today), "wb") as f:
                f.write(raw)

            # **圧縮されたまま返ってきたら、文字にしない。**
            # バイトは上で残してあるので、あとから戻せる。
            # ここで `to_text()` に通すと全部が置換文字になり、
            # 「読めた」顔で「わからない」が積み上がる
            圧縮 = atsushuku(raw, cenc)
            if 圧縮:
                res.update(status=status, bytes=len(raw))
                res["fetch_error"] = (
                    "圧縮されたまま返ってきた（%s）。"
                    "バイトは残したが、中身は読んでいない" % 圧縮)
                counts["失敗"] = counts.get("失敗", 0) + 1
                time.sleep(WAIT)
                return res

            text, enc = to_text(raw, ctype)
            res.update(status=status, encoding=enc, bytes=len(raw))
            res["analysis"] = analyze(text, src["url"], src)
            counts[res["analysis"]["verdict"]] = \
                counts.get(res["analysis"]["verdict"], 0) + 1
            blocked["santen_links"] += res["analysis"]["santen_count"]

            # 入口が目次だけのことが多い。表が無いページはその先を見に行く。
            # BIT では follow_links が必ず空を返すので、ここは動かない。
            if res["analysis"]["verdict"] == "わからない":
                res["followed"] = []
                known = {src["url"]}
                queue = []

                def enqueue(links, depth, limit):
                    """まだ見ていないものだけを、上限まで列に並べる。"""
                    fresh = [(u, lb) for u, lb in links if u not in known]
                    for u, lb in fresh[:limit]:
                        known.add(u)
                        queue.append((u, lb, depth))
                    return len(fresh)

                n_found = enqueue(follow_links(text, src["url"]), 1, FOLLOW_MAX)
                if n_found > FOLLOW_MAX:
                    res["follow_capped"] = (n_found, FOLLOW_MAX)

                while queue and len(res["followed"]) < FOLLOW_BUDGET:
                    url2, label, depth = queue.pop(0)
                    # **辿った先にも robots.txt を当てる。**
                    # 目次のページが許可でも、その先が Disallow のことがある。
                    # ここを飛ばすと、断られている場所を実際に取りに行くことになる
                    try:
                        ok2, why2, _ = check_robots(url2)
                    except BackOff as e:
                        res["followed"].append((label, None, depth, str(e)))
                        res["back_off"] = True
                        h2 = host_of(url2)
                        if h2:
                            _BUSY_HOSTS.add(h2)
                        break
                    if not ok2:
                        res["followed"].append((label, None, depth, why2))
                        continue
                    time.sleep(WAIT)
                    try:
                        st2, ct2, raw2, ce2 = fetch(url2)
                    except kado.Tomeru:
                        # **門で止めた。** `except Exception` に飲ませない
                        # （下の except で「取れなかった」に化けると、
                        # 門で止めたことが report_one() から見えなくなる）
                        raise
                    except BackOff as e:
                        res["followed"].append((label, None, depth, str(e)))
                        res["back_off"] = True
                        h2 = host_of(url2)
                        if h2:
                            _BUSY_HOSTS.add(h2)
                        break          # この収集先はここで打ち切る
                    except Exception as e:
                        res["followed"].append((label, None, depth, type(e).__name__))
                        continue
                    if blocked_pdf(url2, ct2):
                        blocked["bit_pdf"] += 1
                        res["followed"].append((label, None, depth, "BITのPDFを捨てた"))
                        continue
                    # 入口と同じ。**読む前にしまう。圧縮なら文字にしない**
                    with open(os.path.join(d, "%s--%s.html" % (today, slug_of(url2))),
                              "wb") as f:
                        f.write(raw2)
                    圧縮2 = atsushuku(raw2, ce2)
                    if 圧縮2:
                        res["followed"].append(
                            (label, None, depth,
                             "圧縮されたまま返ってきた（%s）。読んでいない" % 圧縮2))
                        continue
                    t2, _ = to_text(raw2, ct2)
                    a2 = analyze(t2, url2, src)
                    res["followed"].append((label, a2, depth, None))
                    counts[a2["verdict"]] = counts.get(a2["verdict"], 0) + 1
                    blocked["santen_links"] += a2["santen_count"]

                    if a2["verdict"] == "わからない" and depth < 2:
                        enqueue(follow_links(t2, url2), depth + 1, FOLLOW_MAX_2)

                if len(res["followed"]) >= FOLLOW_BUDGET and queue:
                    res["budget_hit"] = (FOLLOW_BUDGET, len(queue))

            time.sleep(WAIT)
            return res
    except kado.Tomeru as e:
        res["skipped"] = "門で止めた：" + "／".join(e.riyuu)
        return res


# ---------------------------------------------------------------- 公開ログ
#
# **偵察レポートの本文は、ログにも Actions の要約にも出さない**（2026-09-24）。
# 公開用 repo の Actions のログと要約は、誰でも読める。レポートは
# 「このファイルは公開しない」と名乗っているのに、前は同じ本文を print し、
# 要約（GITHUB_STEP_SUMMARY）にも書いていた。取得元のURL・保存した名前・
# 伏せる前の内訳が、公開の画面にそのまま出ていた。
#
# **後から伏せ字にしない。そもそも流さない。** 書く先を2つに分ける。
#
#     write_report()  詳しいレポート → data/recon-report.md（金庫にしまう。公開しない）
#     announce()      決まった形の数行 → 標準出力と要約（公開される）
#
# ログに出すのは、固定の文と、こちらの動きの件数だけ。取得元の名前もURLも出さない。
# 止まったときも同じ。詳しいこと（traceback）はレポートに書き、ログには型の名前だけ。

def report_path():
    return os.path.join(HERE, "data", "recon-report.md")


def write_report(text):
    """詳しいレポートを書く。**ここだけが本文の行き先。**"""
    os.makedirs(os.path.dirname(report_path()), exist_ok=True)
    with open(report_path(), "w", encoding="utf-8") as f:
        f.write(text)


def announce(lines, summary=False):
    """公開ログに出す。**決まった形の行だけを渡す。** 本文は渡さない。"""
    for line in lines:
        print(line, flush=True)
    gh = os.environ.get("GITHUB_STEP_SUMMARY") if summary else None
    if gh:
        with open(gh, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


def log_start(n):
    return ["偵察を始める（取得元 %d 件）" % n]


def log_end(seen, tried, failed):
    return [
        "偵察を終えた。詳しいレポートは data/recon-report.md に書いた"
        "（公開しない。本文はログに出さない）",
        "取得元 %d 件：取りに行った %d / 行かなかった %d / 取れなかった %d"
        % (seen, tried, seen - tried, failed),
    ]


def log_crash(exc):
    return ["偵察が途中で止まった（%s）。詳しいことは data/recon-report.md に書いた"
            "（公開しない）" % type(exc).__name__]


def write_crash(detail):
    """止まったところを、公開しないレポートの章として残す。

    今日のレポートがまだ書けていなければ、**「公開しない」の頭から作り直す。**
    頭が無い記録は、翌朝の最初の検査（tests/test_public.py）で落ちる。
    """
    title = "競売統計 偵察レポート（%s）" % today_str()
    try:
        with open(report_path(), encoding="utf-8") as f:
            head = f.read(len(title) + 10)
    except OSError:
        head = ""
    if not head.startswith("# " + title):
        write_report(report.not_public(title))
    report.put_chapter(report_path(), "偵察が途中で止まった",
                       "```\n%s\n```" % detail.rstrip("\n"))


def main():
    # **実行の最初に1回だけ、門を開ける。** これを呼ぶまで、この行から先の
    # urllib.request.urlopen() は（common/kado.py を import した時点で）1本も出ない
    # 日付は common/jst.py（時計を見る1か所）から渡す。robots.txt の控えは金庫の中の
    # data/raw/_robots/ にバイトのまま残す（その日に何と書いてあったかは取り直せない）
    kado.hajimeru(HERE, "keibai-toukei", UA, today=today_str(),
                  robots_hikae=os.path.join(HERE, "data", "raw", "_robots"))

    with open(os.path.join(HERE, "sources.json"), encoding="utf-8") as f:
        sources = json.load(f)["sources"]

    only = sys.argv[1] if len(sys.argv) > 1 else None
    today = today_str()
    raw_dir = os.path.join(HERE, "data", "raw")
    announce(log_start(sum(1 for s in sources if wanted(s, only))))

    head = [
        report.not_public("競売統計 偵察レポート（%s）" % today),
        "「そのページが機械で読める形か」だけを見ている。",
        "判定が **表** か **Excel** なら自動化しやすい。**PDF** なら一手間、",
        "**わからない** なら自分の目で見に行く必要がある。",
        "",
        "BIT（競売）からはリンクを1本も辿らない。3点セットに近づかないため。",
        "何が置いてあるかは数えて報告するだけにしてある。",
        "",
        "扱うのは**競売と公売の2段**。国有財産・公有財産の売払いは、",
        "国や自治体が自分の財産を売るもので、滞納処分による公売とは別の制度。",
        "混ざらないよう**姉妹サイト側に置く**。見つけた収集先は消さずに",
        "「姉妹サイト送り」と印を付けて残してある。",
        "",
    ]

    counts = {}
    blocked = {"bit_pdf": 0, "santen_links": 0}
    bodies = {}

    seen = tried = failed = 0     # 公開ログに出すのは、この3つの数だけ
    for src in sources:
        if not wanted(src, only):
            continue
        res = recon_one(src, today, raw_dir, counts, blocked)
        seen += 1
        if "skipped" not in res:
            tried += 1
            if res.get("fetch_error"):
                failed += 1
        bodies.setdefault(src.get("system", "その他"), []).append(
            report_one(src, res))

    lines = list(head)
    summary = " / ".join("%s %d件" % (k, v) for k, v in sorted(counts.items())) \
        or "対象なし"
    lines.append("**まとめ: %s**" % summary)
    lines.append("")

    # **取得元と題材を分けて出す**（正本 9節「『その取得元が使えない』と『その題材が成立しない』を分ける」）。
    # ある取得元が止まっても、題材が止まるとはかぎらない。
    # 逆に、題材ぜんぶが止まっていることは、ここでしか見えない。
    # **4つの題材を全部出す。通れないものも出す**（欠けているキーは0ではない）
    lines.append("### 題材ごとに、通れる取得元があるか")
    lines.append("")
    lines.append("| 題材 | 取得元 | 通る | 通れるか |")
    lines.append("| --- | ---: | ---: | --- |")
    for name, d in torikata.daizai(sources).items():
        lines.append("| %s | %d | %d | %s |"
                     % (name, d["取得元"], d["通る"],
                        "通れる" if d["通れる"] else "**1つも通らない**"))
    lines.append("")

    # 取得元の4語の内訳。**取りに行っているのに「取ってよい」ではない数を出す。**
    # 0 でも出す（黙って通さない）
    go = {g: sum(1 for x in sources if torikata.go(x) == g) for g in torikata.GO}
    lines.append("**取得元の欄: %s**"
                 % " / ".join("%s %d" % (g, go[g]) for g in torikata.GO))
    kiwa = torikata.kiwadoi(sources)
    lines.append("")
    lines.append("**取りに行っているが「取ってよい」ではない取得元: %d 件。**"
                 % len(kiwa))
    if kiwa:
        lines.append("robots は見ているが、規約を読み終えていない。"
                     "**読み終えるまでは個票を出さない**（正本 3.1）。")
        lines.append("")
        for x in kiwa:
            lines.append("- `%s` … %s（%s）"
                         % (x["id"], torikata.go(x),
                            torikata.riyuu(x) or "理由が書いていない"))
    lines.append("")
    # **「辿った数: 0 本」と直接書いていた。**
    # 数えていない 0 は、数えた 0 と見分けられない。実測（2026-09-20）:
    # 辿るように変えても 0 のままだった。
    # いまは「辿る先を選ぶところで外した数」を数えて出す。
    # 辿った数そのものは `tests/test_recon.py` が見る
    # （辿る先の一覧に3点セットが1本も無いこと）
    lines.append("**3点セットらしきリンクを見つけた数: %d 本"
                 "（辿る先を選ぶときに外した %d 本）／"
                 "BITから返ってきたPDFを捨てた数: %d 本**"
                 % (blocked["santen_links"], SANTEN_SKIPPED[0],
                    blocked["bit_pdf"]))
    lines.append("")

    for system in ("keibai", "kobai", "kokuyu", "koyu", "その他"):
        if system not in bodies:
            continue
        lines.append("## %s" % SYSTEM_NAME.get(system, system))
        lines.append("")
        lines.extend(bodies[system])

    write_report("\n".join(lines))
    # **本文は print しない。要約にも書かない**（上の「公開ログ」）
    announce(log_end(seen, tried, failed), summary=True)


def run():
    """入口。終了コードを返す（ふつうは 0、止まったら 1）。

    **止まっても、詳しいことは公開ログに出さない。** 何もしないと、
    Python が traceback（例外の文・途中の値）を標準エラーにそのまま出す。
    """
    try:
        main()
    except Exception as e:
        try:
            with warnings.catch_warnings():
                # common/report.py の put_chapter は、読んだファイルを閉じていない。
                # 警告を出す設定で走らせると、ResourceWarning がファイルの場所ごと
                # 標準エラーに出る（tests/test_recon_log.py で踏んだ）。
                # 止まったときにログへ出すのは、決まった1行だけにする
                warnings.simplefilter("ignore", ResourceWarning)
                write_crash(traceback.format_exc())
        except Exception:
            # レポートにも書けなかった。**それでも詳しいことはログに出さない**
            pass
        for line in log_crash(e):
            sys.stderr.write(line + "\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run())
