#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""配られている実物を見る検査（scripts/check_haishin.py）。

**本物のサーバーを立てて確かめる。** 差し替えの偽物だと、
「リダイレクトを追わない」が本当かどうかは分からない
（追う/追わないを決めているのは urllib の中だから）。

    127.0.0.1 に小さいサーバーを立てて、配るものを入れ替える。
    外には出ない。

    python3 -m unittest discover -s tests
"""

import io
import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import check_haishin  # noqa: E402
from common import site  # noqa: E402

# サーバーが配るもの。テストごとに入れ替える
配るもの = {"code": 200, "body": "{}", "type": "application/json"}
見たUA = []


class _手(BaseHTTPRequestHandler):

    def do_GET(self):
        見たUA.append(self.headers.get("User-Agent") or "")
        # **飛ばし先は必ず通る中身にしておく。**
        # 飛ばし先も止まる形にすると、追っても追わなくても止まるので、
        # 「追わないこと」を確かめたことにならない（検査が空回りする）
        if self.path == "/tobisaki.json":
            body = b'{"records": [], "counts_by_city": [9]}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        code = 配るもの["code"]
        self.send_response(code)
        if code in (301, 302, 307, 308):
            self.send_header("Location", 配るもの["body"])
            self.end_headers()
            return
        body = 配るもの["body"].encode("utf-8")
        self.send_header("Content-Type", 配るもの["type"])
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass          # 検査の出力を汚さない


class 配信を見る(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), _手)
        cls.port = cls.srv.server_address[1]
        cls.th = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.th.start()
        # **プロキシを通さない。** 通すと外向きの決まりに当たって、
        # 何を確かめているのか分からない落ち方をする
        cls.keep = {}
        for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
            cls.keep[k] = os.environ.pop(k, None)
        os.environ["NO_PROXY"] = "127.0.0.1,localhost"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()      # 閉じないと ResourceWarning が出る
        for k, v in cls.keep.items():
            if v is not None:
                os.environ[k] = v

    def setUp(self):
        del 見たUA[:]
        配るもの.update({"code": 200, "body": "{}",
                          "type": "application/json"})

    def 見る(self, **配る):
        配るもの.update(配る)
        out = io.StringIO()
        keep = sys.stdout
        sys.stdout = out
        try:
            code = check_haishin.見る("http://127.0.0.1:%d/" % self.port)
        finally:
            sys.stdout = keep
        return code, out.getvalue()

    def test_個票がからっぽなら通る(self):
        code, 文 = self.見る(body=json.dumps(
            {"records": [], "counts_by_city": [1, 2, 3],
             "generated_at": "2026-09-19"}))
        self.assertEqual(code, 0, 文)
        self.assertIn("市区町村 3", 文)

    def test_個票が入っていたら止める(self):
        """**いちばん出してはいけないもの**（正本 1節）。"""
        code, 文 = self.見る(body=json.dumps(
            {"records": [{"a": 1}, {"a": 2}], "counts_by_city": []}))
        self.assertEqual(code, 1)
        self.assertIn("個票が 2 件", 文)

    def test_recordsという欄が無ければ止める(self):
        """**空なのか、欄ごと無いのかは別**。決めつけない。"""
        code, 文 = self.見る(body=json.dumps({"counts_by_city": []}))
        self.assertEqual(code, 1)
        self.assertIn("records が無い", 文)

    def test_JSONでなければ止める(self):
        """Pages が404ページを配っていると、ここに来る。"""
        code, 文 = self.見る(body="<html>404</html>", type="text/html")
        self.assertEqual(code, 1)
        self.assertIn("JSON", 文)

    def test_404なら止める(self):
        code, 文 = self.見る(code=404, body="")
        self.assertEqual(code, 1)
        self.assertIn("404", 文)

    def test_リダイレクトを追わない(self):
        """**追うと、飛ばされる側を入口にしても緑になる。**

        www と本体はどちらか一方だけを GitHub が主張し、もう片方は 301。
        追ってしまうと index.json に入るURLが全部リダイレクトのまま、
        誰も気づけない。**追わないことが、正しいほうを入れる強制になる。**

        **飛ばし先は200で通る中身にしてある。**
        追えば通り、追わなければ止まる。だからこの1本で見分けられる。
        """
        code, 文 = self.見る(code=301,
                             body="http://127.0.0.1:%d/tobisaki.json"
                                  % self.port)
        self.assertEqual(code, 1, 文)
        self.assertIn("301", 文)
        self.assertNotIn("からっぽ", 文)   # 追っていたらこれが出る

    def test_名乗って取りに行く(self):
        """正本 3.4「UA に連絡先の URL を入れる」。自分のサイトでも名乗る。"""
        self.見る(body=json.dumps({"records": [], "counts_by_city": []}))
        self.assertTrue(見たUA)
        self.assertEqual(見たUA[0], site.user_agent())
        self.assertIn(site.contact_url(), 見たUA[0])


class 入口が空の日(unittest.TestCase):
    """**鳴らない見張りにしない**（正本 3.3）。

    ⑤ Pages がまだなら配信は無い。毎朝赤にすると、
    鳴らなくなるのではなく**見られなくなる**。
    """

    def test_空なら見に行かずに通る(self):
        out = io.StringIO()
        keep, keepsite = sys.stdout, dict(site.SITE)
        keepenv = os.environ.pop("SITE_URL", None)
        sys.stdout = out
        try:
            site.SITE["site_url"] = ""
            code = check_haishin.main(["check_haishin.py"])
        finally:
            sys.stdout = keep
            site.SITE.clear()
            site.SITE.update(keepsite)
            if keepenv is not None:
                os.environ["SITE_URL"] = keepenv
        self.assertEqual(code, 0)
        self.assertIn("まだ空", out.getvalue())

    def test_引数で渡せる(self):
        """**site_url に入れる前に確かめられること。**

        確かめてから入れるのが順番。site.json に入れないと確かめられない
        作りにすると、順番が逆になる。
        """
        import inspect
        src = inspect.getsource(check_haishin.main)
        self.assertIn("argv[1]", src)


if __name__ == "__main__":
    unittest.main()
