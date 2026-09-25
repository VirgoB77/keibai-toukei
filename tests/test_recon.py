#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""偵察の「やってはいけないこと」を固定する。

DESIGN 1章の決定事項のうち、コードで守れるものをここで縛る。
いちばん大事なのは **BITから3点セットを取らない** こと。
うっかり便利にしようとして壁を崩したら、ここが落ちる。

    python3 -m unittest discover -s tests
"""

import io
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import recon  # noqa: E402
import nise_kado  # noqa: E402  検査の中だけの偽の門（tests/kinko.py と同じ、手伝いのモジュール）
from common import kado  # noqa: E402
from common import torikata  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


class BITに近づかない(unittest.TestCase):
    """3点セットへ向かう道を全部塞いであるか。"""

    def test_3点セットのリンクを見分ける(self):
        for href, label in [
            ("/app/detail/pt003/h01", "3点セット"),
            ("/app/detail/pt003/h01", "３点セット"),
            ("/app/detail/pt003/h01", "ダウンロード"),
            ("/app/detail/pt003/h01", "物件明細書"),
            ("/app/detail/pt003/h01", "現況調査報告書"),
            ("/app/detail/pt003/h01", "評価書"),
            ("/download/santen.pdf", "詳細"),
        ]:
            with self.subTest(label=label):
                self.assertTrue(recon.is_santen_link(href, label))

    def test_ふつうのリンクは弾かない(self):
        self.assertFalse(recon.is_santen_link("/kanzai/list.html", "売却物件一覧"))
        self.assertFalse(recon.is_santen_link("/result.html", "入札結果"))

    def test_BITからはリンクを1本も辿らない(self):
        page = """
        <a href="/app/schedule/pr005/h01?courtId=33311">売却スケジュール</a>
        <a href="/app/search/pt001/h01">物件検索 令和7年度の売却結果一覧</a>
        <a href="/app/detail/pt003/h01">3点セット</a>
        """
        got = recon.follow_links(page, "https://www.bit.courts.go.jp/app/top/pt001/h01")
        self.assertEqual(got, [])

    def test_BITのPDFは捨てる(self):
        self.assertTrue(recon.blocked_pdf(
            "https://www.bit.courts.go.jp/app/detail/pt003/h01",
            "application/pdf"))
        self.assertTrue(recon.blocked_pdf(
            "https://www.bit.courts.go.jp/x.html",
            "application/pdf; charset=binary"))
        # よその役所のPDFは、ここでは捨てない（2MBの上限は fetch.py 側の仕事）
        self.assertFalse(recon.blocked_pdf(
            "https://lfb.mof.go.jp/kinki/chosho.pdf", "application/pdf"))
        self.assertFalse(recon.blocked_pdf(
            "https://www.bit.courts.go.jp/app/top/pt001/h01", "text/html"))

    def test_BITは判定しても辿らない(self):
        html = """<html><body>
        <a href="/app/detail/pt003/h01">3点セット</a>
        <a href="/app/detail/pt003/h02">ダウンロード</a>
        <table><tr><th>物件番号</th><th>売却基準価額</th></tr>
        <tr><td>1</td><td>12,000,000円</td></tr></table>
        </body></html>"""
        a = recon.analyze(html, "https://www.bit.courts.go.jp/app/list", {"kind": "bit-list"})
        self.assertEqual(a["santen_count"], 2)
        # 3点セットはPDFの数にもExcelの数にも混ぜない。数えるだけ
        self.assertEqual(a["pdf_count"], 0)


class 目次を辿るときの行儀(unittest.TestCase):

    BASE = "https://web.pref.hyogo.lg.jp/kk30/pa10_000000015.html"

    def test_売却だけを追い_貸付には行かない(self):
        page = """
        <a href="a.html">県有地の売却物件一覧</a>
        <a href="b.html">県有地の貸付物件一覧</a>
        <a href="c.html">サウンディング型市場調査の売却意見募集</a>
        <a href="d.html">様式のダウンロード</a>
        <a href="https://www.kankocho.jp/e">官公庁オークションで入札する土地</a>
        """
        got = [lb for _, lb in recon.follow_links(page, self.BASE)]
        self.assertIn("県有地の売却物件一覧", got)
        for ng in ("県有地の貸付物件一覧", "サウンディング型市場調査の売却意見募集",
                   "様式のダウンロード", "官公庁オークションで入札する土地"):
            self.assertNotIn(ng, got)

    def test_よそのサイトへは出ていかない(self):
        page = '<a href="https://kokuyuzaisan.akiya-athome.jp/x">国有財産の売却物件</a>'
        self.assertEqual(recon.follow_links(page, self.BASE), [])


class sources_jsonの決まり(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "sources.json"), encoding="utf-8") as f:
            cls.sources = json.load(f)["sources"]

    def test_idが重複していない(self):
        ids = [s["id"] for s in self.sources]
        self.assertEqual(len(ids), len(set(ids)))

    def test_段は4つのどれか(self):
        for s in self.sources:
            self.assertIn(s["system"], ("keibai", "kobai", "kokuyu", "koyu"))

    def test_競売はPDFを取らない(self):
        for s in self.sources:
            if s["system"] == "keibai":
                self.assertFalse(s.get("pdf", False), s["id"])

    def test_PDFの上限は2MBまで(self):
        for s in self.sources:
            if s.get("pdf"):
                self.assertLessEqual(s.get("pdf_max_mb", 2), 2, s["id"])

    def test_動かす収集先にはURLがある(self):
        for s in self.sources:
            if torikata.toru(s):
                self.assertTrue(s.get("url"), s["id"])

    def test_URL未確認のものは止めてある(self):
        for s in self.sources:
            if not s.get("url"):
                self.assertFalse(torikata.toru(s), s["id"])

    def test_読めないものの列を先に当てる出どころがある(self):
        """**実物を取る前に、何が載るかを知っておく**（2026-09-19）。

        BIT の売却結果・過去データ・取下げ等は、画面遷移が POST なので
        GET の URL が無い。**人が保存するしかない。**
        頼む前に列を知っておかないと、
        「保存してもらったが、欲しい欄が無かった」になる。

        `bit-help` のメモにそう書いてあったのに、**索引しか入れていなかった。**
        索引はリンクの一覧で、列名は1つも書いていない。
        """
        url = {s["id"]: s.get("url") or "" for s in self.sources}
        for sid in ("bit-help-result", "bit-help-past", "bit-help-withdrawn"):
            self.assertIn(sid, url, sid)
            self.assertTrue(url[sid].startswith("https://www.bit.courts.go.jp/help/"),
                            "%s の URL が使い方のページではない" % sid)
        # **索引と同じURLにしない。** 索引には列名が1つも無い
        self.assertNotEqual(url["bit-help-result"], url["bit-help"])

    def test_人が保存するものは止めてある(self):
        """**読み取りが無いものを人に頼まない**（parse.INBOX_READABLE）。

        頼むと、人が手を動かしたぶんがそのまま捨てられる。しかも置かれた
        時点で催促が止まるので、**その升は永久に空のまま**になる。
        """
        import parse
        for s in self.sources:
            if s.get("manual"):
                self.assertFalse(
                    torikata.toru(s), "%s が manual なのに動いている" % s["id"])
        self.assertEqual(parse.INBOX_READABLE, ("list",),
                         "読み取りを書いたら、ここと一緒に増やすこと")

    def test_KSIと財務省の売却サイトは入れていない(self):
        for s in self.sources:
            url = s.get("url") or ""
            self.assertNotIn("kankocho.jp", url)
            self.assertNotIn("akiya-athome.jp", url)


class 取得の作法(unittest.TestCase):
    """正本 3.4「断られたら、そこで打ち切る。回り込まない」を固定する。

    **2026-09-25 から**、robots.txt の取得・解釈・キャッシュ・404/410 の
    判定・redirect の扱いは `common/kado.py`（`Kado.robots_kekka`）に
    寄せた。その中身の検査は `tests/test_kado.py` が持つ（あちらは書き換えない
    約束のファイル）。ここで見るのは、`recon.check_robots()` がそこへ
    正しくつないでいるか（**wiring**）だけ。
    """

    def _K(self, robots_kekka):
        """`robots_kekka(url)` だけを差し替えた偽の門を、いまの門として据える。"""
        class 偽の門:
            def __init__(self, f):
                self._f = f
                self.kita = []

            def robots_kekka(self, url):
                self.kita.append(url)
                return self._f(url)

        k = 偽の門(robots_kekka)
        keep = kado.genzai()
        self.addCleanup(setattr, kado, "_KADO", keep)
        kado._KADO = k
        return k

    def test_Noneを許可に変えない(self):
        """**「確かめられなかった」「混んでいる」を許可にしない**（2026-09-24 からの決まり）。"""
        k = self._K(lambda url: (None, "確かめられなかった（検査用）"))
        ok, why, body = recon.check_robots("https://example.invalid/a.html")
        self.assertEqual(k.kita, ["https://example.invalid/a.html"])
        self.assertFalse(ok, "None を許可に変えている")
        self.assertEqual(why, "確かめられなかった（検査用）")
        self.assertEqual(body, "")

    def test_Falseはそのまま通す(self):
        self._K(lambda url: (False, "robots.txt で拒否されている"))
        ok, why, _ = recon.check_robots("https://example.invalid/himitsu/x.html")
        self.assertFalse(ok)
        self.assertEqual(why, recon.ROBOTS_KYOHI)

    def test_Trueはそのまま通す(self):
        self._K(lambda url: (True, "許可（検査用）"))
        ok, why, _ = recon.check_robots("https://example.invalid/ok.html")
        self.assertTrue(ok)
        self.assertEqual(why, "許可（検査用）")

    def test_辿った先にもrobotsを当てる(self):
        # 目次が許可でも、その先が Disallow のことがある
        import inspect
        src = inspect.getsource(recon)
        follow = src[src.index("while queue and len(res"):]
        self.assertIn("check_robots(url2)", follow[:900])

    def test_待ち時間と打ち切りの決まりは正本どおり(self):
        self.assertGreaterEqual(recon.WAIT, 5)
        self.assertEqual(tuple(sorted(recon.BACK_OFF)), (429, 503))


class 保存する名前(unittest.TestCase):

    def test_クエリだけ違うページが上書きで消えない(self):
        a = recon.slug_of("https://example.lg.jp/list?page=1")
        b = recon.slug_of("https://example.lg.jp/list?page=2")
        self.assertNotEqual(a, b)

    def test_同じURLなら同じ名前(self):
        self.assertEqual(recon.slug_of("https://example.lg.jp/list?page=1"),
                         recon.slug_of("https://example.lg.jp/list?page=1"))

    def test_ファイル名に使えない字が入らない(self):
        import re
        name = recon.slug_of("https://example.lg.jp/a b/c?x=1&y=2 3")
        self.assertIsNone(re.search(r"[^A-Za-z0-9._-]", name), name)


class 圧縮されたまま返ってきたとき(unittest.TestCase):
    """**バイトを残す。文字にしない**（2026-09-19）。

    `urllib` は `Accept-Encoding` を自分からは付けないし、付いていても
    **中身をほどかない**。相手が勝手に圧縮して返すと `r.read()` は
    圧縮のバイトになる。それを `to_text()` に通すと、どの文字コードでも
    読めないので最後の `decode("utf-8", "replace")` に落ちて
    **全部が置換文字になる。**

    バイトを残してあれば後から戻せる。**先に文字にすると戻せない。**
    姉妹サイトが実物で踏んだ（wayback から取るところだけ文字にしていて、
    gzip の回の5枚が戻らない形で壊れた）。
    """

    def test_中身の頭で見分ける(self):
        for 生, 名 in ((b"\x1f\x8b\x08\x00", "gzip"),
                        (b"BZh91AY", "bzip2"),
                        (b"PK\x03\x04", "zip"),
                        (b"\xfd7zXZ\x00", "xz"),
                        (b"(\xb5/\xfd", "zstd")):
            self.assertEqual(recon.atsushuku(生), 名, 名)

    def test_見出しでも見分ける(self):
        """**付け忘れて返すサーバーがあるので、中身も見る。**

        逆に、知らない圧縮の形もあるので見出しも見る。片方だけにしない。
        """
        self.assertEqual(recon.atsushuku(b"<html>", "gzip"), "gzip")
        self.assertEqual(recon.atsushuku(b"<html>", "br"), "br")

    def test_圧縮されていなければ空文字(self):
        self.assertEqual(recon.atsushuku(b"<html><body>", ""), "")
        self.assertEqual(recon.atsushuku(b"<html>", "identity"), "")
        self.assertEqual(recon.atsushuku(b"", ""), "")
        self.assertEqual(recon.atsushuku(b"<html>", "  IDENTITY  "), "")

    def test_圧縮を文字にすると全部置換文字になることを覚えておく(self):
        """**なぜバイトで残すのか**を、ここで1回見せておく。

        戻せないことが分かっていれば、次に急いだ日も文字にしない。
        """
        import gzip
        生 = gzip.compress("大阪市北区梅田1丁目".encode("utf-8"))
        文字, enc = recon.to_text(生, "text/html")
        self.assertEqual(enc, "utf-8(replace)")
        self.assertIn("�", 文字)
        # **文字から生には戻らない。** 保存が文字だと、ここで終わる
        self.assertNotEqual(文字.encode("utf-8", "replace"), 生)
        # バイトで残してあれば戻る
        self.assertEqual(gzip.decompress(生).decode("utf-8"), "大阪市北区梅田1丁目")


class 取りに行ったものを読む前にしまう(unittest.TestCase):
    """**取り直せないものが先**（正本 3.5）。

    前は `analyze()` のあとに書いていた。その朝のページは取り直せないのに、
    **読み取りで例外が出たら1枚も残らない**形だった。
    """

    def 走らせる(self, 生, ctype="text/html", cenc="", 読めなくする=False):
        import tempfile
        d = tempfile.mkdtemp()
        keep_fetch, keep_analyze = recon.fetch, recon.analyze
        recon.fetch = lambda url: (200, ctype, 生, cenc)
        if 読めなくする:
            def 落ちる(*a, **k):
                raise ValueError("読み取りでわざと落とす")
            recon.analyze = 落ちる
        # id はカードを見に行く鍵になった。ここは「門は通った先」を見る検査
        # （読み取り・保存の順番）なので、**検査の中だけの通す偽の門**を差し込む
        # （正本の共通指示書 5節。門そのものの挙動はここでは試さない）
        src = {"id": "test-src", "url": "https://example.test/a",
               "name": "試験", "system": "keibai"}
        keep_robots = recon.check_robots
        recon.check_robots = lambda url: (True, "許可", "")
        keep_wait = recon.WAIT
        recon.WAIT = 0
        keep_genzai = kado.genzai()
        kado._KADO = nise_kado.ToosuMon()
        try:
            res, err = None, None
            try:
                res = recon.recon_one(
                    src, "2026-09-19", d, {},
                    {"bit_pdf": 0, "santen_links": 0})   # main() と同じ形
            except Exception as e:                      # noqa: BLE001
                err = e
            置いた = []
            for cur, _dirs, files in os.walk(d):
                for f in files:
                    with open(os.path.join(cur, f), "rb") as fh:
                        置いた.append(fh.read())
            return res, err, 置いた
        finally:
            recon.fetch, recon.analyze = keep_fetch, keep_analyze
            recon.check_robots = keep_robots
            recon.WAIT = keep_wait
            kado._KADO = keep_genzai

    def test_読み取りで落ちてもバイトは残る(self):
        """**ここが本体。** 落ちる日に、その朝のページを失わない。"""
        生 = b"<html><body>\xe5\xa4\xa7\xe9\x98\xaa</body></html>"
        res, err, 置いた = self.走らせる(生, 読めなくする=True)
        self.assertIsNotNone(err, "わざと落としたのに落ちていない")
        self.assertIn(生, 置いた, "落ちたときにバイトが残っていない")

    def test_圧縮されていたら_バイトは残して中身は読まない(self):
        import gzip
        生 = gzip.compress(b"<html>x</html>")
        res, err, 置いた = self.走らせる(生, cenc="gzip")
        self.assertIsNone(err)
        self.assertIn(生, 置いた, "圧縮でもバイトは残すこと")
        self.assertIn("圧縮", res.get("fetch_error", ""))
        self.assertNotIn("analysis", res,
                         "読めていないのに読んだ顔をしている")

    def test_ふつうのページは今までどおり読む(self):
        生 = b"<html><body><table><tr><td>1</td></tr></table></body></html>"
        res, err, 置いた = self.走らせる(生)
        self.assertIsNone(err)
        self.assertIn(生, 置いた)
        self.assertIn("analysis", res)


class 保存したものが壊れていないか(unittest.TestCase):
    """**置いてあるものを、そのまま数える。**

    仕掛けの検査ではなく、**実物の検査**。書き方をどう直しても、
    壊れたものが1枚でも入ったらここで鳴る。
    """

    def 生データ(self):
        import glob
        out = []
        for top in ("data/raw", "inbox"):
            d = os.path.join(ROOT, top)
            if not os.path.isdir(d):
                continue
            for p in glob.glob(os.path.join(d, "**", "*"), recursive=True):
                if os.path.isfile(p):
                    out.append(p)
        return out

    def setUp(self):
        self.files = self.生データ()
        if not self.files:
            self.skipTest("生データがここには無い（公開用では、これが正しい）")

    def test_圧縮されたまま置かれていない(self):
        見つけた = []
        for p in self.files:
            with open(p, "rb") as f:
                頭 = f.read(8)
            名 = recon.atsushuku(頭)
            if 名:
                見つけた.append("%s（%s）" % (os.path.relpath(p, ROOT), 名))
        self.assertEqual(見つけた, [], "圧縮されたまま置かれている")

    def test_置換文字が混ざっていない(self):
        """**文字にしてから保存した跡。** 1つ入ったら、そこは戻せない。"""
        見つけた = []
        for p in self.files:
            with open(p, "rb") as f:
                b = f.read()
            n = b.count("�".encode("utf-8"))
            if n:
                見つけた.append("%s（%d個）" % (os.path.relpath(p, ROOT), n))
        self.assertEqual(見つけた, [], "置換文字が混ざっている")


# **robots_txtもバイトで残す（旧）は 2026-09-25 に削った。**
# `_get_robots()` が保存していた robots.txt の生バイトの控え
# （data/raw/_robots/<host>.txt）は、common/kado.py に寄せたときに
# 移していない（あちらは robots.txt の本文を控えに残さない）。
# **控えが1つ失われた。** 参謀へ：DESIGN 13章の「BIT の robots.txt に
# 何が書いてあるか」を控えで見る用途があるなら、common/kado.py 側に
# 同じ機能を足すかどうかを判断すること（ここでは決められない）。


class 辿った数を数えて出す(unittest.TestCase):
    """報告に「（辿った数: 0 本）」と **0 を直接書いていた**（2026-09-20）。

    **数えていない 0 は、数えた 0 と見分けられない。**
    実測: 辿るように変えても 0 のままだった。

    ここは2つを分けて見る。
    ① 辿る先を選ぶときに外した数が、ちゃんと増えるか
    ② 辿る先の一覧に、3点セットが1本も残っていないか（本丸）
    """

    BASE = "https://example.test/list.html"

    def 頁(self, *links):
        return "".join('<a href="%s">%s</a>' % (h, lb) for h, lb in links)

    def test_3点セットは辿る先に出てこない(self):
        """**材料は、3点セットの壁だけが効くものでないといけない。**

        ラベルが「物件明細書（3点セット）」だと、後ろの
        `FOLLOW_TEXT`（売却・公売…）でも落ちる。それだと
        3点セットの壁を外しても同じ結果になり、**見分けられない**。
        実測（2026-09-20）: その材料で壁を外しても検査は黙ったままだった。

        だから**辿る条件を全部満たす3点セットのリンク**を渡す。
        壁が効いていれば出てこない。外せば出てくる。
        """
        # 「売却」「一覧」を含むので FOLLOW_TEXT / FOLLOW_TOPIC は通る。
        # 止めているのは url の santen だけ
        通る名 = "令和8年度 売却物件 一覧"
        page = self.頁(("/santen/2026.html", 通る名),
                       ("/r08/list.html", "令和8年度 公売物件一覧"))
        先 = recon.follow_links(page, self.BASE)
        self.assertTrue(先, "材料が1本も辿られない。これでは見分けられない")
        for u, lb in 先:
            self.assertFalse(
                recon.is_santen_link(u, lb),
                "**3点セットを辿る先に入れている**: %s（%s）" % (u, lb))

    def test_外した数が増える(self):
        前 = recon.SANTEN_SKIPPED[0]
        recon.follow_links(self.頁(("/santen/a.html", "3点セット"),
                                   ("/santen/b.html", "物件明細書 3点セット")),
                           self.BASE)
        self.assertGreater(recon.SANTEN_SKIPPED[0], 前,
                           "外したのに数えていない。"
                           "**数えていない0は、数えた0と見分けられない**")

    def test_3点セットが無い日は増えない(self):
        """**材料は、両方でないと見分けられない。**"""
        前 = recon.SANTEN_SKIPPED[0]
        recon.follow_links(self.頁(("/r08/list.html", "令和8年度 公売物件一覧")),
                           self.BASE)
        self.assertEqual(recon.SANTEN_SKIPPED[0], 前,
                         "3点セットが1本も無いのに数が増えた")


class 取得元の欄と題材の欄を分ける(unittest.TestCase):
    """正本 9節「『その取得元が使えない』と『その題材が成立しない』を分ける」。**ある入札サイトが STOP ≠ DB 全体が STOP。**

    前は `enabled` という真偽1つだった。実測（2026-09-21）:
    `enabled: false` の26件の中身は3種類で、
    **「取ってはいけない」は1件も無かった。**

        題材が別（姉妹サイト送り）        21
        GETで再現できない（手で保存）      4
        相手にその頁が無い                 1

    **2026-09-25 から**、取得元の4語は sources.json の欄には書かない。
    カード（`data/ref/torimoto-card.json`）＋運営者承認から `common/kado.py`
    が導く（`common/torikata.py` の docstring）。ここは handoff・manual・url
    未確認という、**カードの手前で決まる**話だけを見る（カード状態が要る話は
    下の `カードから導く取得元の状態` クラスで、偽のカード置き場を使って試す）。
    """

    def もと(self, **kw):
        s = {"id": "x", "url": "https://example.test/a", "system": "keibai"}
        s.update(kw)
        return s

    def test_取らない理由は1つの真偽にしない(self):
        """減らす手が違うので、同じ箱に入れない。"""
        self.assertEqual(torikata.naze_toranai(self.もと(handoff="よそ")),
                         torikata.RIYUU_DAIZAI)
        self.assertEqual(torikata.naze_toranai(self.もと(manual=True, url="")),
                         torikata.RIYUU_TEMOCHI)
        self.assertEqual(torikata.naze_toranai(self.もと(url="")),
                         torikata.RIYUU_NAI)

    def test_手で保存するものを相手に無いと名乗らない(self):
        """**BIT の一覧・結果・過去・取下げは url が空**。

        GETで再現できないから空にしてある。url から先に見ると
        「相手にその頁が無い」と名乗る（実測 2026-09-21: 4件が誤名乗り）。
        """
        self.assertEqual(
            torikata.naze_toranai(self.もと(manual=True, url="")),
            torikata.RIYUU_TEMOCHI)

    def test_torikata欄はもうsources_jsonに無い(self):
        """**カードの「移行元」に写してある。二重に持たない**（common/torikata.py）。"""
        with io.open(os.path.join(ROOT, "sources.json"), encoding="utf-8") as f:
            src = json.load(f)["sources"]
        for s in src:
            self.assertNotIn("torikata", s,
                             "%s に torikata 欄が残っている" % s["id"])
            self.assertNotIn("torikata_riyuu", s,
                             "%s に torikata_riyuu 欄が残っている" % s["id"])

    def test_enabledはもう使わない(self):
        with io.open(os.path.join(ROOT, "sources.json"), encoding="utf-8") as f:
            src = json.load(f)["sources"]
        for s in src:
            self.assertNotIn("enabled", s,
                             "%s に真偽の欄が残っている。"
                             "**4語と真偽を両方持つと、どちらが効くか読めない**"
                             % s["id"])

    def test_handoff以外はカードがある(self):
        """カードid = sources.json の id。**handoff の収集先にはカードが無い**（もともと取らない）。"""
        with io.open(os.path.join(ROOT, "data", "ref", "torimoto-card.json"),
                     encoding="utf-8") as f:
            cards = json.load(f)["cards"]
        with io.open(os.path.join(ROOT, "sources.json"), encoding="utf-8") as f:
            src = json.load(f)["sources"]
        for s in src:
            if s.get("handoff"):
                self.assertNotIn(s["id"], cards,
                                 "%s は姉妹サイト送りなのにカードがある"
                                 "（もともと取らないもの。カードは要らない）" % s["id"])
                continue
            self.assertIn(s["id"], cards,
                          "%s にカードが無い（足した日に黙って取りに行かなくなる）"
                          % s["id"])

    def test_実データの題材(self):
        """**4つの題材を全部出す。通れないものも出す。**

        **いまは運営者の承認が1件も無いので、どの題材も「通れる」にはならない**
        （カード＋承認がそろって初めて通る。迷ったら止まる側に倒した初期状態。
        承認が進んでここが崩れたら、参謀 が見直すこと。カードから実際に
        「取ってよい」を導けることは `カードから導く取得元の状態` クラスが
        偽のカード置き場で確かめている）。
        """
        with io.open(os.path.join(ROOT, "sources.json"), encoding="utf-8") as f:
            src = json.load(f)["sources"]
        d = torikata.daizai(src)
        self.assertEqual(sorted(d), ["keibai", "kobai", "kokuyu", "koyu"])
        # **取りに行っているのに「取ってよい」ではない取得元は、いつも空が正しい。**
        # 関所が緩んでいれば、ここが空でなくなる
        self.assertEqual(torikata.kiwadoi(src), [])


class カードから導く取得元の状態(unittest.TestCase):
    """`common/torikata.py` の4語が、カード＋運営者承認から正しく導かれるか。

    **偽のカード置き場でだけ試す**（`data/ref/shounin/` に承認ファイルを
    作らない。`tests/test_kado.py` の `Oki` と同じ形。`tests/nise_kado.py`）。
    本物の置き場（sources.json・data/ref/）は見ない。
    """

    def setUp(self):
        yoi = nise_kado.card()
        dame = nise_kado.card(統括判定案="取ってはいけない")
        mikakutei = nise_kado.card(統括判定案="規約未確定")
        cards = {"yoi": yoi, "dame": dame, "mikakutei": mikakutei}
        shounin = {"yoi": nise_kado.shounin_of("yoi", yoi)}
        self.root = nise_kado.repo(cards, nise_kado.daicho_of(cards), shounin)
        self.addCleanup(shutil.rmtree, self.root, True)
        self.keep = torikata.ROOT
        torikata.ROOT = self.root
        self.addCleanup(setattr, torikata, "ROOT", self.keep)

    def もと(self, **kw):
        s = {"id": "yoi", "url": "https://example.test/a", "system": "keibai"}
        s.update(kw)
        return s

    def test_承認までそろえば取ってよい(self):
        self.assertEqual(torikata.go(self.もと()), "取ってよい")
        self.assertTrue(torikata.toru(self.もと()))
        self.assertEqual(torikata.naze_toranai(self.もと()), "")
        self.assertEqual(torikata.kiwadoi([self.もと()]), [])

    def test_取ってはいけないものは取らない(self):
        self.assertFalse(torikata.toru(self.もと(id="dame")))
        self.assertIn(torikata.TORANAI,
                      torikata.naze_toranai(self.もと(id="dame")))

    def test_取ってよい以外は取りに行かず_kiwadoiも空(self):
        """`kiwadoi()` は、関所が正しければいつも空になる。"""
        for cid in ("dame", "mikakutei", "nai-card"):
            with self.subTest(cid=cid):
                s = self.もと(id=cid)
                self.assertFalse(torikata.toru(s), cid)
                self.assertEqual(torikata.kiwadoi([s]), [], cid)

    def test_カードが無い先は未確認として取らない(self):
        """**知らない語と同じく、取らない側に倒す。** カードが無ければ「未確認」。"""
        self.assertEqual(torikata.go(self.もと(id="nai-card")), "未確認")
        self.assertFalse(torikata.toru(self.もと(id="nai-card")))

    def test_idが無いものは取らない(self):
        s = self.もと()
        del s["id"]
        self.assertFalse(torikata.toru(s))
        self.assertIn("id", torikata.naze_toranai(s))

    def test_題材は取得元が1つ止まっても止まらない(self):
        d = torikata.daizai([self.もと(id="yoi", system="keibai"),
                             self.もと(id="dame", system="keibai")])
        self.assertEqual(d["keibai"], {"取得元": 2, "通る": 1, "通れる": True})

    def test_題材ぜんぶ止まっていることは見える(self):
        d = torikata.daizai([self.もと(id="dame", system="koyu")])
        self.assertFalse(d["koyu"]["通れる"])

    def test_handoffはカードより先に見る(self):
        """カードが無い id でも、handoff が付いていれば「題材が別」で止まる。"""
        s = self.もと(id="handoff付きの空id", handoff="よそ")
        self.assertEqual(torikata.naze_toranai(s), torikata.RIYUU_DAIZAI)


class 取る判定はカードの門を通る(unittest.TestCase):
    """**recon.py が古い判定に戻ったら鳴る。**

    前の recon.py は `torikata.naze_toranai(src)`（sources.json の4語）を
    見ていた。いまは `K.card_mon()` / `with K.sesshon():`（common/kado.py）を
    見る。`torikata.py` の検査だけでは、`recon_one()` がそれを使っているかは
    分からない。だから `recon_one()` そのものに渡して、robots を見る手前で
    止まるかを見る。**外には出ない**（robots を見に行くところを差し替えて
    あるうえ、カードの門が通さなければ `check_robots()` 自体が呼ばれない）。
    """

    def setUp(self):
        self._k = None
        self.keep_genzai = kado.genzai()
        self.addCleanup(self._modosu)

    def _modosu(self):
        kado._KADO = self.keep_genzai
        if self._k is not None:
            self._k.close()

    def 据える(self, **kw):
        self._k = nise_kado.Kumitate(**kw)
        kado._KADO = self._k.kado()
        return self._k

    def 渡す(self, cid, url=None):
        呼んだ = []

        def 見に行った(*a, **k):
            呼んだ.append(a)
            raise RuntimeError("robots を見に行くところまで来た")

        keep = recon.check_robots
        recon.check_robots = 見に行った
        src = {"id": cid, "name": "試験", "system": "keibai",
               "kind": "bit-schedule",
               "url": url or "https://example.invalid/data/x.html"}
        # **保存先は金庫（KINKO_DIR）の中でなければならない**（Kado.kinko_preflight）。
        # 別の一時フォルダを渡すと、承認がそろっていても金庫の手前で止まる
        raw_dir = os.path.join(self._k.kinko, "raw")
        try:
            res = recon.recon_one(src, "2026-10-01", raw_dir, {}, {})
        except RuntimeError:
            res = None
        finally:
            recon.check_robots = keep
        return 呼んだ, res

    def test_カードが無い先はrobotsの手前で止まる(self):
        self.据える(cid="shiken")
        呼んだ, res = self.渡す("nai-card")
        self.assertEqual(呼んだ, [],
                         "カードの無い取得元に robots を見に行った。"
                         "取る判定が common/kado.py の門を通っていない")
        self.assertIn("門で止めた", res["skipped"])

    def test_未承認は通らない(self):
        self.据える(cid="mikakutei", shounin=False, 統括判定案="取ってよい")
        呼んだ, res = self.渡す("mikakutei")
        self.assertEqual(呼んだ, [])
        self.assertIn("門で止めた", res["skipped"])

    def test_取ってはいけないは通らない(self):
        self.据える(cid="dame", 統括判定案="取ってはいけない")
        呼んだ, res = self.渡す("dame")
        self.assertEqual(呼んだ, [])
        self.assertIn("門で止めた", res["skipped"])

    def test_承認された先はrobotsまで行く(self):
        """**材料が見分けられることの確かめ。** 差し替えが効いていなければ、上の1本は何も見ていない。"""
        k = self.据える(cid="shiken")
        呼んだ, _ = self.渡す(k.cid, url="https://example.invalid/data/x.html")
        self.assertEqual(len(呼んだ), 1)


if __name__ == "__main__":
    unittest.main()
