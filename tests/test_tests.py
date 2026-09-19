#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""テストそのものの見張り。**書いた検査が鳴らない、が一番こわい。**

2026-09-19 に実物で踏んだ。`tests/test_aggregate.py` と
`tests/test_privacy.py` の真ん中に

    if __name__ == "__main__":
        unittest.main()

があり、**そのあとにクラスが定義されていた**。

    discover で走らせる        __name__ は tests.test_aggregate なので
                               番人は False。あとのクラスも定義され、走る
    ファイルを直に走らせる      番人が True。**あとのクラスは定義される前に
                               unittest.main() が走り、丸ごと落ちる**

数えた。直に走らせると test_aggregate は 41本のうち 32本、
test_privacy は 59本のうち 44本しか走っていなかった。**合わせて24本が黙っていた。**

落ちないので気づけない。「OK」と出て、走っていない。

    python3 -m unittest discover -s tests
"""

import ast
import io
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def test_files():
    for name in sorted(os.listdir(HERE)):
        if name.startswith("test_") and name.endswith(".py"):
            yield name, os.path.join(HERE, name)


class 番人はいちばん下に置く(unittest.TestCase):

    def test_番人のあとに定義を置かない(self):
        """**`if __name__ == "__main__"` より下に class や def を書かない。**

        書くと、そのファイルを直に走らせたときだけ黙って落ちる。
        """
        bad = []
        for name, path in test_files():
            with io.open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=name)
            guard = None
            for node in tree.body:
                if (isinstance(node, ast.If)
                        and ast.dump(node.test).find("__main__") >= 0):
                    guard = node.lineno
                elif guard is not None and isinstance(
                        node, (ast.ClassDef, ast.FunctionDef)):
                    bad.append("%s:%d %s（番人は %d 行目）"
                               % (name, node.lineno, node.name, guard))
        self.assertEqual(
            bad, [],
            "番人のあとに定義がある。**直に走らせたとき、ここから下が"
            "丸ごと走らない。**落ちないので気づけない:\n" + "\n".join(bad))

    def test_番人はどのファイルにもある(self):
        """無いと、そのファイルだけ直に走らせられない。そろえておく。"""
        bad = []
        for name, path in test_files():
            with io.open(path, encoding="utf-8") as f:
                if "__main__" not in f.read():
                    bad.append(name)
        self.assertEqual(bad, [], "番人が無いファイル")


if __name__ == "__main__":
    unittest.main()
