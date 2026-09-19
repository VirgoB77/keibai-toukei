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
    """(HTTPの番号, 中身) を返す。つながらなければ (0, 理由)。"""
    opener = urllib.request.build_opener(_追わない)
    req = urllib.request.Request(url, headers={"User-Agent": site.user_agent()})
    最後 = ""
    for i in range(TRIES):
        try:
            with opener.open(req, timeout=TIMEOUT) as r:
                return r.getcode(), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            # 404 も 301 も「返ってきた」。数として持って帰る
            return e.code, ""
        except Exception as e:                     # noqa: BLE001 つながらない理由は何でも同じ扱い
            最後 = "%s: %s" % (type(e).__name__, e)
    return 0, 最後


def 見る(base):
    """配られている index.json を見る。戻り値は終了コード（0 なら止めない）。"""
    url = base.rstrip("/") + "/index.json"
    print("取りに行く: %s" % url)
    code, body = 取りに行く(url)

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
    print("配られているもの: 市区町村 %d / records 0（からっぽ）/ %s"
          % (len(町), d.get("generated_at") or "（日付なし）"))
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
    return 見る(base)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
