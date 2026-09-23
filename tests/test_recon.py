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
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import recon  # noqa: E402
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
        # **取得元の欄が要る。** 無いと取りに行かない（きつい側）。
        # ここを入れ忘れて、この検査3本が「1枚も残っていない」で鳴った
        src = {"id": "test-src", "url": "https://example.test/a",
               "name": "試験", "system": "keibai", "torikata": "取ってよい"}
        keep_robots = recon.check_robots
        recon.check_robots = lambda url: (True, "許可", "")
        keep_wait = recon.WAIT
        recon.WAIT = 0
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


class robots_txtもバイトで残す(unittest.TestCase):
    """**役所のサーバーには Shift_JIS が残っている**（2026-09-19）。

    前はここで `decode("utf-8", "replace")` してから保存していた。
    日本語の注記が入った robots.txt は**その場で置換文字になり、
    そのまま保存されていた。戻せない。**

    しかも `Disallow` の行は ASCII なので読み取りは通る。
    **壊れたことに、どこでも気づけない形だった。**

    robots.txt は毎日取り直せるが、**その日に何と書いてあったか**の控えは
    取り直せない。相手が書き換えたら、こちらの控えが唯一の記録になる。
    """

    def 取らせる(self, 生, ctype="text/plain", cenc=""):
        import tempfile
        import urllib.request

        class _返す:
            headers = {"Content-Type": ctype, "Content-Encoding": cenc}

            def read(self, n=None):
                return 生

            def __enter__(self):
                self.headers = type(self).返す見出し()
                return self

            def __exit__(self, *a):
                return False

            @staticmethod
            def 返す見出し():
                class H(dict):
                    def get(self, k, d=""):
                        return dict.get(self, k, d)
                return H({"Content-Type": ctype, "Content-Encoding": cenc})

        d = tempfile.mkdtemp()
        keep = (urllib.request.urlopen, recon.HERE, recon.WAIT,
                dict(recon._ROBOTS_CACHE))
        urllib.request.urlopen = lambda *a, **k: _返す()
        recon.HERE = d
        recon.WAIT = 0
        recon._ROBOTS_CACHE.clear()
        try:
            body, state = recon._get_robots("https", "example.test")
            path = os.path.join(d, "data", "raw", "_robots", "example.test.txt")
            置いた = b""
            if os.path.exists(path):
                with open(path, "rb") as f:
                    置いた = f.read()
            return body, state, 置いた
        finally:
            (urllib.request.urlopen, recon.HERE, recon.WAIT) = keep[:3]
            recon._ROBOTS_CACHE.clear()
            recon._ROBOTS_CACHE.update(keep[3])

    def test_ShiftJISの注記が壊れずに残る(self):
        注記 = "# 競売情報サイト\nUser-agent: *\nDisallow: /app/\n"
        生 = 注記.encode("cp932")
        body, state, 置いた = self.取らせる(生)
        self.assertEqual(state, "ok")
        # **バイトがそのまま入っていること。** ここが本体
        self.assertIn(生, 置いた, "保存したものが生のバイトではない")
        self.assertNotIn("�".encode("utf-8"), 置いた,
                         "保存したものに置換文字が入っている")
        # 読むほうは、文字コードを当てて読めていること
        self.assertIn("競売情報サイト", body)
        self.assertIn("Disallow: /app/", body)

    def test_UTF8のときも今までどおり読める(self):
        生 = "# こんにちは\nUser-agent: *\nAllow: /\n".encode("utf-8")
        body, state, 置いた = self.取らせる(生, ctype="text/plain; charset=utf-8")
        self.assertEqual(state, "ok")
        self.assertIn(生, 置いた)
        self.assertIn("こんにちは", body)

    def test_圧縮されていたら_読めないとして扱う(self):
        """**拒否とは混ぜない。** 読めないのであって、断られたのではない。"""
        import gzip
        生 = gzip.compress(b"User-agent: *\nDisallow: /\n")
        body, state, 置いた = self.取らせる(生, cenc="gzip")
        self.assertIn(生, 置いた, "圧縮でもバイトは残すこと")
        self.assertEqual(body, "")
        self.assertEqual(state, "unknown",
                         "読めなかったものを ok や 拒否 にしない")

    def test_取得日と出どころを頭に控える(self):
        生 = b"User-agent: *\nDisallow: /x/\n"
        _body, _state, 置いた = self.取らせる(生)
        頭 = 置いた.split(生)[0].decode("utf-8")
        self.assertIn("# 取得日:", 頭)
        self.assertIn("https://example.test/robots.txt", 頭)

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

    **真偽を4語に替えるときの罠**も、ここで固定する。
    4語はどれも非空文字列なので、`if not src.get("torikata")` のままだと
    **どの語でも真**になり、「取ってはいけない」にも取りに行く。
    """

    def もと(self, **kw):
        s = {"id": "x", "url": "https://example.test/a", "system": "keibai",
             "torikata": "取ってよい"}
        s.update(kw)
        return s

    def test_取ってはいけないものは取らない(self):
        self.assertFalse(torikata.toru(self.もと(torikata="取ってはいけない")))

    def test_知らない語は取らない(self):
        """**きつい側に倒す。** 綴りが違ったら取りに行かない。"""
        for g in ("取ってよし", "OK", "true", "", None, "とってよい"):
            self.assertFalse(torikata.toru(self.もと(torikata=g)),
                             "知らない語 %r で取りに行っている" % (g,))

    def test_欄が無いものは取らない(self):
        s = self.もと()
        del s["torikata"]
        self.assertFalse(torikata.toru(s))

    def test_取ってよい以外の3語でも取りに行く(self):
        """**取得元の欄は、取得の可否そのものではない。**

        「未確認」「規約未確定」は、**いま取りに行っていることを
        止める語ではない**（robots は見ている）。止めるのは
        「取ってはいけない」だけ。かわりに `kiwadoi()` で数えて出す。
        """
        for g in ("未確認", "規約未確定"):
            self.assertTrue(torikata.toru(self.もと(torikata=g)), g)
            self.assertEqual(len(torikata.kiwadoi([self.もと(torikata=g)])), 1)
        self.assertEqual(torikata.kiwadoi([self.もと()]), [])

    def test_取らない理由は1つの真偽にしない(self):
        """減らす手が違うので、同じ箱に入れない。"""
        self.assertEqual(torikata.naze_toranai(self.もと(handoff="よそ")),
                         torikata.RIYUU_DAIZAI)
        self.assertEqual(torikata.naze_toranai(self.もと(manual=True, url="")),
                         torikata.RIYUU_TEMOCHI)
        self.assertEqual(torikata.naze_toranai(self.もと(url="")),
                         torikata.RIYUU_NAI)
        self.assertEqual(torikata.naze_toranai(self.もと()), "")

    def test_手で保存するものを相手に無いと名乗らない(self):
        """**BIT の一覧・結果・過去・取下げは url が空**。

        GETで再現できないから空にしてある。url から先に見ると
        「相手にその頁が無い」と名乗る（実測 2026-09-21: 4件が誤名乗り）。
        """
        self.assertEqual(
            torikata.naze_toranai(self.もと(manual=True, url="")),
            torikata.RIYUU_TEMOCHI)

    def test_全部の取得元が4語のどれかを持っている(self):
        with io.open(os.path.join(ROOT, "sources.json"), encoding="utf-8") as f:
            src = json.load(f)["sources"]
        for s in src:
            self.assertIn(s.get("torikata"), torikata.GO,
                          "%s に取得元の欄が無い（足した日に黙って取りに行かなくなる）"
                          % s["id"])
            self.assertTrue((s.get("torikata_riyuu") or "").strip(),
                            "%s に取得元の欄の理由が書いていない" % s["id"])

    def test_enabledはもう使わない(self):
        with io.open(os.path.join(ROOT, "sources.json"), encoding="utf-8") as f:
            src = json.load(f)["sources"]
        for s in src:
            self.assertNotIn("enabled", s,
                             "%s に真偽の欄が残っている。"
                             "**4語と真偽を両方持つと、どちらが効くか読めない**"
                             % s["id"])

    def test_題材は取得元が1つ止まっても止まらない(self):
        d = torikata.daizai([self.もと(id="a", system="keibai"),
                             self.もと(id="b", system="keibai",
                                       torikata="取ってはいけない")])
        self.assertEqual(d["keibai"], {"取得元": 2, "通る": 1, "通れる": True})

    def test_題材ぜんぶ止まっていることは見える(self):
        d = torikata.daizai([self.もと(id="a", system="koyu", handoff="よそ")])
        self.assertFalse(d["koyu"]["通れる"])

    def test_実データの題材(self):
        """**4つの題材を全部出す。通れないものも出す。**"""
        with io.open(os.path.join(ROOT, "sources.json"), encoding="utf-8") as f:
            src = json.load(f)["sources"]
        d = torikata.daizai(src)
        self.assertEqual(sorted(d), ["keibai", "kobai", "kokuyu", "koyu"])
        self.assertTrue(d["keibai"]["通れる"])
        self.assertFalse(d["koyu"]["通れる"],
                         "公有財産に通れる取得元ができたなら、"
                         "姉妹サイト送りの取り決めを見直すこと")


class 取る判定はtorikataを通る(unittest.TestCase):
    """**recon.py が真偽の欄に戻ったら鳴る。**

    前の recon.py は `src.get("enabled", True)` で見ていたので、欄が無いものは
    「取る」になる。sources.json から enabled を消したまま、判定だけが前に戻ると、
    「取ってはいけない」の取得元にも robots を見に行く。
    `torikata.py` の検査だけでは、recon.py がそれを使っているかは分からない。
    だから recon_one() そのものに渡して、robots を見る手前で止まるかを見る。
    **外には出ない**（robots を見に行くところを差し替えてある）。
    """

    def 渡す(self, 語):
        import tempfile
        呼んだ = []

        def 見に行った(*a, **k):
            呼んだ.append(a)
            raise RuntimeError("robots を見に行くところまで来た")

        keep = recon.check_robots
        recon.check_robots = 見に行った
        src = {"id": "shiken", "name": "試験", "system": "keibai",
               "kind": "bit-schedule", "url": "https://example.invalid/",
               "torikata": 語, "torikata_riyuu": "試験"}
        try:
            res = recon.recon_one(src, "2026-10-01", tempfile.mkdtemp(), {}, {})
        except RuntimeError:
            res = None
        finally:
            recon.check_robots = keep
        return 呼んだ, res

    def test_取ってはいけない先はrobotsの手前で止まる(self):
        呼んだ, res = self.渡す(torikata.TORANAI)
        self.assertEqual(呼んだ, [],
                         "「取ってはいけない」の取得元に robots を見に行った。"
                         "取る判定が torikata を通っていない")
        self.assertIn(torikata.TORANAI, res["skipped"])

    def test_取ってよい先はrobotsまで行く(self):
        """**材料が見分けられることの確かめ。** 差し替えが効いていなければ、上の1本は何も見ていない。"""
        呼んだ, _ = self.渡す(torikata.GO[0])
        self.assertEqual(len(呼んだ), 1)


if __name__ == "__main__":
    unittest.main()
