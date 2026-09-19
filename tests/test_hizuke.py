#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""走った日は、1回だけ決める（正本 3.5）。

**時刻ではなく、値を1回に決める。**

時間帯を日本時間に寄せるだけでは足りない。それは「たまたま日付をまたがない」
だけで、走る時刻が動けばまた起きる。

このサイトの実物（2026-09-19 に確かめた）。

    22:30 UTC  走り始める（＝日本時間の翌日 07:30）
    00:32 UTC  commit する（2時間かかる）

commit の時刻に `date -u` を打つと 09-19 が出て、**たまたま合っていた**。
取りに行くのに2時間かかって UTC の日付をまたぐから。
**速くなった日に、黙って1日戻る。**

姉妹サイト（大型店日報）は同じ形で、**取得日が毎日1日早く出ていた**。

**workflow 側の検査は `tests/test_workflow.py` に置いてある。**
ここに置くと、workflow を持たない木（公開用）で
**glob が空になり、検査が黙って通る**（2026-09-19 に気づいた）。
見張りは、見張る相手と同じ木に置く。

    python3 -m unittest discover -s tests
"""

import io
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 時計を直に見る書き方
CLOCK = re.compile(r"datetime\.now|date\.today|time\.time\(|utcnow")

# 時計を見てよいのはここだけ
ONLY = "common/jst.py"


def py_files():
    for cur, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs
                   if d not in (".git", "__pycache__", "data", "inbox")]
        for name in sorted(files):
            if not name.endswith(".py"):
                continue
            rel = os.path.relpath(os.path.join(cur, name), ROOT)
            yield rel.replace(os.sep, "/"), os.path.join(cur, name)


class 時計を見るのは1か所(unittest.TestCase):

    def test_jst以外が時計を見ていない(self):
        """**見る場所が増えると、1回の実行の中で日付が食い違う。**"""
        bad = []
        for rel, path in py_files():
            if rel == ONLY or rel.startswith("tests/"):
                continue
            with io.open(path, encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    if line.lstrip().startswith("#"):
                        continue
                    if CLOCK.search(line):
                        bad.append("%s:%d %s" % (rel, i, line.strip()[:60]))
        self.assertEqual(bad, [],
                         "時計を直に見ている。common/jst.py の today() を使うこと:\n"
                         + "\n".join(bad))

class 渡された日を使う(unittest.TestCase):

    def setUp(self):
        self.keep = os.environ.get("RUN_DATE")

    def tearDown(self):
        if self.keep is None:
            os.environ.pop("RUN_DATE", None)
        else:
            os.environ["RUN_DATE"] = self.keep

    def test_渡されればそれを使う(self):
        from common import jst
        os.environ["RUN_DATE"] = "2026-09-18"
        self.assertEqual(jst.today_str(), "2026-09-18")

    def test_無ければ日本時間の今日(self):
        from common import jst
        os.environ.pop("RUN_DATE", None)
        self.assertEqual(jst.today_str(), jst.now().date().isoformat())

    def test_読めなければ落とす(self):
        """**黙って今日に倒さない。**

        渡したつもりで渡せていないことに、気づけなくなる。
        """
        from common import jst
        for bad in ("きのう", "2026/09/18", "20260918", "2026-13-99"):
            os.environ["RUN_DATE"] = bad
            with self.assertRaises(RuntimeError, msg=bad):
                jst.today_str()


if __name__ == "__main__":
    unittest.main()
