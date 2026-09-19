#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""金庫では走らない、を見張る（正本 9節）。

収集用（金庫）は置き場で、Actions は公開用が持つ。
移し終われば「金庫に workflow が無い」ので走りようがない。
**それでも1行の保険を入れる。** あとで誰かが merge や copy で
金庫に戻す経路が残るため（姉妹サイトの `*-raw) exit 1`）。

**文字列を grep して確かめたことにしない。**
`"TZ" in text` が `env:` を消しても通ったのと同じ穴があく
（2026-09-19、test_hizuke.py で踏んだ）。
ここは workflow から run: の本文を取り出して、**実際に sh に通す**。

    python3 -m unittest discover -s tests
"""

import glob
import io
import os
import re
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WF = os.path.join(ROOT, ".github", "workflows")

# 自己停止の step の名前。workflow 側を変えたらここも変える
STEP = "金庫では走らないことの確認"

# 移行前の印。**これがあるあいだだけ、金庫でも通る**
MARK = os.path.join(".github", "ikou-mae")


def read(path):
    with io.open(path, encoding="utf-8") as f:
        return f.read()


def write(path, text):
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(text)


def top_env(text):
    """workflow のいちばん上の `env:` を読む。

    **`"TZ" in text` では確かめたことにならない。**
    `env:` を消しても、中身の行は残るので通ってしまう
    （2026-09-19、わざと壊して鳴らないことに気づいた）。
    PyYAML は使わない（標準ライブラリだけで動かす方針）。
    """
    out, inside = {}, False
    for line in text.splitlines():
        if line.rstrip() == "env:":
            inside = True
            continue
        if inside:
            if not line[:1].isspace() or not line.strip():
                if line.strip() and not line[:1].isspace():
                    break
                continue
            if ":" in line:
                k, _, v = line.strip().partition(":")
                out[k.strip()] = v.strip()
    return out


def workflows():
    return sorted(glob.glob(os.path.join(WF, "*.yml")))


def step_body(text, name):
    """`- name: <name>` の run: | の中身を、字下げを外して返す。

    **`name:` と `run:` のあいだに別の欄が来てよい**（2026-09-19）。
    `env:` を挟んだ step で、この関数が None を返して
    **検査が「step が無い」と読み違えた。**
    """
    m = re.search(
        r"- name: %s\n(?: {8}(?!- )[^\n]*\n| {10}[^\n]*\n)*? +run: \|\n"
        r"((?: {10}.*\n|\n)+)" % re.escape(name), text)
    if not m:
        return None
    return "".join(l[10:] if l.startswith(" " * 10) else l
                   for l in m.group(1).splitlines(True))


def run_body(body, repo, mark):
    """本文を sh に通して終了コードを返す。mark は印を置くかどうか。"""
    with tempfile.TemporaryDirectory() as d:
        if mark:
            os.makedirs(os.path.join(d, ".github"))
            write(os.path.join(d, MARK), "移行前。試験用の印。\n")
        script = body.replace("${{ github.repository }}", repo)
        path = os.path.join(d, "step.sh")
        write(path, script)
        p = subprocess.run(["sh", path], cwd=d,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return p.returncode, p.stdout.decode("utf-8", "replace")


class 名前による自己停止(unittest.TestCase):

    def setUp(self):
        self.files = workflows()
        if not self.files:
            self.skipTest(
                "このリポジトリに workflow が無い。"
                "金庫から消したあと・公開用に入れる前は、これが正しい")

    def test_workflow全部が自己停止を持っている(self):
        for path in self.files:
            self.assertIsNotNone(
                step_body(read(path), STEP),
                "%s に「%s」の step が無い。\n"
                "公開用に移したあとも、この1行は入れたままにする（正本 9節）"
                % (os.path.basename(path), STEP))

    def test_印が無ければ金庫で止まる(self):
        """**これが保険の本体。** 移し終わったあとに戻されたら、ここで止まる。"""
        for path in self.files:
            body = step_body(read(path), STEP)
            for repo in ("VirgoB77/keibai-toukei-raw",
                         "VirgoB77/keibai-toukei-raw-2",
                         "VirgoB77/shutten-nippo-raw"):
                rc, out = run_body(body, repo, mark=False)
                self.assertEqual(
                    rc, 1,
                    "%s が %s で止まらなかった:\n%s"
                    % (os.path.basename(path), repo, out))

    def test_公開用では止まらない(self):
        """名前が `-raw` で終わらなければ、印のあるなしによらず通る。"""
        for path in self.files:
            body = step_body(read(path), STEP)
            for mark in (True, False):
                rc, out = run_body(body, "VirgoB77/keibai-toukei", mark)
                self.assertEqual(
                    rc, 0,
                    "%s が公開用で止まった（印=%s）:\n%s"
                    % (os.path.basename(path), mark, out))

    def test_印があるあいだは金庫でも通る(self):
        """**移し終わるまでは、ここが唯一の集め手。**

        止めるとその朝の物件が永久に取れない（BIT は消える）。
        母集団の保存が先（正本 3.5）。

        **印の逃げ道を持つ workflow だけに掛ける**（2026-09-19）。
        公開用の workflow は印を持たない（印は公開用に行かない）。
        そちらは名前だけで止まるのが正しいので、ここでは見ない。
        どちらにも掛かるのは、上の「印が無ければ金庫で止まる」のほう。
        """
        見た = 0
        for path in self.files:
            body = step_body(read(path), STEP)
            if "ikou-mae" not in body:
                # 公開用の workflow。**印を持たないのが正しい**
                rc, out = run_body(body, "VirgoB77/keibai-toukei-raw",
                                   mark=True)
                self.assertEqual(
                    rc, 1,
                    "%s は印を持たないのに、印があると通っている:\n%s"
                    % (os.path.basename(path), out))
                continue
            見た += 1
            rc, out = run_body(body, "VirgoB77/keibai-toukei-raw", mark=True)
            self.assertEqual(rc, 0,
                             "%s が移行前の金庫で止まった:\n%s"
                             % (os.path.basename(path), out))
            self.assertIn("::warning::", out,
                          "通すときに warning が出ていない。"
                          "**印が残っていることが、毎回の記録に見える形で要る**")
        if not 見た:
            self.skipTest("印の逃げ道を持つ workflow が無い。"
                          "移し終わったあとは、これが正しい")


class 走った日は1回だけ決める(unittest.TestCase):
    """**時刻ではなく値を1回に決める**（正本 3.5）。

    もとは `tests/test_hizuke.py` にあった。**あちらに置くと、
    workflow を持たない木で glob が空になり、黙って通る。**
    見張りは、見張る相手と同じ木に置く（2026-09-19 に移した）。
    """

    def setUp(self):
        if not workflows():
            self.skipTest(
                "このリポジトリに workflow が無い。"
                "金庫から消したあと・公開用に入れる前は、これが正しい")

    def test_dateを2回打たない(self):
        """commit のときに時計を打ち直さない。**上で決めた値を使う。**"""
        import glob
        for path in glob.glob(os.path.join(ROOT, ".github", "workflows", "*.yml")):
            with io.open(path, encoding="utf-8") as f:
                text = f.read()
            body = "\n".join(l for l in text.splitlines()
                             if not l.lstrip().startswith("#"))
            n = body.count("date +%F") + body.count("date -u")
            self.assertLessEqual(
                n, 1, "%s が時計を %d 回打っている。"
                      "走り始めに1回決めて $GITHUB_ENV に置くこと"
                      % (os.path.basename(path), n))
            # **時計を1回も見ない workflow には、渡す値が無い**（2026-09-19）。
            # 手で押す配信の確認は日付を記録しないので `RUN_DATE` を持たない。
            # 「持っていること」を全部に求めると、**持つ理由が無いものに
            # 持たせる**ことになり、そのうち意味を見ずに足すようになる。
            # 縛るのは「2回打たない」のほうで、こちらは打つときだけ見る。
            if n:
                self.assertIn(
                    "RUN_DATE", body,
                    "%s が時計を打っているのに、値を渡していない"
                    % os.path.basename(path))
            self.assertEqual(
                top_env(text).get("TZ"), "Asia/Tokyo",
                "%s のいちばん上の env に TZ: Asia/Tokyo が無い。"
                "サーバーは UTC で動いているので、date が前日を出す"
                % os.path.basename(path))


class 移行前の印(unittest.TestCase):

    def test_印があるなら中身に消す日が書いてある(self):
        path = os.path.join(ROOT, MARK)
        if not os.path.exists(path):
            self.skipTest("印が無い。移し終わったあとは、これが正しい")
        text = read(path)
        for word in ("消す日", "手順5"):
            self.assertIn(word, text,
                          "%s に「%s」が無い。"
                          "**いつ消すかが書いていない印は、消えずに残る**"
                          % (MARK, word))


class 検査の入口は1つ(unittest.TestCase):
    """**手で `unittest` を打てるようにしておくと、急いだ日に打つ**（2026-09-19）。

    `scripts/check.sh` が2つやる。

        __pycache__ を消す      `-B` では足りない（もうある .pyc は読む）
        終了コードで見る        後ろにパイプを置かない

    どちらも、やらなかった日に実際に踏んだ。
    """

    SH = os.path.join(ROOT, "scripts", "check.sh")

    def test_workflowはcheck_shを通る(self):
        if not workflows():
            # **空回りで通さない**（2026-09-19）。金庫から workflow を
            # 消した日から、このループは一度も回らなくなった。
            # 回らないのに「通った」と出るのは、鳴らない見張り
            self.skipTest("このリポジトリに workflow が無い。"
                          "控え（scripts/public-workflow.yml）のほうは"
                          "別のクラスが見ている")
        for path in workflows():
            text = read(path)
            body = "\n".join(l for l in text.splitlines()
                              if not l.lstrip().startswith("#"))
            if "unittest" not in body:
                continue
            self.assertIn(
                "scripts/check.sh", body,
                "%s が unittest を直に打っている。**急いだ日に踏む形**"
                % os.path.basename(path))

    def test_check_shがキャッシュを消す(self):
        """**`-B` では足りない。** もうある .pyc はそのまま読まれる。

        公開用の木にも入れる（`make_public_tree.py` の許可リスト）。
        入れ忘れると、公開用では**ここが落ちて**1回も通らない。
        2026-09-19 に入れ忘れて、出す直前の clone で捕まえた。
        """
        self.assertTrue(
            os.path.exists(self.SH),
            "scripts/check.sh が無い。"
            "**公開用の木にも入れること**（許可リストに足す）")
        body = "\n".join(l for l in read(self.SH).splitlines()
                          if not l.lstrip().startswith("#"))
        self.assertIn("__pycache__", body, "キャッシュを消していない")
        self.assertIn("rm -rf", body)

    def test_check_shが終了コードを捨てない(self):
        """**検査の後ろにパイプを置かない。** tail も head も grep も 0 を返す。"""
        for line in read(self.SH).splitlines():
            line = line.strip()
            if line.startswith("#") or "unittest" not in line:
                continue
            self.assertNotIn(
                "|", line,
                "検査の後ろにパイプがある。**終了コードが飲まれる**: %s" % line)

    def test_キャッシュが残っていると嘘をつくことを覚えておく(self):
        """**実測（2026-09-19）。** 同じ秒・同じバイト数で書き換えると当たる。

        ここは動きを見るのではなく、**確かめた事実を固定する**ための1本。
        `-B` を足して済ませた日に、これが残る。
        """
        body = read(self.SH)
        for 語 in ("-B", "mtime"):
            self.assertIn(語, body,
                          "check.sh から「%s」の説明が消えている。"
                          "**なぜ消すのかが分からないと、次の人が -B に戻す**"
                          % 語)


class 公開用のworkflowの控え(unittest.TestCase):
    """④の鍵が入った日に、公開用の `.github/workflows/keibai.yml` に入れる控え。

    **ここでは走らない**（金庫に `.github/workflows/` を増やさないため、
    ふつうのファイルとして置いてある）。走らないものは、書いた形が
    そのまま残る。**入れる日まで、守りが揃っているかをここで見る。**

    入れる日は `tests/test_workflow.py` も同じコミットで入れる
    （`make_public_tree.py` の WAIT_FOR_WORKFLOW が片方だけを止める）。
    """

    def find(self):
        """**公開用の workflow を、置き場ではなく中身で見つける。**

        金庫では控え（`scripts/public-workflow.yml`）、
        公開用では `.github/workflows/` の中。
        **置き場で探すと、入れた日から11本 skip になる**
        （2026-09-19。skip の一覧が読まれなくなる形を、また作りかけた）。

        見分けるのは中身。**鍵を使うのは公開用だけ**（金庫は置き場で、
        Secret を持たない）。最初は「印を持たない」も条件に入れていたが、
        **公開用の workflow の説明文に「印はここには無い」と書いてあって、
        文字列としては当たってしまった。**
        中身で見分けるときは、説明文にも同じ語が出ることを見ておく。
        """
        控え = os.path.join(ROOT, "scripts", "public-workflow.yml")
        if os.path.exists(控え):
            return 控え
        for path in workflows():
            if "RAW_DEPLOY_KEY" in read(path):
                return path
        return None

    def setUp(self):
        self.P = self.find()
        if self.P is None:
            self.skipTest("公開用の workflow がまだ無い"
                          "（金庫に控えも、.github にも）")
        self.text = read(self.P)
        self.body = "\n".join(l for l in self.text.splitlines()
                               if not l.lstrip().startswith("#"))

    def test_名前による自己停止がある(self):
        """**印による逃げ道は無い。** 公開用には印が行かないので、名前だけで止まる。"""
        body = step_body(self.text, "金庫では走らないことの確認")
        self.assertIsNotNone(body, "自己停止の step が無い")
        self.assertNotIn("ikou-mae", body,
                         "公開用に印の逃げ道を持ち込んでいる。"
                         "**印は公開用には行かない。名前だけで止まる**")
        for repo in ("VirgoB77/keibai-toukei-raw", "VirgoB77/x-raw-2"):
            rc, out = run_body(body, repo, mark=False)
            self.assertEqual(rc, 1, "%s で止まらない:\n%s" % (repo, out))
        rc, out = run_body(body, "VirgoB77/keibai-toukei", mark=False)
        self.assertEqual(rc, 0, "公開用で止まっている:\n%s" % out)

    def test_秘密鍵のCRLFを落とす(self):
        """**Windows から貼ると改行が CRLF になる**（2026-09-19）。

        そのまま書くと `Load key: invalid format` で落ちる。
        **そこで鍵を作り直しに行かせない。** 鍵のせいではない。
        """
        body = step_body(self.text, "金庫を隣に出す")
        self.assertIsNotNone(body, "金庫をつなぐ step が無い")
        self.assertIn("tr -d", body, "秘密鍵の \\r を落としていない")
        self.assertIn("ssh-keygen -y", body,
                      "鍵の形を先に見ていない。**取りに行く前に落とす**")

    def test_dataの直下のファイルも金庫につなぐ(self):
        """ディレクトリだけつなぐと、**直下のファイルが毎回消える。**

        `inbox-ledger.json` が消えると「取り込んだ」の記録が飛び、
        **同じものを毎朝催促する。**
        `data/*.md`（走らせた記録）も金庫に置く（公開用には出さない）。
        """
        body = step_body(self.text, "今までのパスにつなぐ")
        self.assertIsNotNone(body)
        for f in ("inbox-ledger.json", "parse-unknown.md", "recon-report.md"):
            self.assertIn(f, body, "data/%s を金庫につないでいない" % f)

    def test_鍵が無ければ何もしない(self):
        """鍵が無いまま進むと、**その日の出力が空のまま公開側に載る**。"""
        self.assertIn("RAW_DEPLOY_KEY", self.body)
        self.assertIn("鍵があることの確認", self.body)

    def test_金庫が見えていないかを_つなぐ前に確かめる(self):
        つなぐ = self.body.index("金庫を隣に出す")
        確かめ = self.body.index("金庫が非公開であることの確認")
        self.assertLess(確かめ, つなぐ,
                        "**つないでから確かめている。** 順番が逆")

    def test_取り直せないものを先にしまう(self):
        """**収集用 → 公開用。** 集計より前に、その朝に取ったページを金庫へ。"""
        金庫 = self.body.index("金庫にしまう（取り直せないものが先）")
        集計 = self.body.index("数字にまとめる")
        公開 = self.body.index("公開用にしまう（許可リスト）")
        self.assertLess(金庫, 集計, "集計のあとに生データをしまっている")
        self.assertLess(集計, 公開, "集計の前に公開用へ送っている")

    def test_検査を2回通す(self):
        """1回目は昨日の出力に対して。**それだけだと今日の伏せ忘れが載る。**"""
        self.assertEqual(self.body.count("sh scripts/check.sh"), 2,
                         "検査が2回通っていない（作る前と、送る前）")

    def test_配る場所に置く(self):
        """**しまう場所と配る場所は別**（DESIGN「公開用の棚」）。

        金庫の `data/public/` は「ここから先は出してよい」という仕切りの
        名前で、配る側では意味が無い。
        """
        from common import site
        公開 = self.body[self.body.index("公開用にしまう（許可リスト）"):]
        self.assertIn('git add "data/$(basename "$f")"', 公開)
        self.assertNotIn("git add data/public/index.json", 公開,
                         "しまう場所のまま配っている")

    def test_dataを丸ごと消さない(self):
        """**`data/` には金庫への symlink が並んでいる。**

        `data/raw` `data/rows` … と `data/inbox-ledger.json`。
        `rm -f data/*.json` はその symlink まで持っていく。
        消えると「取り込んだ」の記録が飛び、同じものを毎朝催促する。
        """
        公開 = self.body[self.body.index("公開用にしまう（許可リスト）"):]
        for 危ない in ("rm -rf data\n", "rm -f data/*.json", "rm -rf data/*"):
            self.assertNotIn(危ない, 公開, 危ない)

    def test_公開用には丸ごとaddしない(self):
        """**許可リストが掛かるのは公開用だけ。**

        金庫は private で、生データをもともと全部追いかけている。
        そちらは丸ごとでよい（正本 9節）。
        **公開用に丸ごと add すると、足すつもりのないものが載る。**
        足し忘れは「載らない」で済むが、逆は済まない。
        """
        公開 = self.body[self.body.index("公開用にしまう（許可リスト）"):]
        for ng in ("git add -A", "git add ."):
            self.assertNotIn(ng, 公開, "公開用に丸ごと add している: %r" % ng)
        金庫 = self.body[self.body.index("金庫にしまう"):
                        self.body.index("数字にまとめる")]
        self.assertIn("git add", 金庫, "金庫に何も送っていない")

    def test_CNAMEを足さない(self):
        """**仕掛けではなく「入れないこと」が守り。**

        こちらが add すると、GitHub が書き戻した CNAME を消す差分になる。
        """
        公開 = self.body[self.body.index("公開用にしまう（許可リスト）"):]
        self.assertNotIn("CNAME", 公開)

    def test_走った日を1回だけ決める(self):
        n = self.body.count("date +%F") + self.body.count("date -u")
        self.assertLessEqual(n, 1, "時計を %d 回打っている" % n)
        self.assertIn("RUN_DATE", self.body)
        self.assertEqual(top_env(self.text).get("TZ"), "Asia/Tokyo")

    def test_unittestを直に打たない(self):
        self.assertNotIn("python3 -m unittest", self.body,
                         "**急いだ日に打つ形。** check.sh を通すこと")

    def test_配られている実物を1回見る(self):
        """**手前の検査は全部「出すつもりのもの」しか見ていない。**

        Pages が建てるのをやめても、途中で別のものを配っても、
        木の検査も許可リストも、そのまま緑になる。
        **配られている実物を取りに行く段が、1つだけ要る。**
        """
        self.assertIn("配られている実物を見る", self.body)
        配信 = self.body[self.body.index("配られている実物を見る"):]
        self.assertIn("check_haishin.py", 配信)

    def test_配信の中身を2か所に書かない(self):
        """**手で押す workflow と同じものを呼ぶ。**

        前はここに Python を直接書いていた。手で押せる workflow を足したとき、
        同じ判定が2か所になる。**片方だけ直る形を先に潰す。**
        """
        配信 = self.body[self.body.index("配られている実物を見る"):]
        for 中身 in ("records", "counts_by_city", "json.loads"):
            self.assertNotIn(中身, 配信,
                             "配信の判定が workflow の中に書いてある。"
                             "scripts/check_haishin.py に寄せること")

    def test_site_urlが空のあいだは待たない(self):
        """**鳴らない見張りにしない**（正本 3.3）。

        ⑤ Pages がまだなら配信は無い。判定そのものは
        `check_haishin.py` が素通りするが、**待ち時間まで素通りさせる。**
        毎朝1分を、何も見ないために使わない。
        """
        配信 = self.body[self.body.index("配られている実物を見る"):]
        self.assertIn("base_url", 配信)
        self.assertLess(配信.index("base_url"), 配信.index("sleep"),
                        "入口が空かどうかを見る前に待っている")

    def test_配信を見るのは公開用にしまったあと(self):
        """順番。**押す前の木を見ても、配られているものは分からない。**"""
        self.assertLess(self.body.index("公開用にしまう（許可リスト）"),
                        self.body.index("配られている実物を見る"))


class 手で押す配信の確認(unittest.TestCase):
    """**相手のサーバーに触らずに、配信だけを見たい日がある。**

    毎朝のほうは取りに行ったあとにしか配信を見ない。だから

        相手のサーバーが落ちて偵察で止まった日   配信を見ないまま終わる
        site_url を入れる前に確かめたい日         毎朝を回すと相手に触る
    """

    def find(self):
        控え = os.path.join(ROOT, "scripts", "public-haishin-workflow.yml")
        if os.path.exists(控え):
            return 控え
        for path in workflows():
            if "check_haishin.py" in read(path) and "RAW_DEPLOY_KEY" not in read(path):
                return path
        return None

    def setUp(self):
        self.P = self.find()
        if self.P is None:
            self.skipTest("手で押す配信の確認がまだ無い")
        self.text = read(self.P)
        self.body = "\n".join(l for l in self.text.splitlines()
                                if not l.lstrip().startswith("#"))

    def test_自分で走り出さない(self):
        """**毎朝の分は毎朝のほうが見る。** 勝手に走ると同じものを2回見る。"""
        self.assertNotIn("schedule", self.body)
        self.assertNotIn("cron", self.body)
        self.assertIn("workflow_dispatch", self.body)

    def test_名前による自己停止がある(self):
        """**逃げ道を1つも作らない。**

        ここは外に出るだけで金庫には触らないが、
        「ここは触らないから要らない」を1回許すと、次に同じ理由が使われる。
        """
        self.assertIsNotNone(step_body(self.text, STEP))

    def test_入口を引数で渡せる(self):
        """**確かめてから site_url を入れる**のが順番。

        site.json に入れないと確かめられない作りにすると、順番が逆になる。
        """
        self.assertIn("inputs", self.body)
        self.assertIn("check_haishin.py", self.body)

    def test_金庫に書き込まない(self):
        """見るだけ。**押せる手は、できることを小さくしておく。**"""
        self.assertNotIn("RAW_DEPLOY_KEY", self.body)
        self.assertIn("contents: read", self.body)

    def test_公開用の木に入る(self):
        """入れ忘れると、**押す手が公開用に無い**まま気づけない。

        許可リストは金庫にしかない（`make_public_tree.py` は公開用の木に
        入れない。入れると公開側から「何を外したか」が読めてしまう）。
        **だから公開用では skip する。金庫では走る。**
        """
        try:
            import scripts.make_public_tree as m
        except ImportError:
            self.skipTest("許可リストは金庫にしかない（公開用では、これが正しい）")
        self.assertIn("scripts/public-haishin-workflow.yml", m.RENAME)
        self.assertIn("scripts/check_haishin.py", m.FILES)


if __name__ == "__main__":
    unittest.main()
