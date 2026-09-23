#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DESIGN_HISTORY.md は履歴。今の決まりの根拠にしない。

DESIGN.md から、過去の経緯だけの節を移した先。**履歴の文は当時のまま**なので、
今は使わない言い方・やめた案・当時の引用が残っている。
だから、今の決まりの語を見張る検査には入れない。かわりに、次を見る。

- 冒頭に「履歴であり、今の仕様の根拠ではない」と書いてある
- DESIGN.md の「DESIGN_HISTORY.md の『…』へ移した」の案内が、履歴に実在する見出しを指している
- 案内のすぐ上の DESIGN.md の見出しも同じ名前（番号と見出しは DESIGN.md に残してある）
- 本番のコード・workflow・README・sources.json などが、履歴ファイルを根拠として引いていない
  （DESIGN.md からの案内と、この tests は許す）

    python3 -m unittest discover -s tests
"""

import io
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HIST = os.path.join(ROOT, "DESIGN_HISTORY.md")
DESIGN = os.path.join(ROOT, "DESIGN.md")
案内 = re.compile(r"この項目の過去経緯は DESIGN_HISTORY\.md の「(.+?)」へ移した。")


def 読む(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def 見出しの名前(本文):
    return [re.sub(r"^#{1,6} ", "", l) for l in 本文.splitlines()
            if re.match(r"^#{1,6} ", l)]


class 履歴ファイル(unittest.TestCase):

    def test_冒頭に履歴で根拠ではないと書いてある(self):
        頭 = "\n".join(読む(HIST).splitlines()[:8])
        self.assertIn("これは設計・移行の履歴", 頭)
        self.assertIn("このファイルを、現在の仕様の根拠として使わない", 頭)
        self.assertIn("DESIGN.md", 頭)

    def test_案内が指す見出しが履歴にある(self):
        先 = 案内.findall(読む(DESIGN))
        self.assertTrue(先, "DESIGN.md に、履歴への案内が1つも無い")
        ある = set(見出しの名前(読む(HIST)))
        無い = [t for t in 先 if t not in ある]
        self.assertEqual(無い, [],
                         "DESIGN.md の案内が、履歴に無い見出しを指している")

    def test_案内のすぐ上に同じ見出しが残っている(self):
        """**番号と見出しは DESIGN.md に残す。** 移したのは本文だけ。

        コード・README・sources.json は、章や項目の番号で DESIGN を引く。
        見出しごと移すと、番号の行き先が消える。
        """
        行 = 読む(DESIGN).splitlines()
        for i, l in enumerate(行):
            m = 案内.search(l)
            if not m:
                continue
            上 = [x for x in 行[:i] if x.strip()][-1]
            self.assertEqual(re.sub(r"^#{1,6} ", "", 上), m.group(1),
                             "案内の上の見出しが、案内の指す名前と違う: %s" % 上)

    def test_本番のものが履歴を根拠にしていない(self):
        """**履歴を根拠にしない。** 名前が出たら鳴る。

        木を全部歩く。見ないものには理由を書く：
        tests（この検査が名前を持つ）・data と inbox と _raw（毎朝の実行で金庫につながる）・
        .git と __pycache__（機械が作るもの）。文字でないファイルは読めないので見ない。
        DESIGN.md は案内を置く所なので見ない。履歴ファイル自身も見ない。
        """
        上だけ見ない = {"tests", "data", "inbox", "_raw"}
        どこでも見ない = {".git", "__pycache__"}
        自分 = {"DESIGN.md", "DESIGN_HISTORY.md"}
        bad = []
        for cur, dirs, files in os.walk(ROOT):
            rel_dir = os.path.relpath(cur, ROOT).replace(os.sep, "/")
            dirs[:] = [d for d in dirs
                       if d not in どこでも見ない
                       and not (rel_dir == "." and d in 上だけ見ない)]
            for name in files:
                if rel_dir == "." and name in 自分:
                    continue
                path = os.path.join(cur, name)
                try:
                    with io.open(path, encoding="utf-8") as f:
                        text = f.read()
                except (UnicodeDecodeError, OSError):
                    continue
                if "DESIGN_HISTORY" in text:
                    bad.append(os.path.relpath(path, ROOT))
        self.assertEqual(bad, [],
                         "履歴ファイルを引いている。今の決まりの根拠は DESIGN.md")


if __name__ == "__main__":
    unittest.main()
