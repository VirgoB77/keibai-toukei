#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""レポートの章が、動かすたびに増えないことを固定する。

`terms.py` も `kibo.py` も自分の章を書き足していた。ふだんは recon.py が
レポートを作り直すので気づかないが、収集先を絞って動かした回に二重になる。

    python3 -m unittest discover -s tests
"""

import io
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common import report  # noqa: E402
from common.report import put_chapter  # noqa: E402


class 章を差し替える(unittest.TestCase):

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.p = os.path.join(self.d, "r.md")
        io.open(self.p, "w", encoding="utf-8").write(
            "# 偵察\n\nほんぶん\n\n---\n\n# あとの章\n\nうしろ\n")

    def 読む(self):
        return io.open(self.p, encoding="utf-8", newline="").read()

    def test_何回動かしても章は1つ(self):
        for _ in range(3):
            put_chapter(self.p, "規約", "ばん")
            put_chapter(self.p, "規模", "きぼ")
        t = self.読む()
        self.assertEqual(t.count("\n# 規約\n"), 1)
        self.assertEqual(t.count("\n# 規模\n"), 1)

    def test_何回動かしても同じ形(self):
        形 = set()
        for _ in range(3):
            put_chapter(self.p, "規約", "ばん")
            形.add(self.読む())
        self.assertEqual(len(形), 1)

    def test_中身が新しくなる(self):
        put_chapter(self.p, "規約", "ふるい")
        put_chapter(self.p, "規約", "あたらしい")
        t = self.読む()
        self.assertIn("あたらしい", t)
        self.assertNotIn("ふるい", t)

    def test_ほかの章を壊さない(self):
        put_chapter(self.p, "規約", "ばん")
        put_chapter(self.p, "規約", "ばん2")
        t = self.読む()
        self.assertIn("# 偵察", t)
        self.assertIn("ほんぶん", t)
        self.assertIn("# あとの章", t)
        self.assertIn("うしろ", t)

    def test_写した行のCRを黙って消さない(self):
        # レポートには一次情報から写した行が入る。中に CR が混ざることがある
        io.open(self.p, "w", encoding="utf-8", newline="").write(
            "# 偵察\n\n  - 例: ダウンロード\r\n\nあと\n")
        put_chapter(self.p, "規約", "ばん")
        self.assertIn("ダウンロード\r\n", self.読む())


class 書き出す側が2人いる(unittest.TestCase):
    """1つの記録に2人以上が書くことがある（正本 9節）。

    `data/parse-unknown.md` は `parse.py`（読めなかった見出し）と
    `aggregate.py`（段階が決まらなかった行）の2人が書く。
    **片方がファイルごと上書きすると、もう片方の章が消える。**
    消えても動くので、走らせても気づけない。実際にそうなっていた（2026-09-19）。

    いちばん上を持つ側は `put_head()`、章を足す側は `put_chapter()`。
    """

    def setUp(self):
        import tempfile
        self.d = tempfile.mkdtemp()
        self.p = os.path.join(self.d, "r.md")

    def read(self):
        return io.open(self.p, encoding="utf-8", newline="").read()

    def test_章を足したあとに頭を書き替えても章が残る(self):
        report.put_head(self.p, "# 頭\n\n本文")
        report.put_chapter(self.p, "章", "中身")
        report.put_head(self.p, "# 頭\n\n書き替えた本文")
        self.assertIn("書き替えた本文", self.read())
        self.assertIn("# 章", self.read())
        self.assertIn("中身", self.read())

    def test_どちらの順でも同じ形になる(self):
        report.put_head(self.p, "# 頭\n\n本文")
        report.put_chapter(self.p, "章", "中身")
        a = self.read()
        os.remove(self.p)
        report.put_chapter(self.p, "章", "中身")
        report.put_head(self.p, "# 頭\n\n本文")
        self.assertEqual(a, self.read(), "走らせる順番で差分が立つ")

    def test_何回走らせても同じ(self):
        for _ in range(3):
            report.put_head(self.p, "# 頭\n\n本文")
            report.put_chapter(self.p, "章", "中身")
        self.assertEqual(self.read().count("# 章"), 1)
        self.assertEqual(self.read().count("# 頭"), 1)

    def test_まっさらなファイルの先頭に区切りを置かない(self):
        report.put_chapter(self.p, "章", "中身")
        self.assertFalse(self.read().lstrip().startswith("---"))


if __name__ == "__main__":
    unittest.main()
