#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""名乗りを1か所から配る（正本 3.4・6節・9節）。

**site_id と、外に名乗る名前は、別の速さで決まる。**

    site_id    内部の鍵。**records が0件のうち**に決める（9節「鍵は変えない」）
    名乗り     相手のサーバーに届く。**ドメインを検証してから**でないと、
               相手が調べても存在せず、3.4「確認できない名乗りは、
               名乗らないより不審に見える」に触れる

だからこのサイトは、2026-09-18 に site_id だけを先に当てて、
名乗り（UA）は `ua_label` で据え置いている。

**据え置きは消し忘れる。** about ページを公開して `about_url` が入れば
`user_agent()` はそちらを使うので、`ua_label` は要らなくなる。
残っていても動くので、走らせても気づけない。だから下の
`test_⓪が済んだらua_labelを消す` が鳴る。

**鳴らして確かめた**（正本 9節。2026-09-18）。書いたから動くはず、で止めない。

    about_url を入れて ua_label を残す（消し忘れ）  → 2件 鳴った
    ua_label を消して site_id に落とす              → 2件 鳴った
    site_url に未公開のURLを入れる                  → 1件 鳴った
    戻す                                            → 黙った

    python3 -m unittest discover -s tests
"""

import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from common import site  # noqa: E402

PATH = os.path.join(ROOT, "common", "site.json")


def raw():
    with open(PATH, encoding="utf-8") as f:
        return json.load(f)


class 決めた名前(unittest.TestCase):
    """2026-09-18 の決定。**もう変えない**（正本 9節）。"""

    def test_site_idはドメインの語幹(self):
        self.assertEqual(site.SITE["site_id"], "keibai-toukei")

    def test_接頭辞は2節の表のとおり(self):
        self.assertEqual(site.id_prefix(), "keibai")

    def test_リポジトリ名をsite_idに使わない(self):
        """リポジトリ名は変わる（金庫は `keibai-toukei-raw` に rename する）。

        正本 9節「鍵にはあとから変わらないものだけを入れる」。
        """
        for bad in ("keibai-data", "keibai-toukei-raw", "ic-log"):
            self.assertNotEqual(site.SITE["site_id"], bad)


class 名乗りは据え置き(unittest.TestCase):
    """**⓪（ドメインの検証）が済むまで、外向きの名乗りは変えない。**"""

    def test_UAは決めた名前になっている(self):
        """⓪（ドメインの検証）が 2026-09-19 に済んだので当てた。

        据え置いていたのは、検証の前に名乗ると**相手が調べても存在せず**、
        正本 3.4「確認できない名乗りは、名乗らないより不審に見える」に
        触れるため。検証が済んだので、その理由が無くなった。
        """
        self.assertIn("keibai-toukei", site.user_agent())

    def test_UAに連絡先が入っている(self):
        """正本 3.4「UA に連絡先の URL を入れる」。"""
        self.assertIn(site.contact_url(), site.user_agent())
        self.assertTrue(site.contact_url().startswith("https://"))

    def test_site_urlは配信を確かめてから入れた(self):
        """**2026-09-19 に入れた。実物を引いてから。**

        ⓪（Verified domains）は「ほかの人にドメインを取られない」ことを
        保証するだけで、「そこに何かがある」ことは保証しない。
        だから⓪とは別に、配信そのものを見てから入れた
        （正本 3.4「404を入れない。まだ公開していないページのURLは入れない」）。

        確かめた中身:

            取りに行く: https://keibai-toukei.com/data/index.json
            配られているもの: 市区町村 92 / records 0（からっぽ）

        **本体（apex）にすること。** www は 301 で飛ぶ。
        飛ばされる側を入れると index.json のURLが全部リダイレクトになり、
        配信の確認（リダイレクトを追わない）も落ちる。
        """
        u = site.SITE.get("site_url", "")
        self.assertTrue(u.startswith("https://"), u)
        self.assertFalse(u.startswith("https://www."),
                         "www は 301 で飛ぶ側。本体を入れること")
        self.assertTrue(u.endswith("/"), "末尾のスラッシュを落とさない")

    def test_ドメイン検証が済んだらua_labelを消す(self):
        """**据え置きは消し忘れる。**

        about ページを公開して `about_url` が入れば `user_agent()` は
        そちらを使うので、`ua_label` は要らなくなる。
        残っていても動くので、走らせても気づけない。ここが鳴る。
        """
        d = raw()
        if not d.get("about_url"):
            self.assertTrue(
                d.get("ua_label"),
                "about_url がまだ空なのに ua_label も空。"
                "名乗りが site_id に落ちて、検証前のドメイン名を名乗ることになる")
            return
        self.assertFalse(
            d.get("ua_label"),
            "about ページを公開したのに ua_label が残っている。"
            "名乗りが2つある状態になるので、common/site.json から消すこと")


class 入口のURL(unittest.TestCase):
    """**site_url を入れる日に、いちばん急いでいる。だから今のうちに置く。**

    `BASE_URL` は `"%s%s/%s.html" % (BASE_URL, system, key)` でつなぐ。
    末尾の `/` を付け忘れると、つないだ先がこうなる:

        https://keibai-toukei.comkeibai/xxx.html

    **形としては正しいURLなので、検査を通って押せてしまう。**
    気づくのは、誰かが踏んで404になったとき。

    いまは site_url が空なので、ここは1本も効いていないように見える。
    そうではない。**空のときの戻り値（相対URL）も、ここで縛っている。**
    """

    def 入れてみる(self, 値):
        import common.site as m
        keep = dict(m.SITE)
        keepenv = os.environ.pop("SITE_URL", None)
        try:
            m.SITE["site_url"] = 値
            return m.base_url()
        finally:
            m.SITE.clear()
            m.SITE.update(keep)
            if keepenv is not None:
                os.environ["SITE_URL"] = keepenv

    def test_末尾のスラッシュをそろえる(self):
        for 入れた in ("https://keibai-toukei.com",
                       "https://keibai-toukei.com/",
                       "https://keibai-toukei.com//",
                       "  https://keibai-toukei.com  "):
            self.assertEqual(self.入れてみる(入れた),
                             "https://keibai-toukei.com/", 入れた)

    def test_ドメインと次の語がくっつかない(self):
        """**これが本番のつなぎ方そのもの**（make_index.py・make_cross.py）。"""
        base = self.入れてみる("https://keibai-toukei.com")
        self.assertEqual("%s%s/%s.html" % (base, "keibai", "x"),
                         "https://keibai-toukei.com/keibai/x.html")

    def test_もとから付いていても二重にならない(self):
        base = self.入れてみる("https://keibai-toukei.com/")
        self.assertEqual("%s%s/%s.html" % (base, "keibai", "x"),
                         "https://keibai-toukei.com/keibai/x.html")

    def test_空のときは相対のまま(self):
        """配信がまだ無い日に、絶対URLを名乗らない（正本 3.4「404を入れない」）。"""
        self.assertEqual(self.入れてみる(""), "")
        self.assertEqual("%s%s/%s.html" % (self.入れてみる(""), "keibai", "x"),
                         "keibai/x.html")

    def test_本番のBASE_URLがそのままつながる(self):
        """**ここが本番のつなぎ方そのもの。**

        `site_url` を入れた日に、ここも一緒に見直す約束だった（2026-09-19 に入れた）。
        """
        import make_cross
        import make_index
        self.assertEqual(make_index.BASE_URL, site.base_url())
        self.assertEqual(make_cross.BASE_URL, site.base_url())
        つないだ = "%s%s/%s.html" % (make_index.BASE_URL, "keibai", "x")
        self.assertEqual(つないだ, "https://keibai-toukei.com/keibai/x.html")
        self.assertNotIn(".comkeibai", つないだ)

    def test_入れるならhttps(self):
        u = raw().get("site_url", "")
        if not u:
            self.skipTest("site_url はまだ空。入れた日から効く")
        self.assertTrue(u.startswith("https://"), u)

    def test_配信しているドメインと食い違わない(self):
        """**CNAME は GitHub が公開側に書いたもの。そこが唯一の実物。**

        公開用の clone と公開用の Actions にはこれがある。金庫には無い
        （`make_public_tree.py` は CNAME を木に入れない。入れると
        GitHub が書き戻したものを消す差分になってドメインが外れる）。

        だから**金庫では skip、公開用では走る**。走る場所が違う検査で、
        木を見るだけでは捕まらないものを捕まえる。

        www と本体の取り違えがここで鳴る。GitHub が主張しているのは
        CNAME に書いてあるほう1つだけで、もう片方は 301 で飛ばされる。
        飛ばされる側を site_url にすると、index.json に入るURLが全部
        リダイレクトになり、配信の確認（curl は -L を付けていない）も落ちる。
        """
        u = raw().get("site_url", "")
        if not u:
            self.skipTest("site_url はまだ空。入れた日から効く")
        path = os.path.join(ROOT, "CNAME")
        if not os.path.exists(path):
            self.skipTest("CNAME が無い（金庫。公開用の clone では走る）")
        with open(path, encoding="utf-8") as f:
            名乗り = f.read().strip()
        host = u.split("//", 1)[-1].split("/", 1)[0]
        self.assertEqual(host, 名乗り,
                         "site_url のホストと、GitHub が配信しているドメインが違う")


class 配る場所は1か所に書く(unittest.TestCase):
    """**しまう場所と配る場所は別**（DESIGN「公開用の棚」・2026-09-19）。

        金庫   data/public/index.json   しまう場所（ここだけが公開してよい置き場）
        公開用 data/index.json          配る場所（金庫から写したものだけ）

    金庫の `public/` は「ここから先は出してよい」という仕切りの名前で、
    配る側では意味が無い。**配る側の棚に内側の仕切りの名前を持ち込まない。**

    ここが3つに割れていた（2026-09-19 に気づいた）。

        DESIGN.md     （公開用）/data/index.json
        実際の木       data/public/index.json
        配信の確認     /index.json            ← 404 になって気づいた

    **site_url がまだ空で、姉妹サイトも誰も引いていないうちに直した。**
    引かれたあとだと、直すほうが壊す。
    """

    def test_置き場はDESIGNのとおり(self):
        self.assertEqual(site.INDEX_PATH, "data/index.json")

    def test_入口と合わせてURLになる(self):
        import common.site as m
        keep = dict(m.SITE)
        keepenv = os.environ.pop("SITE_URL", None)
        try:
            m.SITE["site_url"] = "https://keibai-toukei.com"
            self.assertEqual(m.index_url(),
                             "https://keibai-toukei.com/data/index.json")
            m.SITE["site_url"] = ""
            self.assertEqual(m.index_url(), "",
                             "配信がまだ無い日に絶対URLを名乗らない")
        finally:
            m.SITE.clear()
            m.SITE.update(keep)
            if keepenv is not None:
                os.environ["SITE_URL"] = keepenv

    def test_配信の確認が同じ置き場を見る(self):
        """**2か所に書かない。** 片方だけ直ると404で気づくことになる。"""
        import inspect
        sys.path.insert(0, os.path.join(ROOT, "scripts"))
        import check_haishin
        src = inspect.getsource(check_haishin.見る)
        self.assertIn("site.INDEX_PATH", src)
        self.assertNotIn('"/index.json"', src)

    def test_公開用の木が配る場所に置く(self):
        try:
            import scripts.make_public_tree as m
        except ImportError:
            self.skipTest("許可リストは金庫にしかない（公開用では、これが正しい）")
        self.assertEqual(m.RENAME.get("data/public/index.json"),
                         site.INDEX_PATH)
        self.assertNotIn("data/public/index.json", m.FILES,
                         "しまう場所のまま配っている")

    def test_DESIGNに書いてある形と合っている(self):
        """**書いたものと動くものを突き合わせる。** 片方だけ直る形を潰す。"""
        path = os.path.join(ROOT, "DESIGN.md")
        if not os.path.exists(path):
            self.skipTest("DESIGN.md がここには無い")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("（公開用）/%s" % site.INDEX_PATH, text,
                      "DESIGN の棚と site.INDEX_PATH が食い違っている")


class つなぎの1枚(unittest.TestCase):
    """**ドメインを付けた日から、そのドメインは404を返す**（2026-09-19）。

    ドメインを付けるのと、人が見るページを作るのは別の作業。
    ⓪〜⑤は「ドメインを取り合わない」ための順番で、
    **中身があるかは見ていない。** 別の問いなので、別に確かめる。

    棚の全体（Phase 3）はまだ作らない。ここは
    「何のサイトで、誰がやっていて、いつ本番になるか」だけを置く。
    """

    def setUp(self):
        self.path = os.path.join(ROOT, "index.html")
        if not os.path.exists(self.path):
            self.fail("index.html が無い。ドメインに来た人が404を見る")
        with open(self.path, encoding="utf-8") as f:
            self.html = f.read()
        import re
        # 注記（<!-- -->）と見た目（<style>）を落とす。
        # **注記も配られる**ので、禁じた語の検査だけは全文を見る
        t = re.sub(r"<!--.*?-->", "", self.html, flags=re.S)
        self.body = re.sub(r"<style\b.*?</style>", "", t, flags=re.S | re.I)
        # 人が目にする文字だけ（タグを落とす）
        m = re.search(r"<main\b[^>]*>(.*)</main>", self.body, flags=re.S | re.I)
        self.text = re.sub(r"<[^>]+>", " ", m.group(1) if m else self.body)

    def test_誰がやっているかが書いてある(self):
        """正本 7節。**名乗りは1か所から配る**ので、site.json と同じ文字にする。"""
        d = raw()
        self.assertIn(d["operator"], self.body)
        self.assertIn(d["contact_url"], self.body)

    def test_何を数えているかが書いてある(self):
        for 語 in ("競売", "公売", "大阪府", "兵庫県"):
            self.assertIn(語, self.body, 語)

    def test_出さないものを出さないと書いてある(self):
        """**いちばん大事な約束**（正本 1節）。見に来た人に先に伝える。"""
        self.assertIn("物件そのものの一覧は出しません", self.body)

    def test_同じ語で別のものを名指しで外す(self):
        """**「公売」には2つある。**

        滞納処分による公売（ここで扱う）と、
        公有財産の売却（市や県が自分の土地を売る。ここでは扱わない）。

        「税金の滞納による公売」と書けば読み分けられる。
        **書いてあっても、読む人は自分の知っているほうで読む。**
        実物で迷われた（2026-09-19）。**出さないほうを名指しする。**
        """
        self.assertIn("公有財産の売却", self.text)
        self.assertIn("ここでは扱いません", self.text)

    def test_検索に出る文にも同じ書き分けがある(self):
        """**1枚の中で言い方が2つあると、片方だけ直る。**

        `description` は検索結果に出る文で、本文より先に読まれることがある。
        """
        import re
        m = re.search(r'<meta name="description" content="([^"]*)"', self.body)
        self.assertIsNotNone(m, "description が無い")
        文 = m.group(1)
        self.assertIn("税金の滞納による公売", 文)
        self.assertIn("公有財産の売却", 文)

    def test_配っているファイルへ行ける(self):
        self.assertIn('href="%s"' % site.INDEX_PATH, self.body,
                      "配っているものへの道が無い")

    def test_売り文句を書かない(self):
        """正本 3.3。**書くのは「何を数えているか」だけ。**"""
        for 語 in ("狙い目", "安く買える", "穴場", "お得", "儲か"):
            self.assertNotIn(語, self.html, 語)

    def test_まだ試作だと書いてある(self):
        """**言わないと、本番の顔で読まれる。**"""
        self.assertIn("試作版", self.body)

    def test_よそのサーバーを読み込まない(self):
        """**人が見るだけのページに、よそのサーバーを混ぜない。**

        リンクは行き先なので別。読み込むもの（script・link・img）を見る。
        """
        import re
        for tag in re.findall(r"<(script|link|img)\b[^>]*>", self.html, re.I):
            self.fail("外から読み込んでいる: %s" % tag)

    def test_公開用の木に入る(self):
        """入れ忘れると、**直したのに404のまま**になる。"""
        try:
            import scripts.make_public_tree as m
        except ImportError:
            self.skipTest("許可リストは金庫にしかない（公開用では、これが正しい）")
        self.assertIn("index.html", m.FILES)

    def test_数を書かない(self):
        """**書くと data/index.json と2か所になって、片方だけ古くなる。**"""
        import re
        for n in re.findall(r"[0-9]{2,}", self.text):
            self.fail("人が読む文字に数がある（%s）。"
                      "配っているファイルを見てもらう" % n)


class 退役した名前(unittest.TestCase):
    """**退役した名前の一覧と比べる。現在値と比べない**（正本 9節）。

    現在値と比べる作りにすると、手で直した瞬間に old == new になり、
    見張りが黙って空振りする。

    **ここには1つ、わざと退役名が残っている場所がある。**
    `ua_label`（＝ UA の頭）は `keibai-data` のままで、これは
    ⓪（ドメインの検証）が済むまでの据え置き。意図して残しているので、
    テストは「残っていること」ではなく **「いつまで残ってよいか」** を見張る。
    """

    def test_site_idに退役名を使わない(self):
        for old in site.RETIRED_NAMES:
            self.assertNotEqual(site.SITE["site_id"], old, old)
            self.assertNotEqual(site.id_prefix(), old, old)

    def test_出す升のsiteに退役名を使わない(self):
        import make_index
        for old in site.RETIRED_NAMES:
            self.assertNotEqual(make_index.SITE, old, old)
            self.assertNotEqual(make_index.PREFIX, old, old)

    def test_UAに退役名が1つも出ない(self):
        """**⓪が済んだので、据え置きの理由が無くなった**（2026-09-19）。

        据え置いていたあいだは、`ua_label` としてだけ退役名が出てよかった。
        いまは1つも出てはいけない。
        """
        ua = site.user_agent()
        for old in site.RETIRED_NAMES:
            self.assertNotIn(old, ua, old)

    def test_退役名の一覧を減らさない(self):
        """**消さない。** 減らすと、次に同じ名前が戻ってきても鳴らない。"""
        for old in ("ic-log", "keibai-data"):
            self.assertIn(old, site.RETIRED_NAMES, old)


class 設定が読めない日は止まる(unittest.TestCase):
    """**古い名前で行く日を作るより、取りに行かない日を作る**（正本 3.4）。

    前は黙って既定値を返していた。そうすると設定が壊れた日に、
    古い名前で・連絡先の無い名乗りで相手のサーバーに出ていく。
    しかも**失敗した日にしか出ない**ので、テストでも手元でも見えない。
    """

    def test_読めなければ例外(self):
        import tempfile
        import common.site as m
        keep = m.PATH
        try:
            m.PATH = os.path.join(tempfile.mkdtemp(), "no-such.json")
            with self.assertRaises(RuntimeError):
                m._load()
        finally:
            m.PATH = keep

    def test_site_idが無ければ例外(self):
        import tempfile
        import common.site as m
        keep = m.PATH
        d = tempfile.mkdtemp()
        path = os.path.join(d, "site.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"bot_name": "x"}, f)
        try:
            m.PATH = path
            with self.assertRaises(RuntimeError):
                m._load()
        finally:
            m.PATH = keep

    def test_既定値に名前を持たせない(self):
        """既定値に名前を書くと、欄が消えた日にその名前で名乗る。

        **2026-09-19 まで2つ残っていた**（`bot_name` と `operator`）。
        `common/site.py` の注記は「名前を持たせない」と書いてあったのに、
        コードはそうなっていなかった。`bot_name` は**相手のサーバーに届く
        名乗り**そのもので、site.json から欄が消えても補われて動きつづける。
        **動くので誰も気づかない。**

        ここは**1つずつ名指ししない**。名指しだと、次に足した欄を書き忘れる。
        **全部の欄が空であることを見る。**
        """
        for k, v in m_default().items():
            self.assertEqual(v, "", "既定値に %s が入っている（%r）" % (k, v))

    def test_名乗りの欄が無ければ止まる(self):
        """**空のまま外に出る**より**今日は取りに行かない**（正本 3.4）。"""
        import json as _json
        import tempfile
        import common.site as m
        いまの = raw()
        for 抜く in ("site_id", "bot_name", "contact_url", "operator"):
            d = {k: v for k, v in いまの.items() if k != 抜く}
            path = os.path.join(tempfile.mkdtemp(), "site.json")
            with open(path, "w", encoding="utf-8") as f:
                _json.dump(d, f, ensure_ascii=False)
            keep = m.PATH
            m.PATH = path
            try:
                with self.assertRaises(RuntimeError, msg=抜く):
                    m._load()
            finally:
                m.PATH = keep

    def test_違ってよいものがどこにあるかを書いてある(self):
        """正本 11節「**同じでない理由をそのサイトに書く**」。

        ここには指紋の仕組みが無い（`MANIFEST.txt` も `DIFFERENCES` も無い）。
        代わりに、サイトごとに違う値は**コードではなくデータ**に置いてある。
        **その形そのものを書いておく。**
        """
        path = os.path.join(ROOT, "DESIGN.md")
        if not os.path.exists(path):
            self.skipTest("DESIGN.md がここには無い")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("サイトごとに違ってよいもの", text)
        for 語 in ("common/site.json", "共通のコードは1文字も変わらない"):
            self.assertIn(語, text, 語)

    def test_名乗りは欄が揃っていれば作れる(self):
        """**止まる側だけ見ない。** 通るほうも見ないと、全部止める形でも通る。"""
        self.assertIn(raw()["bot_name"], site.user_agent())
        self.assertIn(raw()["contact_url"], site.user_agent())


def m_default():
    import common.site as m
    return m._DEFAULT


class 名乗りは1か所から(unittest.TestCase):

    def test_URLをコードに直書きしていない(self):
        """正本 3.4「URL は設定の1か所にだけ書く」。"""
        import glob
        bad = []
        for path in glob.glob(os.path.join(ROOT, "*.py")) + \
                glob.glob(os.path.join(ROOT, "common", "*.py")):
            if os.path.basename(path) == "site.py":
                continue
            with open(path, encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    if line.lstrip().startswith("#"):
                        continue
                    if "forms.gle" in line or "keibai-toukei.com" in line:
                        bad.append("%s:%d" % (os.path.basename(path), i))
        self.assertEqual(bad, [], "URL が common/site.json の外に書いてある")


if __name__ == "__main__":
    unittest.main()
