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


def py_files():
    """`tests/` の `.py` を全部返す（2026-09-19 に広げた）。

    前は `test_` で始まるものだけを見ていた。`kinko.py` のような
    手伝いのファイルに TestCase を置かれると、**番人の見張りから外れる。**
    「番人のあとに定義を置かない」は、置き場で切らずに全部に掛ける。
    """
    for name in sorted(os.listdir(HERE)):
        if name.endswith(".py") and not name.startswith("_"):
            yield name, os.path.join(HERE, name)


def test_files():
    """**TestCase を持つファイルだけ**返す。

    「番人がある」は、直に走らせる意味があるファイルにだけ求める。
    `kinko.py` は手伝いのモジュールで、直に走らせるものではない。
    **持っているかどうかで決める。名前では決めない**
    （名前で決めると、`kinko.py` に TestCase を置いた日に外れる）。
    """
    for name, path in py_files():
        with io.open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=name)
        if any(_is_testcase(n) for n in ast.walk(tree)):
            yield name, path


def _is_testcase(node):
    """`unittest.TestCase` を継いだクラスか。"""
    if not isinstance(node, ast.ClassDef):
        return False
    for b in node.bases:
        if isinstance(b, ast.Attribute) and b.attr == "TestCase":
            return True
        if isinstance(b, ast.Name) and b.id == "TestCase":
            return True
    return False


class 番人はいちばん下に置く(unittest.TestCase):

    def test_番人のあとに定義を置かない(self):
        """**`if __name__ == "__main__"` より下に class や def を書かない。**

        書くと、そのファイルを直に走らせたときだけ黙って落ちる。
        """
        bad = []
        for name, path in py_files():
            with io.open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=name)
            guard = None
            for node in tree.body:
                if (isinstance(node, ast.If)
                        and ast.dump(node.test).find("__main__") >= 0):
                    guard = node.lineno
                elif guard is not None:
                    # **`if` や `try` でくるんだ定義も拾う**（2026-09-19）。
                    # 前は tree.body の直下しか見ていなかったので、
                    # 番人の後ろに `if True:` で包んだ TestCase を置くと
                    # 21本が20本になっても**緑のまま**だった。
                    # 拾う側が防ぐと宣言している被害そのものを素通りさせていた
                    for sub in ast.walk(node):
                        if isinstance(sub, (ast.ClassDef, ast.FunctionDef,
                                            ast.AsyncFunctionDef)):
                            bad.append("%s:%d %s（番人は %d 行目）"
                                       % (name, sub.lineno, sub.name, guard))
        self.assertEqual(
            bad, [],
            "番人のあとに定義がある。**直に走らせたとき、ここから下が"
            "丸ごと走らない。**落ちないので気づけない:\n" + "\n".join(bad))

    def test_番人はどのファイルにもある(self):
        """無いと、そのファイルだけ直に走らせられない。そろえておく。

        **文字列で探さない**（2026-09-19）。隣の検査は ast で見ているのに、
        こちらだけ `"__main__" in text` だった。コメントに1行書くだけで
        通ってしまい、番人を消しても緑のままだった。
        """
        bad = []
        for name, path in test_files():
            with io.open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=name)
            if not any(isinstance(n, ast.If)
                       and ast.dump(n.test).find("__main__") >= 0
                       for n in tree.body):
                bad.append(name)
        self.assertEqual(bad, [], "番人が無いファイル")

    def test_この見張り自身にも掛かっている(self):
        """**自分のコードを例外にしない**（正本 9節）。

        `test_files()` は `test_` で始まるファイルを全部返すので、
        このファイルも入っている。入っていることを固定しておく。
        """
        self.assertIn("test_tests.py", [n for n, _ in test_files()])
        # 「番人のあとに定義を置かない」は手伝いのファイルにも掛ける
        self.assertIn("kinko.py", [n for n, _ in py_files()],
                      "手伝いのファイルが網から外れている")
        self.assertTrue(list(test_files()), "1本も見ていない")


if __name__ == "__main__":
    unittest.main()
