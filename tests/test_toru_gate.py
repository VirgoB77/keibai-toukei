#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""取りに行ってよいかの関所を2つ固定する。**2026-09-25 からの形。**

鯨屋DBの固定線：**迷ったら止まる。robots で断られたら取らない。未確認を許可扱いしない。**

    カードの関所   common/kado.py の Kado.card_mon() / K.sesshon()
                   カード（data/ref/torimoto-card.json）＋運営者承認から
                   導いた正式状態が「取ってよい」の収集先だけが通る
    robots の関所  同じく common/kado.py の Kado.robots_kekka()（K.sesshon() の中）
                   読めて Allow か、404 / 410 だけ通す

前はどちらも「sources.json の4語（torikata）」と「recon.py 自身の
robots.txt 取得処理」だけで決まっていた。**その中身の検査は
tests/test_kado.py へ移した**（common/kado.py が1か所で持つように
なったため。あちらは書き換えない約束のファイル）。

ここで recon.py 側として固定するのは2つ。

    1. `recon_one()` が実際にカードの門（`K.card_mon()`/`with K.sesshon():`）
       を通っているか（`torikata.py` を見るだけの古い形に戻っていないか）
    2. カード・承認・robots・URL範囲がそろった収集先は、**本物の Kado ＋
       偽の相手（Nise）を通して**、本文まで実際に取れるか（recon.py の
       `fetch()` / `check_robots()` が「セッションの中でだけ通る」門の
       配線に正しく乗っているか）

**外へは1本も出ない**（Nise が受ける。socket も塞いである）。

    python3 -m unittest discover -s tests
"""

import os
import socket
import sys
import unittest
import urllib.request
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import recon  # noqa: E402
import nise_kado  # noqa: E402
from common import kado  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOW = "User-agent: *\nAllow: /\n"
DISALLOW = "User-agent: *\nDisallow: /\n"
# nise_kado.card() の既定の 対象host／対象URL／承認する取得方法.URL範囲 と同じ
HOST = "example.invalid"
URL = "https://%s/data/list.html" % HOST
ROBOTS_URL = "https://%s/robots.txt" % HOST


def 外へ出た(*a, **k):
    raise AssertionError("外へ出ていこうとした（テストでは通信しない）")


class 関所(unittest.TestCase):
    """カード1枚（`nise_kado.Kumitate`）を据えて `recon_one()` に渡す。"""

    def setUp(self):
        self.k = nise_kado.Kumitate(cid="shiken")
        self.addCleanup(self.k.close)
        self.keep_genzai = kado.genzai()
        self.addCleanup(self._modosu)
        for p in (mock.patch("socket.create_connection", 外へ出た),
                  mock.patch.object(socket.socket, "connect", 外へ出た),
                  mock.patch.object(recon, "WAIT", 0),
                  mock.patch.object(recon, "_BUSY_HOSTS", set()),
                  mock.patch.object(recon.time, "sleep", lambda _n: None)):
            p.start()
            self.addCleanup(p.stop)

    def _modosu(self):
        kado._KADO = self.keep_genzai
        urllib.request.install_opener(None)

    def 通す(self, cid, kumitate=None, kotae=None, **src_kw):
        """カード `cid`（`kumitate`。既定は `self.k`）を据えて、
        本物の `Kado` ＋偽の相手（`Nise`）で `recon_one()` に渡す。
        """
        kumitate = kumitate or self.k
        既定 = {ROBOTS_URL: (200, {"Content-Type": "text/plain"}, ALLOW.encode("utf-8")),
               URL: (200, {"Content-Type": "text/html"}, b"<html>ok</html>")}
        nise = nise_kado.Nise(既定 if kotae is None else kotae)
        K = kumitate.kado(transport=nise)
        K.install()
        src = {"id": cid, "name": "試験", "system": "kobai",
               "kind": "kobai-list", "url": URL}
        src.update(src_kw)
        res = recon.recon_one(src, "2026-10-01",
                              os.path.join(kumitate.kinko, "raw"), {},
                              {"bit_pdf": 0, "santen_links": 0})
        return res, nise


class カードの関所(関所):
    """**カード＋運営者承認がそろわなければ、robots すら見に行かない。**"""

    def test_カードが無ければ通らない(self):
        res, nise = self.通す("nai-card")
        self.assertIn("skipped", res)
        self.assertIn("門で止めた", res["skipped"])
        self.assertEqual(nise.kita, [], "カードが無いのに robots.txt を見に行った")

    def test_未承認なら通らない(self):
        k2 = nise_kado.Kumitate(cid="mikakutei", shounin=False)
        self.addCleanup(k2.close)
        res, nise = self.通す("mikakutei", kumitate=k2)
        self.assertIn("skipped", res)
        self.assertIn("門で止めた", res["skipped"])
        self.assertEqual(nise.kita, [])

    def test_取ってはいけないなら通らない(self):
        k2 = nise_kado.Kumitate(cid="dame", 統括判定案="取ってはいけない")
        self.addCleanup(k2.close)
        res, nise = self.通す("dame", kumitate=k2)
        self.assertIn("skipped", res)
        self.assertIn("門で止めた", res["skipped"])
        self.assertEqual(nise.kita, [])

    def test_URL範囲の外は通らない(self):
        """カードの門は通っても、URL ごとの関所（url_mon）で止まる。"""
        res, nise = self.通す(
            "shiken", url="https://%s/himitsu2/x.html" % HOST,
            kotae={ROBOTS_URL: (200, {"Content-Type": "text/plain"},
                                ALLOW.encode("utf-8"))})
        self.assertIn("skipped", res)
        self.assertNotIn("https://%s/himitsu2/x.html" % HOST, nise.kita)

    def test_承認がそろえば本文まで取れる(self):
        res, nise = self.通す("shiken")
        self.assertNotIn("skipped", res)
        self.assertEqual(res.get("status"), 200)
        self.assertEqual(sorted(nise.kita), sorted([ROBOTS_URL, URL]))

    def test_実データで取りに行くのは_取ってよいのカードと承認がそろったものだけ(self):
        """**本物の sources.json ＋本物のカード置き場**（偽物は使わない）。

        いまは運営者の承認が1件も無いので、`recon_one()` は
        全部を「門で止めた」で skip するはず（カードの門が本当に効いている
        ことの、実データでの確かめ）。
        """
        import json
        with open(os.path.join(ROOT, "sources.json"), encoding="utf-8") as f:
            srcs = json.load(f)["sources"]
        keep_genzai = kado.genzai()
        K = kado.hajimeru(ROOT, "keibai-toukei",
                          "kujiraya archive bot (test; https://example.invalid)")
        try:
            for s in srcs:
                if s.get("handoff") or s.get("manual") or not s.get("url"):
                    continue
                riyuu = K.card_mon(s["id"], hozon_saki=os.path.join(
                    self.k.kinko, "raw", s["id"]))
                self.assertTrue(
                    riyuu, "%s が門を通ってしまう（運営者の承認は1件も無いはず）"
                    % s["id"])
        finally:
            kado._KADO = keep_genzai
            urllib.request.install_opener(None)


class robotsの関所(関所):
    """**読めて Allow か、404 / 410 だけ通す。** カードの関所を通った先の話。"""

    def test_Allowは通る(self):
        res, nise = self.通す("shiken")
        self.assertNotIn("skipped", res)

    def test_Disallowは止まる(self):
        res, nise = self.通す("shiken", kotae={
            ROBOTS_URL: (200, {"Content-Type": "text/plain"},
                        DISALLOW.encode("utf-8")),
            URL: (200, {"Content-Type": "text/html"}, b"<html>ok</html>")})
        self.assertEqual(res.get("skipped"), recon.ROBOTS_KYOHI)
        self.assertNotIn(URL, nise.kita)

    def test_404はrobotsが無いとして通る(self):
        # robots.txt を kotae に入れない → Nise の既定は 404
        res, nise = self.通す("shiken", kotae={
            URL: (200, {"Content-Type": "text/html"}, b"<html>ok</html>")})
        self.assertNotIn("skipped", res)
        self.assertIn(URL, nise.kita)

    def test_読めなかったら止まる(self):
        """401・403・5xx は「許可」に変えない（None は取らない）。"""
        for code in (401, 403, 500):
            with self.subTest(code=code):
                res, nise = self.通す("shiken", kotae={
                    ROBOTS_URL: (code, {"Content-Type": "text/plain"},
                                ALLOW.encode("utf-8")),
                    URL: (200, {"Content-Type": "text/html"}, b"<html>ok</html>")})
                self.assertIn("skipped", res)
                self.assertNotIn(URL, nise.kita)

    def test_robotsが混んでいたら止まる(self):
        """429 / 503 は「いまは待って」。押し込まず、その回は取らない。"""
        res, nise = self.通す("shiken", kotae={
            ROBOTS_URL: (503, {"Content-Type": "text/plain"}, b""),
            URL: (200, {"Content-Type": "text/html"}, b"<html>ok</html>")})
        self.assertIn("skipped", res)
        self.assertNotIn(URL, nise.kita)

    def test_本体が混んでいたら止まる(self):
        """robots は通っても、本体側の 429 / 503 はその日そのサーバーへ行かない。"""
        res, nise = self.通す("shiken", kotae={
            ROBOTS_URL: (200, {"Content-Type": "text/plain"},
                        ALLOW.encode("utf-8")),
            URL: (503, {}, b"")})
        self.assertTrue(res.get("back_off"), res)
        self.assertIn(HOST, recon._BUSY_HOSTS)


if __name__ == "__main__":
    unittest.main()
