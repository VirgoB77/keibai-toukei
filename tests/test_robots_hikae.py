#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""robots.txt の控えと日付を、recon.py が門（common/kado.py）へ渡しているか。

前は recon.py の `_get_robots()` が `data/raw/_robots/<host>.txt` に、
**バイトのまま**控えを残していた（役所の robots.txt には Shift_JIS の注記が残っていて、
decode してから保存すると置換文字になって戻せなかった。2026-09-19）。
robots.txt は毎日取り直せるが、**その日に何と書いてあったか**の控えは取り直せない。

2026-09-25、robots.txt を見るのは門の仕事になった。控えも門が残す。
ここでは recon.py が門に**控えの置き場**と**日付**を渡していることを見る。
中身がバイトのまま残ること・金庫の外には書かないことは `tests/test_kado.py`（robotsのバイト）が見る。

日付は common/jst.py（時計を見る1か所）の値を渡す。門は時計を見ない。

    python3 -m unittest tests.test_robots_hikae
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import recon  # noqa: E402
from common import jst  # noqa: E402


class 門に控えの置き場と日付を渡す(unittest.TestCase):

    def test_mainが最初に渡す(self):
        uketotta = {}

        class Tomaru(Exception):
            pass

        def nise(root, repo, ua, **kw):
            uketotta.update(kw, root=root, repo=repo)
            raise Tomaru()          # 門を始めたところで止める。外へは1本も出ない

        moto = recon.kado.hajimeru
        recon.kado.hajimeru = nise
        try:
            with self.assertRaises(Tomaru):
                recon.main()
        finally:
            recon.kado.hajimeru = moto
        self.assertEqual(uketotta["repo"], "keibai-toukei")
        self.assertEqual(uketotta["today"], jst.today_str())
        self.assertEqual(os.path.normpath(uketotta["robots_hikae"]),
                         os.path.normpath(os.path.join(recon.HERE, "data", "raw", "_robots")))


if __name__ == "__main__":
    unittest.main()
