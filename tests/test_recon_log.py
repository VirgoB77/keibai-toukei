#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""偵察レポートの本文を、公開される Actions のログと要約に出さない。

公開用 repo の Actions のログと要約（GITHUB_STEP_SUMMARY）は、誰でも読める。
偵察レポートは「このファイルは公開しない」と名乗っているのに、前は同じ本文を
print し、要約にも書いていた（2026-09-24 に run #7 のログで確かめた）。

**後から伏せ字にしない。そもそも流さない。** だからここでは、
中身に目印を仕込んだ偵察を実際に1回走らせて、出たものを全部読む。

    - 詳しいレポートは今までどおり data/recon-report.md に書かれる（目印が入っている）
    - 標準出力・標準エラー・要約には、目印もレポートの行も1つも出ない
    - 出てよいのは決まった形の行だけ。**形を並べるのはこちら（見張り）の側**
    - 止まったときも、詳しいこと（traceback）はレポートにだけ書き、ログには型の名前だけ
    - 外へは1本も出ていかない（取得と robots は差し替え、通信は封じてある）

    python3 -m unittest discover -s tests
"""

import contextlib
import io
import json
import os
import re
import shutil
import socket
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import recon  # noqa: E402
from common.report import NOT_PUBLIC_LINE  # noqa: E402

# レポートにだけ入ってよい目印。**ログ・要約に1つでも出たら鳴る**
目印 = "ZQ7"
取得元 = [
    {"id": "himitsu-id-ZQ7", "name": "目印の取得元 ZQ7", "system": "kobai",
     "area": "osaka", "kind": "kobai-list", "torikata": "取ってよい",
     "url": "https://example.invalid/himitsu-path-ZQ7.html",
     "note": "目印のメモ ZQ7"},
    {"id": "okuri-id-ZQ7", "name": "送る取得元 ZQ7", "system": "kokuyu",
     "area": "osaka", "kind": "kokuyu-list", "torikata": "取ってよい",
     "handoff": "姉妹サイト",
     "url": "https://example.invalid/okuri-path-ZQ7.html",
     "note": "送るメモ ZQ7"},
    {"id": "kowareta-id-ZQ7", "name": "取れない取得元 ZQ7", "system": "kobai",
     "area": "hyogo", "kind": "kobai-list", "torikata": "取ってよい",
     "url": "https://example.invalid/kowareta-path-ZQ7.html",
     "note": "取れないメモ ZQ7"},
]
ページ = ("<html><body><table>"
       "<tr><th>見出しの目印 ZQ7</th><th>列</th></tr>"
       "<tr><td>本文の目印 ZQ7</td><td>x</td></tr>"
       "</table></body></html>").encode("utf-8")

# **公開ログに出てよい形。** ここに無い形の行が出たら鳴る（足した日に黙らない向き）
出てよい形 = [
    re.compile(r"偵察を始める（取得元 \d+ 件）"),
    re.compile(r"偵察を終えた。詳しいレポートは data/recon-report\.md に書いた"
               r"（公開しない。本文はログに出さない）"),
    re.compile(r"取得元 \d+ 件：取りに行った \d+ / 行かなかった \d+ / 取れなかった \d+"),
    re.compile(r"偵察が途中で止まった（[A-Za-z_][A-Za-z0-9_]*）。"
               r"詳しいことは data/recon-report\.md に書いた（公開しない）"),
]


def 取ってくる(url):
    if "kowareta" in url:
        raise RuntimeError("取れなかった詳しい文 ZQ7 %s" % url)
    return 200, "text/html; charset=utf-8", ページ, None


def 外へ出た(*a, **k):
    raise AssertionError("外へ出ていこうとした（テストでは通信しない）")


class 走らせる(unittest.TestCase):
    """目印を仕込んだ偵察を1回走らせ、出たものを全部とっておく。"""

    壊す = None          # main の途中で止めたいときに、差し替える関数の名前

    def setUp(self):
        self.d = tempfile.mkdtemp()
        with io.open(os.path.join(self.d, "sources.json"), "w",
                     encoding="utf-8") as f:
            json.dump({"sources": 取得元}, f, ensure_ascii=False)
        self.要約 = os.path.join(self.d, "summary.md")
        self.取った = []

        def 数えて取る(url):
            self.取った.append(url)
            return 取ってくる(url)

        差し替え = [
            mock.patch.object(recon, "HERE", self.d),
            mock.patch.object(recon, "WAIT", 0),
            mock.patch.object(recon, "_BUSY_HOSTS", set()),
            mock.patch.object(recon, "check_robots",
                              lambda url: (True, "許可（テスト）", None)),
            mock.patch.object(recon, "fetch", 数えて取る),
            mock.patch.object(sys, "argv", ["recon.py"]),
            mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": self.要約}),
            # **通信を封じる。** 差し替えを漏らしても、ここで落ちる
            mock.patch("urllib.request.urlopen", 外へ出た),
            mock.patch("socket.create_connection", 外へ出た),
            mock.patch.object(socket.socket, "connect", 外へ出た),
        ]
        if self.壊す:
            差し替え.append(mock.patch.object(
                recon, self.壊す,
                mock.Mock(side_effect=RuntimeError(
                    "止まったときの詳しい文 ZQ7 https://example.invalid/x-ZQ7"))))
        for p in 差し替え:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(shutil.rmtree, self.d, True)

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.code = recon.run()
        self.out, self.err = out.getvalue(), err.getvalue()
        try:
            with io.open(self.要約, encoding="utf-8") as f:
                self.summary = f.read()
        except OSError:
            self.summary = ""
        with io.open(os.path.join(self.d, "data", "recon-report.md"),
                     encoding="utf-8") as f:
            self.report = f.read()

    def 公開される(self):
        return {"標準出力": self.out, "標準エラー": self.err,
                "要約": self.summary}

    def 目印が出ていない(self):
        for どこ, 中身 in self.公開される().items():
            self.assertNotIn(目印, 中身, "%s に目印が出た:\n%s" % (どこ, 中身))
            for s in ("example.invalid", "himitsu", "kowareta", "okuri",
                      "data/raw", NOT_PUBLIC_LINE):
                self.assertNotIn(s, 中身, "%s に %r が出た" % (どこ, s))

    def 決まった形だけ(self):
        for どこ, 中身 in self.公開される().items():
            for line in 中身.splitlines():
                if not line.strip():
                    continue
                self.assertTrue(
                    any(p.fullmatch(line) for p in 出てよい形),
                    "%s に決まっていない形の行が出た: %r" % (どこ, line))


class ふつうに終わったとき(走らせる):

    def test_詳しいレポートは今までどおり書く(self):
        """**目印がレポートに入っていること**を先に見る。入っていなければ、
        ログに出ていないことを見ても意味が無い。"""
        self.assertTrue(self.report.startswith("# 競売統計 偵察レポート（"))
        self.assertIn(NOT_PUBLIC_LINE, self.report)
        for s in ("https://example.invalid/himitsu-path-ZQ7.html",
                  "himitsu-id-ZQ7", "見出しの目印 ZQ7",
                  "取れなかった詳しい文 ZQ7", "姉妹サイト送り"):
            self.assertIn(s, self.report, s)

    def test_取ってきたページは今までどおり残す(self):
        d = os.path.join(self.d, "data", "raw", "himitsu-id-ZQ7")
        self.assertEqual(len(os.listdir(d)), 1)

    def test_ログにも要約にも本文を出さない(self):
        self.目印が出ていない()
        # レポートの行が1本でも混ざっていたら鳴る（行ごと print に戻した形を捕まえる）
        for どこ, 中身 in self.公開される().items():
            for line in self.report.splitlines():
                if len(line.strip()) >= 6:
                    self.assertNotIn(line, 中身,
                                     "%s にレポートの行が出た: %r" % (どこ, line))

    def test_出てよいのは決まった形の行だけ(self):
        self.決まった形だけ()
        self.assertEqual(self.err, "", "ふつうに終わったのに標準エラーに何か出た")

    def test_件数は数えたとおり(self):
        self.assertIn("偵察を始める（取得元 3 件）", self.out)
        self.assertIn("取得元 3 件：取りに行った 2 / 行かなかった 1 / 取れなかった 1",
                      self.out)
        self.assertIn("取得元 3 件：取りに行った 2 / 行かなかった 1 / 取れなかった 1",
                      self.summary, "要約にも件数の行は出す")

    def test_終了コードは0(self):
        self.assertEqual(self.code, 0)

    def test_外へは1本も出ていない(self):
        """取得は差し替えたものだけを通った。通信は封じてあるので、
        差し替えを漏らしたら AssertionError で止まり、ここまで来ない。"""
        self.assertEqual(sorted(self.取った), sorted([
            "https://example.invalid/himitsu-path-ZQ7.html",
            "https://example.invalid/kowareta-path-ZQ7.html"]))


class 途中で止まったとき(走らせる):
    """**止まっても、詳しいことは公開ログに出さない。**

    何もしないと Python が traceback（例外の文・途中の値）を標準エラーに出す。
    """

    壊す = "report_one"

    def test_終了コードは1(self):
        self.assertEqual(self.code, 1)

    def test_詳しいことはレポートにだけ書く(self):
        self.assertIn("# 偵察が途中で止まった", self.report)
        self.assertIn("止まったときの詳しい文 ZQ7", self.report)
        self.assertIn("Traceback", self.report)

    def test_止まってもレポートの頭に公開しないが付く(self):
        """頭が無い記録は、翌朝の最初の検査（test_public）で落ちる。"""
        head = "".join(self.report.splitlines(True)[:5])
        self.assertTrue(self.report.startswith("# 競売統計 偵察レポート（"))
        self.assertIn(NOT_PUBLIC_LINE, head)

    def test_ログには決まった形と型の名前だけ(self):
        self.目印が出ていない()
        self.決まった形だけ()
        self.assertNotIn("Traceback", self.err)
        self.assertIn("偵察が途中で止まった（RuntimeError）", self.err)


if __name__ == "__main__":
    unittest.main()
