#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""偵察の「やってはいけないこと」を固定する。

DESIGN 1章の決定事項のうち、コードで守れるものをここで縛る。
いちばん大事なのは **BITから3点セットを取らない** こと。
うっかり便利にしようとして壁を崩したら、ここが落ちる。

    python3 -m unittest discover -s tests
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import recon  # noqa: E402

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
            if s.get("enabled") and not s.get("manual"):
                self.assertTrue(s.get("url"), s["id"])

    def test_URL未確認のものは止めてある(self):
        for s in self.sources:
            if not s.get("url"):
                self.assertFalse(s.get("enabled"), s["id"])

    def test_KSIと財務省の売却サイトは入れていない(self):
        for s in self.sources:
            url = s.get("url") or ""
            self.assertNotIn("kankocho.jp", url)
            self.assertNotIn("akiya-athome.jp", url)


class 取得の作法(unittest.TestCase):
    """正本 3.4「断られたら、そこで打ち切る。回り込まない」を固定する。

    ここが緩むと、相手のサーバーに二重に当てたり、断られている場所を
    取りに行ったりする。about ページで読者に約束していることでもある。
    """

    def setUp(self):
        import shutil
        import tempfile
        import urllib.request
        recon._ROBOTS_CACHE.clear()
        # robots.txt の控えはリポジトリに書かせない。テストで data/raw を汚さない
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        self.addCleanup(setattr, recon, "HERE", recon.HERE)
        recon.HERE = tmp
        self.calls = []
        self.real = urllib.request.urlopen
        self.addCleanup(setattr, urllib.request, "urlopen", self.real)
        self.addCleanup(recon._ROBOTS_CACHE.clear)
        # 待ち時間はテストでは飛ばす（作法そのものは別のテストで見る）
        self.sleep = recon.time.sleep
        recon.time.sleep = lambda _n: None
        self.addCleanup(setattr, recon.time, "sleep", self.sleep)

    def 応答(self, body="", code=None):
        import urllib.error
        import urllib.request

        class Fake:
            status = 200
            headers = {"Content-Type": "text/plain"}

            def __init__(self, b):
                self._b = b.encode("utf-8")

            def read(self, n=None):
                return self._b[:n] if n else self._b

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake(req, timeout=None):
            self.calls.append((getattr(req, "full_url", req),
                               dict(getattr(req, "headers", {}))))
            if code:
                raise urllib.error.HTTPError(
                    getattr(req, "full_url", ""), code, "x", {}, None)
            return Fake(body)

        urllib.request.urlopen = fake

    def test_robots_txtを2度取りに行かない(self):
        # 前は本文を取ったあと RobotFileParser.read() でもう1回取っていた
        self.応答("User-agent: *\nAllow: /\n")
        recon.check_robots("https://example.lg.jp/a.html")
        self.assertEqual(len(self.calls), 1, self.calls)

    def test_robots_txtにも名乗る(self):
        self.応答("User-agent: *\nAllow: /\n")
        recon.check_robots("https://example.lg.jp/a.html")
        ua = [v for k, v in self.calls[0][1].items() if k.lower() == "user-agent"]
        self.assertEqual(ua, [recon.UA])

    def test_同じホストなら1回しか取らない(self):
        self.応答("User-agent: *\nAllow: /\n")
        recon.check_robots("https://example.lg.jp/a.html")
        recon.check_robots("https://example.lg.jp/b.html")
        self.assertEqual(len(self.calls), 1)

    def test_Disallowは守る(self):
        self.応答("User-agent: *\nDisallow: /himitsu/\n")
        ok, why, _ = recon.check_robots("https://example.lg.jp/himitsu/x.html")
        self.assertFalse(ok)
        self.assertIn("拒否", why)
        ok2, _why2, _ = recon.check_robots("https://example.lg.jp/ok.html")
        self.assertTrue(ok2)

    def test_混んでいるのを拒否と書かない(self):
        # 429 / 503 は「いまは待って」。拒否ではない。押し込まず打ち切る
        for code in (429, 503):
            recon._ROBOTS_CACHE.clear()
            self.calls = []
            self.応答(code=code)
            with self.assertRaises(recon.BackOff):
                recon.check_robots("https://example.lg.jp/a.html")

    def test_robots_txtが無いのは拒否ではない(self):
        self.応答(code=404)
        ok, why, _ = recon.check_robots("https://example.lg.jp/a.html")
        self.assertTrue(ok)
        self.assertIn("無い", why)

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


if __name__ == "__main__":
    unittest.main()
