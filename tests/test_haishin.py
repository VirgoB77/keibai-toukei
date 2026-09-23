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
# 入口（`/`）が配るもの。**配っているファイルとは別の道**
入口 = {"code": 200, "body": "<html><body>競売・公売の統計</body></html>",
        "type": "text/html; charset=utf-8"}
見たUA = []


class _手(BaseHTTPRequestHandler):

    def do_GET(self):
        見たUA.append(self.headers.get("User-Agent") or "")
        # **飛ばし先は必ず通る中身にしておく。**
        # 飛ばし先も止まる形にすると、追っても追わなくても止まるので、
        # 「追わないこと」を確かめたことにならない（検査が空回りする）
        if self.path == "/":
            body = 入口["body"].encode("utf-8")
            self.send_response(入口["code"])
            if 入口["code"] in (301, 302, 307, 308):
                self.send_header("Location", "http://example.test/")
                self.end_headers()
                return
            self.send_header("Content-Type", 入口["type"])
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
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
        入口.update({"code": 200,
                      "body": "<html><body>競売・公売の統計</body></html>",
                      "type": "text/html; charset=utf-8"})

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
            {"records": [], "counts_by_city": [
                {"city_code": "27106"}, {"city_code": "27107"},
                {"city_code": "27108"}],
             "generated_at": "2026-09-19"}))
        self.assertEqual(code, 0, 文)
        self.assertIn("升 3", 文)
        self.assertIn("市区町村 3", 文)

    def test_升を市区町村と名乗らない(self):
        """**升と市区町村は別の数**（正本 6節）。

        升は city_code × kind × period。1つの市が種別と月の数だけ
        升に分かれるから、升を数えて「市区町村」と名乗ると多く出る。

        実測（2026-09-20）: 配っている 92 升を「市区町村 92」と
        名乗っていた。本当の市区町村は 46。**報告に出す数が外れていた。**
        前の検査は `counts_by_city` に数字を3つ並べて「市区町村 3」を
        確かめていたので、**名乗りのほうを固定していた**。

        ここは同じ市の升を2つ渡す。畳んでいなければ 1 にならない。
        """
        code, 文 = self.見る(body=json.dumps(
            {"records": [],
             "counts_by_city": [
                 {"city_code": "27106", "kind": "競売/公告-初出"},
                 {"city_code": "27106", "kind": "競売/公告-再出"}],
             "generated_at": "2026-09-19"}))
        self.assertEqual(code, 0, 文)
        self.assertIn("升 2", 文)
        self.assertIn("市区町村 1", 文)

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


class 人が来る1枚を見る(unittest.TestCase):
    """**ドメインを付けた日から、そのドメインは404を返す**（2026-09-19）。

    ドメインを付けるのと、人が見るページを作るのは別の作業。
    実際にそうなった。`data/index.json` は配信できていたのに、
    `.html` が1枚も無く（`.nojekyll` があるので Markdown も描かれない）、
    **来た人は全員404を見ていた。**

    配っているファイルだけを見る検査は、それを1つも捕まえない。
    **別の問いなので、別に見る。**
    """

    @classmethod
    def setUpClass(cls):
        配信を見る.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        配信を見る.tearDownClass.__func__(cls)

    def setUp(self):
        del 見たUA[:]
        配るもの.update({"code": 200,
                          "body": json.dumps({"records": [],
                                              "counts_by_city": []}),
                          "type": "application/json"})
        入口.update({"code": 200,
                      "body": "<html><body>競売・公売の統計</body></html>",
                      "type": "text/html; charset=utf-8"})

    def 走らせる(self):
        out = io.StringIO()
        keep = sys.stdout
        sys.stdout = out
        try:
            code = check_haishin.main(
                ["check_haishin.py", "http://127.0.0.1:%d/" % self.port])
        finally:
            sys.stdout = keep
        return code, out.getvalue()

    def test_入口もファイルも通れば通る(self):
        code, 文 = self.走らせる()
        self.assertEqual(code, 0, 文)
        self.assertIn("入口", 文)
        self.assertIn("からっぽ", 文)

    def test_入口が404なら止める(self):
        """**これが 2026-09-19 に起きた形。**"""
        入口.update({"code": 404, "body": "", "type": "text/html"})
        code, 文 = self.走らせる()
        self.assertEqual(code, 1)
        # **何と言うかまで縛る。** 7時半に読む人が、どこを直せばよいか分かる文
        # （「HTMLではない」と言われると、別の場所を探しに行く）
        self.assertIn("来た人はこれを見る", 文)
        self.assertIn("404", 文)
        self.assertNotIn("からっぽ", 文,
                         "入口が落ちているのに、ファイルの話まで進んでいる")

    def test_入口がHTMLでなければ止める(self):
        入口.update({"code": 200, "body": "{}", "type": "application/json"})
        code, 文 = self.走らせる()
        self.assertEqual(code, 1)
        self.assertIn("HTML ではない", 文)

    def test_入口が飛ばしたら止める(self):
        入口.update({"code": 301, "body": "", "type": "text/html"})
        code, 文 = self.走らせる()
        self.assertEqual(code, 1)
        self.assertIn("301", 文)

    def test_入口が通ってもファイルが落ちていれば止める(self):
        """**片方だけ通っても足りない。**"""
        配るもの.update({"body": json.dumps({"records": [{"a": 1}],
                                              "counts_by_city": []})})
        code, 文 = self.走らせる()
        self.assertEqual(code, 1)
        self.assertIn("個票が 1 件", 文)


if __name__ == "__main__":
    unittest.main()
