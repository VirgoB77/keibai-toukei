#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""個人のアドレスが履歴に増えていないか（正本 7節）。

正本 7節「氏名はリポジトリにも書かない。一度もコミットしない。
個人のメールアドレスも同じ（**コミットの作者欄も含む**）」。

**見る場所が2つある。同じ grep では両方見えない。**

    ① ファイルの中身（全履歴）  git grep … $(git rev-list --all)
    ② コミットの枠（作者欄・コミッタ欄）  git log --all --format='%ae%n%ce'

①だけ見ると「無い」、②だけ見ると「ある」。**このサイトで実際に起きた**
（2026-09-17。ファイルの中身は正しく、作者欄を見落としていた）。

**このテストは②を見る。** ①は伏せる前の値と同じ扱いで privacy 側が見ている。

## なぜ「0件」を求めないか

いまの履歴に12コミット入っていて、**消せない**。
force-push しても refs/pull・fork・キャッシュに残る（正本 9節）。
このリポジトリは公開しない（金庫）ので、消す必要も無い。

だから求めるのは「0件」ではなく「**増えていない**」。
既知の12個を名簿に固定し、それ以外が出たら落とす。
名簿はコミットの ID だけ。**アドレスそのものはここに書かない**
（書いたら、この見張りが自分で正本 7節を破る）。

## 浅いクローンで確かめない

`--depth 1` の置き場でこの検査を走らせると「無い」と嘘が出る。
持っていない履歴は数えられない。**姉妹サイトが実際に踏んだ**（同日。
浅いクローンで「0件」と報告し、取り直したら23件出た）。
だから浅ければ落とさず skip し、**浅いことを画面に出す**。

    python3 -m unittest discover -s tests
"""

import os
import subprocess
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 許可リスト。**除外リストにしない**（正本 3.2「許可リストのほうが強い」）。
# 新しい書き方が増えたら、ここに足すほうがきつい側。足し忘れは「落ちる」で済む
OK_EXACT = ("noreply@anthropic.com", "noreply@github.com")
OK_SUFFIX = ("@users.noreply.github.com",)

# いま履歴に入っているもの。**増えていないこと**だけを見る。
# 2026-09-17 時点。すべて 2026-09-14〜15 の手作業ぶん
KNOWN = frozenset((
    "08d8089d191d60e1f5d1780a217a21a9c3344329",
    "0e27b2646e48ed163fe43cdea2494ef0cb6c92a9",
    "2718b31feefd84b833ec5429efa8d2c77598e0a0",
    "6617ca1330b41684440c0787eea64aa1b9955440",
    "6feecf54789ffbb381bcf5be31c4574aa5ea2154",
    "89bba29c445099268a8aa42b0e919081efa9f38a",
    "a30f06776d9cbfa943b4e5d162e636a298f9f9b3",
    "bb9117654a80cdc980ce4101456eb3eaf39c705e",
    "bef10597eb2840c674d904dedc247a1770cf3b57",
    "c02bec5099e95fc361415c6d87a576b787d0e1b6",
    "cc1a268346a9fc2273c7a5b4c5cf8faf7bfc3179",
    "ffdf490c148b9a7a523496dc57795c3853248f77",
))


def git(*args):
    r = subprocess.run(("git",) + args, cwd=HERE,
                       capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def allowed(addr):
    return addr in OK_EXACT or addr.endswith(OK_SUFFIX)


class コミットの枠(unittest.TestCase):

    def setUp(self):
        if git("rev-parse", "--git-dir") is None:
            self.skipTest("git の置き場ではない")
        # **走らせる前に、浅くないことを見る**（正本 7節）
        if os.path.exists(os.path.join(HERE, ".git", "shallow")):
            n = (git("rev-list", "--all", "--count") or "?").strip()
            self.skipTest(
                "**浅いクローン**なので数えられない（コミット %s 個しか無い）。"
                "この検査は全履歴でないと「無い」と嘘が出る。"
                "CI なら actions/checkout に fetch-depth: 0 を付けること" % n)

    def test_許可リストの外が増えていない(self):
        out = git("log", "--all", "--format=%H%x09%ae%x09%ce")
        self.assertIsNotNone(out, "git log が読めない")
        found = set()
        for line in out.splitlines():
            h, ae, ce = line.split("\t")
            if not allowed(ae) or not allowed(ce):
                found.add(h)
        new = found - KNOWN
        self.assertEqual(
            sorted(new), [],
            "**作者欄またはコミッタ欄が許可リストの外**のコミットが増えた。\n"
            "個人のアドレスなら、正本 7節が禁じている（一度コミットすると消せない）。\n"
            "git の設定を noreply に直してから commit し直すこと。\n"
            "GitHub の Settings → Keep my email addresses private。\n"
            "許可してよい書き方なら OK_EXACT / OK_SUFFIX に足す。\n"
            "増えたコミット: %s" % sorted(new))

    def test_名簿が古くなっていない(self):
        """消えた（rebase された）ものが名簿に残っていたら、名簿を縮める。

        名簿が実物より大きいままだと、本当に増えたときに
        「増えた − 名簿」で打ち消されることはないが、名簿が嘘になる。

        **「1つも無い」と「いくつか消えた」は別のこと**（2026-09-19）。

        名簿は**この金庫の履歴**のものなので、公開用のリポジトリ
        （履歴ゼロで別に作った）には1つも無い。そこで落とすと、
        **公開用では毎回落ちる検査**になる。実際そうなっていた。

        公開用の Actions は取りに行く前に
        `python3 -m unittest discover -s tests` を通す。
        **この1本のせいで、1回も通らないまま止まる。**

        だから見分ける。

            1つも無い       別の履歴。この検査の見る相手ではない → skip
            いくつか消えた   名簿が古い → 落とす
        """
        out = git("log", "--all", "--format=%H%x09%ae%x09%ce")
        self.assertIsNotNone(out)
        found = set()
        for line in out.splitlines():
            h, ae, ce = line.split("\t")
            if not allowed(ae) or not allowed(ce):
                found.add(h)
        if KNOWN and not (KNOWN & found):
            self.skipTest(
                "名簿のコミットが1つも無い。**別の履歴**（公開用は履歴ゼロで"
                "作ってある）。名簿はこの金庫のものなので、ここでは見ない")
        self.assertEqual(sorted(KNOWN - found), [],
                         "名簿にあるコミットが履歴から消えている。名簿を縮めること")

    def test_いまのHEADはきれい(self):
        """**これから積むぶん**が許可リストに入っていること。"""
        out = git("log", "-1", "--format=%ae%x09%ce")
        self.assertIsNotNone(out)
        ae, ce = out.strip().split("\t")
        for addr in (ae, ce):
            self.assertTrue(
                allowed(addr),
                "いちばん新しいコミットの枠が許可リストの外。"
                "git config user.email を noreply に直すこと")


if __name__ == "__main__":
    unittest.main()
