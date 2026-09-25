#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""門（common/kado.py）を回り込む道が無いことを見張る（構造の見張り）。

正本「門のつなぎ込み — 共通の指示書」3節。**名前の一覧で作らない**
（足した日に黙るので）。置き場の木を全部歩いて `.py` を機械的に集め、
中身を見る。

    歩く場所      `.git` `__pycache__` `node_modules` は、どの深さでも除く。
                  `tests/` `data/` `inbox/` `_raw/` は**置き場の根の直下だけ**
                  除く（生データ・検査の中の偽物までは覗かない。深いところに
                  同じ名前のフォルダがあっても、それは除かない）
    回り込む道具  `urllib.request.build_opener` `http.client` `HTTPSConnection`
                  `HTTPConnection` `requests` `urllib3` `socket.create_connection`
                  `urlopen(…, context=…)` `cafile=` が出た行を落とす
                  （その行に `# kado-soto` があれば許す）
    urlopen 系    `urlopen(` か `urllib.request` を使うなら、`common/kado.py` を
                  import していること（直接でも、`common` 配下の別モジュール
                  経由でもよい。経由のときは、経由先が kado を import して
                  いることも確かめる）。**例外**: 該当する行が全部
                  `# kado-soto` なら許す（`scripts/check_haishin.py` が
                  自分のサイトの配信を確かめるためだけに、kado を import せず
                  urllib.request を使っている。取得先ではない）

`common/kado.py` 自身は、上のどちらの検査からも除く（回り込む道具の側は
指示書に明記、urlopen 側は「自分で自分を import している」という無意味な
要求になるので、門の本体として同じ扱いにしてある）。

    python3 -m unittest discover -s tests
"""
import os
import re
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# .git・__pycache__・node_modules は、どの深さでも除く
ZENSHIN_JOGAI = {".git", "__pycache__", "node_modules"}
# tests・data・inbox・_raw は、**置き場の根の直下だけ**除く
UE_NO_KAI_JOGAI = {"tests", "data", "inbox", "_raw"}

KADO_HONTAI = "common/kado.py"

# 門を回り込める道具。**この語が出た行**を落とす（kado-soto があれば許す）。
# 正本「門のつなぎ込み」3節の一覧そのまま
MAWARIKOMU = (
    "build_opener", "http.client", "HTTPSConnection", "HTTPConnection",
    "requests", "urllib3", "socket.create_connection", "cafile=",
)
KADO_SOTO = "# kado-soto"

_KADO_IMPORT = re.compile(
    r"^\s*(from\s+common(\.kado)?\s+import\s+[^\n#]*\bkado\b"
    r"|import\s+common\.kado\b)", re.M)


def py_files(root=ROOT):
    """置き場の木を全部歩いて `.py` を集める。docstring のとおりに除く。"""
    out = []
    for cur, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in ZENSHIN_JOGAI]
        if os.path.abspath(cur) == os.path.abspath(root):
            dirs[:] = [d for d in dirs if d not in UE_NO_KAI_JOGAI]
        for f in files:
            if f.endswith(".py"):
                out.append(os.path.join(cur, f))
    return sorted(out)


def _yomu(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _rel(path, root):
    return os.path.relpath(path, root).replace(os.sep, "/")


def mawarikomu_ihan(text):
    """回り込む道具が、`# kado-soto` の印なしで出ている行。空なら問題なし。"""
    out = []
    for i, line in enumerate(text.splitlines(), 1):
        if KADO_SOTO in line:
            continue
        if any(w in line for w in MAWARIKOMU):
            out.append((i, line.strip()))
        elif "urlopen(" in line and "context=" in line:
            out.append((i, line.strip()))
    return out


def urlopen_koho(text):
    """`urlopen(` か `urllib.request` を使っている行。"""
    return [(i, line) for i, line in enumerate(text.splitlines(), 1)
            if "urlopen(" in line or "urllib.request" in line]


def _kado_wo_chokusetsu_import(text):
    return bool(_KADO_IMPORT.search(text))


def _keiyu_de_kado(text, root):
    """`common` 配下の別モジュール経由で kado を import しているか（1段だけ辿る）。"""
    names = set()
    for m in re.finditer(r"^\s*from\s+common\s+import\s+([^\n#]+)", text, re.M):
        for n in m.group(1).split(","):
            n = n.strip().split(" as ")[0].strip()
            if n:
                names.add(n)
    for m in re.finditer(r"^\s*import\s+common\.(\w+)\b", text, re.M):
        names.add(m.group(1))
    for n in names:
        if n == "kado":
            return True
        sub = os.path.join(root, "common", n + ".py")
        if os.path.isfile(sub) and _kado_wo_chokusetsu_import(_yomu(sub)):
            return True
    return False


def kouzou_ihan(root=ROOT):
    """この置き場の `.py` 全部を見て、違反の一覧を返す（空なら問題なし）。

    戻り値は `(違反の一覧, 見た.pyの一覧)`。
    """
    files = py_files(root)
    bad = []
    if not files:
        return ["見た .py の数が0（数え方が壊れている）"], files
    for path in files:
        rel = _rel(path, root)
        if rel == KADO_HONTAI:
            continue  # 門そのもの
        text = _yomu(path)

        for i, line in mawarikomu_ihan(text):
            bad.append("%s:%d が回り込む道具を使っている（kado-soto の印が無い）: %s"
                       % (rel, i, line))

        uk = urlopen_koho(text)
        if not uk:
            continue
        if _kado_wo_chokusetsu_import(text) or _keiyu_de_kado(text, root):
            continue
        if all(KADO_SOTO in line for _, line in uk):
            continue  # 例外：該当行が全部 kado-soto なら許す
        bad.append(
            "%s が urlopen()／urllib.request を使っているのに "
            "common/kado.py を import していない（kado-soto の印もそろっていない）" % rel)
    return bad, files


def _oku(d, rel, text):
    path = os.path.join(d, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def _monoki(d):
    """検査用の小さな木。`common/kado.py`（中身は空でよい。門そのものとして除く対象）だけ置く。"""
    _oku(d, "common/__init__.py", "")
    _oku(d, "common/kado.py", "# 門そのもの（この検査では中身を見ない）\n")


class 回り込む道具(unittest.TestCase):
    """置いてあるものを名前ではなく中身で見る。"""

    def test_本物の置き場に回り込む道が無い(self):
        bad, files = kouzou_ihan()
        self.assertGreater(len(files), 0,
                           "見た .py の数が0（数え方が壊れている）")
        self.assertEqual(bad, [], "\n" + "\n".join(bad))

    def test_壊すと落ちる_build_opener(self):
        """**壊して鳴ることを確かめる。** 印の無い build_opener を置くと落ちること。
        本物の置き場は汚さない（一時フォルダに小さな木を作る）。
        """
        with tempfile.TemporaryDirectory() as d:
            _monoki(d)
            _oku(d, "yabure.py",
                "import urllib.request\n"
                "opener = urllib.request.build_opener()\n")
            bad, files = kouzou_ihan(d)
            self.assertTrue(files)
            self.assertTrue(bad, "build_opener を置いたのに落ちなかった")

    def test_壊すと落ちる_kadoのimportを消す(self):
        """**壊して鳴ることを確かめる。** kado を import せずに urlopen() を
        使うと落ちること。
        """
        with tempfile.TemporaryDirectory() as d:
            _monoki(d)
            _oku(d, "toru.py",
                "import urllib.request\n"
                "urllib.request.urlopen('http://example.invalid')\n")
            bad, files = kouzou_ihan(d)
            self.assertTrue(bad, "kado を import せずに urlopen() を使ったのに落ちなかった")

    def test_kado_sotoの印があれば通る(self):
        """`scripts/check_haishin.py` と同じ形。kado を import しなくても、
        該当行が全部 `# kado-soto` なら通る。
        """
        with tempfile.TemporaryDirectory() as d:
            _monoki(d)
            _oku(d, "jibun.py",
                "import urllib.request  # kado-soto: 自分のサイトを見る\n"
                "urllib.request.urlopen('http://example.invalid')  "
                "# kado-soto: 自分のサイトを見る\n")
            bad, files = kouzou_ihan(d)
            self.assertEqual(bad, [], bad)

    def test_一部だけkado_sotoでは通らない(self):
        """**該当行が全部そろっていないと許さない。** 1行だけ印を忘れたら落ちる。"""
        with tempfile.TemporaryDirectory() as d:
            _monoki(d)
            _oku(d, "hanbun.py",
                "import urllib.request  # kado-soto: 自分のサイトを見る\n"
                "urllib.request.urlopen('http://example.invalid')\n")
            bad, files = kouzou_ihan(d)
            self.assertTrue(bad, "印が足りない行があるのに通ってしまった")

    def test_kadoを直接importしていれば通る(self):
        with tempfile.TemporaryDirectory() as d:
            _monoki(d)
            _oku(d, "toru.py",
                "from common import kado\n"
                "import urllib.request\n"
                "urllib.request.urlopen('http://example.invalid')\n")
            bad, files = kouzou_ihan(d)
            self.assertEqual(bad, [], bad)

    def test_経由でも通る(self):
        """`common` 配下の別モジュール（`torikata` 相当）が kado を import して
        いれば、それを import しているだけのファイルも通る。
        """
        with tempfile.TemporaryDirectory() as d:
            _monoki(d)
            _oku(d, "common/keiyu.py", "from common import kado\n")
            _oku(d, "toru.py",
                "from common import keiyu\n"
                "import urllib.request\n"
                "urllib.request.urlopen('http://example.invalid')\n")
            bad, files = kouzou_ihan(d)
            self.assertEqual(bad, [], bad)

    def test_経由先がkadoをimportしていなければ通らない(self):
        with tempfile.TemporaryDirectory() as d:
            _monoki(d)
            _oku(d, "common/keiyu.py", "# kado を import していない\n")
            _oku(d, "toru.py",
                "from common import keiyu\n"
                "import urllib.request\n"
                "urllib.request.urlopen('http://example.invalid')\n")
            bad, files = kouzou_ihan(d)
            self.assertTrue(bad, "経由先が kado を import していないのに通ってしまった")

    def test_kado本体はどちらの検査からも除く(self):
        with tempfile.TemporaryDirectory() as d:
            _monoki(d)
            # common/kado.py の中身を、回り込む道具そのもの（門の実装）にする
            _oku(d, "common/kado.py",
                "import urllib.request\n"
                "urllib.request.build_opener()\n"
                "urllib.request.urlopen('http://example.invalid')\n")
            bad, files = kouzou_ihan(d)
            self.assertEqual(bad, [], bad)

    def test_上の階だけ除く(self):
        """`tests` `data` `inbox` `_raw` は根の直下だけ除く。
        深いところの同じ名前は除かない。
        """
        with tempfile.TemporaryDirectory() as d:
            _monoki(d)
            _oku(d, "tests/yabure.py",
                "import urllib.request\n"
                "urllib.request.build_opener()\n")
            _oku(d, "scripts/data/yabure.py",
                "import urllib.request\n"
                "urllib.request.build_opener()\n")
            bad, files = kouzou_ihan(d)
            rels = [_rel(p, d) for p in files]
            self.assertNotIn("tests/yabure.py", rels,
                             "根の直下の tests/ を除いていない")
            self.assertIn("scripts/data/yabure.py", rels,
                          "深いところの data/ まで除いている")

    def test_gitや__pycache__はどの深さでも除く(self):
        with tempfile.TemporaryDirectory() as d:
            _monoki(d)
            _oku(d, "a/__pycache__/x.py", "import urllib.request\n")
            _oku(d, ".git/hooks/x.py", "import urllib.request\n")
            bad, files = kouzou_ihan(d)
            rels = [_rel(p, d) for p in files]
            self.assertEqual(
                [r for r in rels if "__pycache__" in r or r.startswith(".git")],
                [])


if __name__ == "__main__":
    unittest.main()
