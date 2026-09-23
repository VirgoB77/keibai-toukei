#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""**配られている実物を見る。**

    python3 scripts/check_haishin.py                  site.json の入口を見る
    python3 scripts/check_haishin.py https://…/       その入口を見る

## なぜ要るか

ほかの検査は全部「**出すつもりのもの**」しか見ていない。
許可リストも、木の検査も、`check.sh` も、押す前のファイルしか知らない。

    木を見る    公開用の木に何が入っているか
    走らせる    走ったときに何が起きるか
    配信を見る  **実際に配られているものが何か**   ← ここ

3つとも別のものを捕まえる。Pages が建てるのをやめても、
途中で別のものが配られても、**手前の2つはそのまま緑になる。**

## 入口を引数で渡せる形にしてある

site_url を入れる前に「ほんとうに配られているか」を確かめたい日がある
（⑤ Pages の直後）。**確かめてから入れる**のが順番なので、
site.json に入れないと確かめられない作りにすると、順番が逆になる。

## リダイレクトを追わない

www と本体はどちらか一方だけを GitHub が主張し、もう片方は 301 になる。
追ってしまうと、**飛ばされる側を site_url に入れても緑になる。**
そうすると index.json に入るURLが全部リダイレクトのまま気づけない。
**追わないことが、正しいほうのホストを入れる強制になる。**

Python 3 の標準ライブラリだけで動く。
"""

import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from common import site  # noqa: E402

TIMEOUT = 30
TRIES = 3


class _追わない(urllib.request.HTTPRedirectHandler):
    """301・302 を追わずに、そのまま持って帰る。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def 取りに行く(url):
    """(HTTPの番号, 中身, Content-Type) を返す。つながらなければ (0, 理由, "")。"""
    opener = urllib.request.build_opener(_追わない)
    req = urllib.request.Request(url, headers={"User-Agent": site.user_agent()})
    最後 = ""
    for i in range(TRIES):
        try:
            with opener.open(req, timeout=TIMEOUT) as r:
                return (r.getcode(), r.read().decode("utf-8", "replace"),
                        r.headers.get("Content-Type", ""))
        except urllib.error.HTTPError as e:
            # 404 も 301 も「返ってきた」。数として持って帰る
            return e.code, "", ""
        except Exception as e:                     # noqa: BLE001 つながらない理由は何でも同じ扱い
            最後 = "%s: %s" % (type(e).__name__, e)
    return 0, 最後, ""


def 入口を見る(base):
    """**人が来る1枚**を見る。戻り値は終了コード（0 なら止めない）。

    ドメインを付けるのと、人が見るページを作るのは別の作業。
    **ドメインを付けた日から、そのドメインは404を返す。**

    2026-09-19 に実際にそうなった。`data/index.json` は配信できていたのに、
    `.html` が1枚も無く（`.nojekyll` があるので Markdown も描かれない）、
    **来た人は全員404を見ていた。** 配っているファイルだけを見る検査は、
    それを1つも捕まえない。**別の問いなので、別に見る。**
    """
    url = base.rstrip("/") + "/"
    print("入口を見る: %s" % url)
    code, body, ctype = 取りに行く(url)

    if code == 0:
        print("::error::入口につながらない。%s" % body)
        return 1
    if code in (301, 302, 303, 307, 308):
        print("::error::入口が %d で飛ばした。**追わない**。%s" % (code, url))
        print("飛ばされない側を入口にすること")
        return 1
    if code != 200:
        print("::error::**入口が %d。来た人はこれを見る。** %s" % (code, url))
        print("公開用の木に人が読む1枚があるか見ること")
        return 1
    if "html" not in (ctype or "").lower():
        print("::error::入口が HTML ではない（%s）。%s" % (ctype, url))
        return 1
    print("入口: %d バイトの HTML が返っている" % len(body.encode("utf-8")))
    return 0


def 見る(base):
    """配られている index.json を見る。戻り値は終了コード（0 なら止めない）。"""
    # **置き場は site.py の1か所から取る。** ここに書き直さない
    url = base.rstrip("/") + "/" + site.INDEX_PATH
    print("取りに行く: %s" % url)
    code, body, _ctype = 取りに行く(url)

    if code == 0:
        print("::error::配信につながらない。%s" % body)
        print("Pages が止まっているか、入口のURLが実物と違う")
        return 1
    if code in (301, 302, 303, 307, 308):
        print("::error::配信が %d で飛ばした。**追わない**。" % code)
        print("www と本体のどちらか一方だけを GitHub が主張している。")
        print("飛ばされない側を入口にすること")
        return 1
    if code != 200:
        print("::error::配信が返ってこない（%d）。%s" % (code, url))
        return 1

    try:
        d = json.loads(body)
    except ValueError as e:
        print("::error::配られているものが JSON として読めない（%s）" % e)
        print("Pages が別のもの（404ページなど）を配っている")
        return 1

    # **いちばん出してはいけないもの。**
    # 物件一覧は入札中の情報で、人が住んでいる建物を含む。
    # 1件1行のデータは公開側に出さない（正本 1節）。
    # 手前の検査は「出すつもりのもの」しか見ないので、ここで実物を見る
    if "records" not in d:
        print("::error::配られている index.json に records が無い。形が違う")
        return 1
    records = d["records"]
    if records:
        print("::error::**配られている index.json に個票が %d 件入っている。**"
              % len(records))
        print("::error::すぐ Pages を止めて、何が出たかを数えること")
        return 1

    町 = d.get("counts_by_city") or []
    # **升の数と市区町村の数は別**（正本 6節。升は city_code × kind × period）。
    # 1つの市が種別と月の数だけ升に分かれるので、升を数えて「市区町村」と
    # 名乗ると、報告に出す数がそのぶんだけ大きくなる。
    # 実測（2026-09-20）: 升 92 を「市区町村 92」と名乗っていた。本当は 46。
    # **数えたものの名前で名乗る**（DESIGN「名乗れる語だけで数える」）
    市 = {m.get("city_code") for m in 町 if isinstance(m, dict)}
    市.discard(None)
    市.discard("")
    print("配られているもの: 升 %d / 市区町村 %d / records 0（からっぽ）/ %s"
          % (len(町), len(市), d.get("generated_at") or "（日付なし）"))
    return 0


def main(argv):
    # **空の引数は「渡していない」と同じ扱い。**
    # workflow の入力欄は、押した人が何も書かないと空文字で渡ってくる。
    # そこで止めると、毎朝の分まで「URLが変だ」と言い出す
    base = (argv[1] if len(argv) > 1 else "").strip() or site.base_url()
    if not base:
        # **鳴らない見張りにしない**（正本 3.3）。
        # ⑤ Pages がまだなら配信は無い。毎朝赤にすると、
        # 鳴らなくなるのではなく**見られなくなる**
        print("入口のURLがまだ空。配信はまだ始まっていない。ここは見ない")
        return 0
    # **2つとも見る。片方だけ通っても足りない。**
    # 機械向けのファイルが配れていても、人が来る1枚が404なら
    # 来た人は何も読めない。逆も同じ
    return 入口を見る(base) or 見る(base)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
