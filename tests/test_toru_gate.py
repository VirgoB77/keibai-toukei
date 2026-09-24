#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""取りに行ってよいかの関所を2つ固定する（2026-09-24）。

鯨屋DBの固定線：**迷ったら止まる。robots で断られたら取らない。未確認を許可扱いしない。**

    規約の関所   common/torikata.py の naze_toranai()   取りに行くのは「取ってよい」だけ
    robots の関所 recon.py の check_robots()             読めて Allow か、404 / 410 だけ通す

前はどちらも緩かった。

    - 「未確認」「規約未確定」の取得元にも毎日取りに行っていた（15件）
    - robots.txt が 403・5xx・つながらない・読めない でも「取得は続ける」で通していた
    - robots.txt が redirect されて、よその host やふつうの HTML（200）が返っても、
      規則が1行も無いものとして読み「全部許可」になっていた

ここでは recon_one() に取得元を1つずつ渡し、**本文を取りに行ったか**で見る。
robots.txt への問い合わせは偽の応答で返し、本文の取得は差し替えて数える。
**外へは1本も出ない**（通信は封じてある）。

    python3 -m unittest discover -s tests
"""

import gzip
import io
import json
import os
import shutil
import socket
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import recon  # noqa: E402
from common import torikata  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOW = "User-agent: *\nAllow: /\n"
DISALLOW = "User-agent: *\nDisallow: /\n"


def 外へ出た(*a, **k):
    raise AssertionError("外へ出ていこうとした（テストでは通信しない）")


class 関所(unittest.TestCase):
    """取得元1つと robots.txt の返り方を決めて、recon_one() に通す。"""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.robots_calls = []
        self.fetch_calls = []
        self.robots = ("body", ALLOW)

        def robots_txt(req, timeout=None):
            self.robots_calls.append(getattr(req, "full_url", req))
            kind, v = self.robots
            if kind == "code":
                raise urllib.error.HTTPError(req.full_url, v, "x", {}, None)
            if kind == "code_at":     # (コード, redirect のあとの URL)。urllib と同じく、先の URL で落ちる
                code, final = v
                raise urllib.error.HTTPError(final, code, "x", {}, None)
            if kind == "exc":
                raise v
            if kind == "resp":        # (本文, Content-Type, redirect のあとの URL)
                body, ctype, final = v
                return 偽の応答(body, ctype=ctype, final=final)
            return 偽の応答(v, final=req.full_url)

        def 本文(url):
            self.fetch_calls.append(url)
            return (200, "text/html; charset=utf-8",
                    b"<html><body><table><tr><th>a</th><th>b</th></tr>"
                    b"<tr><td>1</td><td>2</td></tr></table></body></html>", "")

        for p in (
                mock.patch.object(recon, "HERE", self.d),
                mock.patch.object(recon, "WAIT", 0),
                mock.patch.object(recon, "_ROBOTS_CACHE", {}),
                mock.patch.object(recon, "_BUSY_HOSTS", set()),
                mock.patch.object(recon.time, "sleep", lambda _n: None),
                mock.patch.object(recon, "fetch", 本文),
                mock.patch("urllib.request.urlopen", robots_txt),
                mock.patch("socket.create_connection", 外へ出た),
                mock.patch.object(socket.socket, "connect", 外へ出た)):
            p.start()
            self.addCleanup(p.stop)

    def 取得元(self, **kw):
        s = {"id": "shiken", "name": "試験", "system": "kobai",
             "kind": "kobai-list", "url": "https://example.invalid/a.html",
             "torikata": "取ってよい", "torikata_riyuu": "試験", "note": "試験"}
        s.update(kw)
        return s

    def 通す(self, src=None, robots=None):
        if robots is not None:
            self.robots = robots
        self.counts = {}
        res = recon.recon_one(src or self.取得元(), "2026-10-01",
                              os.path.join(self.d, "raw"), self.counts,
                              {"bit_pdf": 0, "santen_links": 0})
        return res

    def 取りに行った(self, res, url="https://example.invalid/a.html"):
        self.assertEqual(self.fetch_calls, [url])
        self.assertNotIn("skipped", res)

    def 取りに行かなかった(self, res, msg):
        self.assertEqual(self.fetch_calls, [], "本文を取りに行った: %s" % msg)
        self.assertIn("skipped", res, msg)


class 偽の応答:
    status = 200

    def __init__(self, v, ctype="text/plain", final=None):
        if isinstance(v, bytes):
            self._b = v
            self.headers = {"Content-Type": ctype, "Content-Encoding": "gzip"}
        else:
            self._b = v.encode("utf-8")
            self.headers = {"Content-Type": ctype}
        self._final = final

    def geturl(self):
        return self._final

    def read(self, n=None):
        return self._b[:n] if n else self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class 規約の関所(関所):
    """**取りに行くのは「取ってよい」だけ。** robots より手前で止まる。"""

    def test_取ってよいは通る(self):
        self.取りに行った(self.通す())

    def test_取ってよい以外は止まる(self):
        for 語 in ("未確認", "規約未確定", "取ってはいけない",
                  "取ってよし", "OK", "", None):
            self.fetch_calls, self.robots_calls = [], []
            res = self.通す(self.取得元(torikata=語))
            self.取りに行かなかった(res, repr(語))
            self.assertEqual(self.robots_calls, [],
                             "%r で robots.txt を見に行った。規約の関所より先に出ている"
                             % (語,))

    def test_欄が無いものは止まる(self):
        s = self.取得元()
        del s["torikata"]
        self.取りに行かなかった(self.通す(s), "欄なし")
        self.assertEqual(self.robots_calls, [])

    def test_robotsが無くても規約の関所は別に要る(self):
        """404 は robots の関所を通すだけ。規約の関所の代わりにはならない。"""
        res = self.通す(self.取得元(torikata="規約未確定"), robots=("code", 404))
        self.取りに行かなかった(res, "規約未確定・robots 404")

    def test_実データで取りに行くのは取ってよいだけ(self):
        with io.open(os.path.join(ROOT, "sources.json"), encoding="utf-8") as f:
            srcs = json.load(f)["sources"]
        行く = [s for s in srcs if torikata.toru(s)]
        self.assertTrue(行く, "取りに行く取得元が1つも無い（見張りが空回りしている）")
        for s in 行く:
            self.assertEqual(torikata.go(s), torikata.TORU, s["id"])
        self.assertEqual(torikata.kiwadoi(srcs), [])


class robotsの関所(関所):
    """**読めて Allow か、404 / 410 だけ通す。** 分からないときは取らない。"""

    def test_Allowは通る(self):
        self.取りに行った(self.通す(robots=("body", ALLOW)))

    def test_Disallowは止まる(self):
        res = self.通す(robots=("body", DISALLOW))
        self.取りに行かなかった(res, "Disallow")
        self.assertEqual(res["skipped"], recon.ROBOTS_KYOHI)
        self.assertEqual(self.counts.get("拒否"), 1)

    def test_404と410はrobotsの関所だけ通る(self):
        for code in (404, 410):
            self.fetch_calls = []
            recon._ROBOTS_CACHE.clear()
            self.取りに行った(self.通す(robots=("code", code)))

    def test_読めなかったら止まる(self):
        """401・403・ほかの 4xx・5xx は、**許可に変えない。**"""
        for code in (401, 403, 400, 451, 500, 502, 504):
            self.fetch_calls = []
            recon._ROBOTS_CACHE.clear()
            res = self.通す(robots=("code", code))
            self.取りに行かなかった(res, "HTTP %d" % code)
            self.assertEqual(res["skipped"], recon.ROBOTS_FUMEI, code)
            self.assertEqual(self.counts.get("robots不明"), 1, code)
            self.assertNotIn("拒否", self.counts, "読めなかったのを拒否と数えた")

    def test_混んでいたら止まる(self):
        """429 / 503 はその日そのサーバーへ行かない（正本 3.4）。"""
        for code in (429, 503):
            self.fetch_calls = []
            recon._ROBOTS_CACHE.clear()
            recon._BUSY_HOSTS.clear()
            res = self.通す(robots=("code", code))
            self.取りに行かなかった(res, "HTTP %d" % code)
            self.assertTrue(res.get("back_off"), code)

    def test_つながらないと時間切れは止まる(self):
        for e in (urllib.error.URLError("つながらない"),
                  socket.timeout("時間切れ"),
                  ConnectionResetError("切れた"),
                  OSError("読めない")):
            self.fetch_calls = []
            recon._ROBOTS_CACHE.clear()
            res = self.通す(robots=("exc", e))
            self.取りに行かなかった(res, type(e).__name__)
            self.assertEqual(res["skipped"], recon.ROBOTS_FUMEI)

    def test_圧縮のまま返ってきたら止まる(self):
        res = self.通す(robots=("body", gzip.compress(ALLOW.encode("utf-8"))))
        self.取りに行かなかった(res, "圧縮のまま")
        self.assertEqual(res["skipped"], recon.ROBOTS_FUMEI)

    def test_読み取れなかったら止まる(self):
        with mock.patch.object(recon.urllib.robotparser.RobotFileParser,
                               "parse", side_effect=ValueError("読めない")):
            res = self.通す(robots=("body", ALLOW))
        self.取りに行かなかった(res, "parse 不能")
        self.assertEqual(res["skipped"], recon.ROBOTS_FUMEI)

    def test_redirectの先がふつうのHTMLなら止まる(self):
        """**robots.txt → redirect → ふつうの HTML（200）。**

        規則が1行も無いものとして読むと「全部許可」になる。読めたとは言えない。
        """
        html = "<!DOCTYPE html>\n<html><head><title>トップ</title></head></html>"
        res = self.通す(robots=("resp", (html, "text/html; charset=utf-8",
                                         "https://example.invalid/index.html")))
        self.取りに行かなかった(res, "redirect の先が HTML")
        self.assertEqual(res["skipped"], recon.ROBOTS_FUMEI)
        self.assertEqual(self.counts.get("robots不明"), 1)

    def test_よそのhostへのredirectは止まる(self):
        """中身が規則でも、**どの host の規則か曖昧**なら取らない。"""
        for final in ("https://other.invalid/robots.txt",
                      "https://www.example.invalid/robots.txt"):
            self.fetch_calls = []
            recon._ROBOTS_CACHE.clear()
            res = self.通す(robots=("resp", (ALLOW, "text/plain", final)))
            self.取りに行かなかった(res, final)
            self.assertEqual(res["skipped"], recon.ROBOTS_FUMEI, final)

    def test_robots_txtではない場所へのredirectは止まる(self):
        for final in ("https://example.invalid/robots.txt.html",
                      "https://example.invalid/error/404.txt"):
            self.fetch_calls = []
            recon._ROBOTS_CACHE.clear()
            res = self.通す(robots=("resp", (ALLOW, "text/plain", final)))
            self.取りに行かなかった(res, final)

    def test_redirectされずにHTMLが返っても止まる(self):
        html = "\n  <html><body>ようこそ</body></html>"
        res = self.通す(robots=("resp", (
            html, "text/plain", "https://example.invalid/robots.txt")))
        self.取りに行かなかった(res, "200 で HTML")

    def test_同じhostのhttpからhttpsへのredirectは読む(self):
        """**締めすぎない。** 同じ host の /robots.txt なら、規則をそのまま当てる。"""
        src = self.取得元(url="http://example.invalid/a.html")
        res = self.通す(src, robots=("resp", (
            ALLOW, "text/plain", "https://example.invalid/robots.txt")))
        self.取りに行った(res, "http://example.invalid/a.html")
        self.fetch_calls = []
        recon._ROBOTS_CACHE.clear()
        res = self.通す(src, robots=("resp", (
            DISALLOW, "text/plain", "https://example.invalid/robots.txt")))
        self.取りに行かなかった(res, "https に移った先の Disallow")
        self.assertEqual(res["skipped"], recon.ROBOTS_KYOHI)

    def test_redirectなしの404と410は今までどおり通る(self):
        for code in (404, 410):
            self.fetch_calls = []
            recon._ROBOTS_CACHE.clear()
            res = self.通す(robots=("code_at", (
                code, "https://example.invalid/robots.txt")))
            self.取りに行った(res)

    def test_同じhostのhttpからhttpsの404はrobotsなしとして通る(self):
        """**対象の host 自身の robots.txt が無いと確かめられた。**"""
        src = self.取得元(url="http://example.invalid/a.html")
        for code in (404, 410):
            self.fetch_calls = []
            recon._ROBOTS_CACHE.clear()
            res = self.通す(src, robots=("code_at", (
                code, "https://example.invalid/robots.txt")))
            self.取りに行った(res, "http://example.invalid/a.html")

    def test_よそのhostへredirectされた先の404は止まる(self):
        """よその host に robots.txt が無いことは、対象の host の話ではない。"""
        for code in (404, 410):
            for final in ("https://other.invalid/robots.txt",
                          "https://www.example.invalid/robots.txt"):
                self.fetch_calls = []
                recon._ROBOTS_CACHE.clear()
                res = self.通す(robots=("code_at", (code, final)))
                self.取りに行かなかった(res, "%d %s" % (code, final))
                self.assertEqual(res["skipped"], recon.ROBOTS_FUMEI)
                self.assertEqual(self.counts.get("robots不明"), 1)

    def test_同じhostのほかの場所へredirectされた先の404は止まる(self):
        """エラーのページが 404 を返しても、robots.txt が無いとは確かめられていない。"""
        for code in (404, 410):
            for final in ("https://example.invalid/error/404.html",
                          "https://example.invalid/robots.txt/"):
                self.fetch_calls = []
                recon._ROBOTS_CACHE.clear()
                res = self.通す(robots=("code_at", (code, final)))
                self.取りに行かなかった(res, "%d %s" % (code, final))
                self.assertEqual(res["skipped"], recon.ROBOTS_FUMEI)

    def test_見出しがtext_htmlでも中身が規則なら読む(self):
        """**見出しではなく中身で見る。** 見出しだけで止めると締めすぎる。"""
        res = self.通す(robots=("resp", (
            ALLOW, "text/html", "https://example.invalid/robots.txt")))
        self.取りに行った(res)

    def test_読めなかったことを許可に変えない(self):
        """check_robots() そのもの。**辿った先もここを通る。**"""
        for robots in (("code", 403), ("code", 500),
                       ("exc", urllib.error.URLError("x"))):
            recon._ROBOTS_CACHE.clear()
            self.robots = robots
            ok, why, _ = recon.check_robots("https://example.invalid/b.html")
            self.assertFalse(ok, robots)
            self.assertEqual(why, recon.ROBOTS_FUMEI)


if __name__ == "__main__":
    unittest.main()
