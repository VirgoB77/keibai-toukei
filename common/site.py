#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""名乗りと連絡先を、1か所から配る。

正本 3.4「URL は設定の1か所にだけ書き、公開したら about ページの URL に差し替える」。
中身は common/site.json。直すのはあちら。

名乗りの形（about ページが**まだ無い**あいだ）:

    kujiraya archive bot (<ua_label>; https://forms.gle/xxxxx)

about ページを公開したら、site.json の about_url を入れる。すると自動でこうなる:

    kujiraya archive bot (+https://.../about.html; https://forms.gle/xxxxx)

**404 になる URL は入れない。** 確認できない名乗りは、名乗らないより不審に見える。
相手のサーバー管理者が調べて404だったら、それだけでブロック候補になる。
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "site.json")

# **名前を持たせない。** ここに名前を書くと、site.json にその欄が無い日に
# 黙ってその名前で外に名乗ることになる。名前の正は site.json の1か所だけ。
#
# **2026-09-19 まで、ここに2つ名前が残っていた**（`bot_name` と `operator`）。
# 上にそう書いてあるのに、コードはそうなっていなかった。
# `bot_name` は**相手のサーバーに届く名乗り**そのもので、
# site.json から欄が消えても、ここから補われて動きつづける。
# 動くので誰も気づかない。**書いてある規則のほうを本当にした。**
_DEFAULT = {
    "bot_name": "",
    "site_id": "",
    "id_prefix": "",
    "ua_label": "",
    "contact_url": "",
    "about_url": "",
    "operator": "",
    "operator_note": "",
    "contact_note": "",
}

# **無ければ止まる欄。** 外に出ていく名乗りと、人が名乗る運営者。
# 「空のまま外に出る」より「今日は取りに行かない」ほうがよい（正本 3.4）
_要る = ("site_id", "bot_name", "contact_url", "operator")


def _load():
    """site.json を読む。**読めなければ止まる。**

    前は黙って `_DEFAULT` を返していた。そうすると、設定が壊れた日に
    **古い名前で、連絡先の無い名乗り**で相手のサーバーに出ていく。
    括弧の中が空の名乗りは、正本 3.4「確認できない名乗りは、名乗らないより
    不審に見える」そのもの。しかも**失敗した日にしか出ない**ので、
    テストでも手元の確認でも見えない。気づく先は相手のログの中だけ。

    **「取りに行かない日」を作るほうが、古い名前で行く日を作るよりましだ。**
    毎朝の workflow は `if: always()` でその朝の生データを先にしまうので、
    ここで止まっても取り直せないものは失われない。
    """
    try:
        with open(PATH, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError) as e:
        raise RuntimeError(
            "common/site.json が読めない（%s）。"
            "名乗りが作れないので、今日は取りに行かない。"
            "**古い名前で名乗るより、止まるほうがよい**（正本 3.4）" % e)
    out = dict(_DEFAULT)
    out.update({k: v for k, v in d.items() if not k.startswith("_")})
    欠け = [k for k in _要る if not out.get(k)]
    if 欠け:
        raise RuntimeError(
            "common/site.json に %s が無い。"
            "名乗りが作れないので、今日は取りに行かない。"
            "**既定値から補わない**（補うと、欄が消えた日に"
            "古い名前で外に出ていく）" % "・".join(欠け))
    return out


# **退役した名前。消さない**（正本 9節）。
# 現在値と比べる作りにしない。手で直した瞬間に old == new になり、
# 見張りが黙って空振りする。**一覧と比べる。**
RETIRED_NAMES = (
    "ic-log",        # 2026-09-17 退役。publish.sh の宛先として書いてあった置き場
    "keibai-data",   # 2026-09-18 退役。金庫は keibai-toukei-raw へ rename 済み
)


SITE = _load()


def contact_url():
    return SITE.get("contact_url") or ""


def about_url():
    return SITE.get("about_url") or ""


def id_prefix():
    """レコードの id の頭（正本 6節）。

    `<接頭辞>:<source>:<date>:<連番>`。**site_id と同じでなくてよい。**
    正本2節の表で衝突しないことだけが要件。
    """
    return SITE.get("id_prefix") or SITE.get("site_id") or ""


# 配るときの置き場（DESIGN「公開用の棚」）。
#
#     金庫   data/public/index.json   **しまう場所**（ここだけが公開してよい置き場）
#     公開用 data/index.json          **配る場所**（金庫から写したものだけ）
#
# 金庫の `public/` は「ここから先は出してよい」という仕切りの名前で、
# 配る側では意味が無い。**配る側の棚に内側の仕切りの名前を持ち込まない。**
#
# **URLはここ1か所にだけ書く**（正本 3.4）。
# 配信の確認も、姉妹サイトに伝える URL も、ここから作る。
INDEX_PATH = "data/index.json"


def index_url():
    """姉妹サイトに渡す一覧の URL。配信がまだなら空文字。"""
    b = base_url()
    return (b + INDEX_PATH) if b else ""


def base_url():
    """公開したサイトの入口。**末尾は必ず `/` にそろえて返す。**

    呼ぶ側は `base_url() + "keibai/xxx.html"` のように、そのままつなぐ。

    **つなぎ方を呼ぶ側に任せない。** site.json に `/` を付け忘れて
    `https://keibai-toukei.com` と入れると、つないだ先はこうなる:

        https://keibai-toukei.comkeibai/xxx.html

    **形としては正しいURLなので、検査を通って押せてしまう。**
    気づくのは、誰かが踏んで404になったとき。
    site_url を入れる日は⑤の直後で、いちばん急いでいる日になる。
    **その日に気づける形を、入れる前に置いておく。**

    配信がまだ無いあいだは空文字を返す（正本 3.4「404を入れない」）。
    空文字のときは、つないだ先が `keibai/xxx.html`（相対）になる。
    """
    u = (os.environ.get("SITE_URL") or SITE.get("site_url") or "").strip()
    if not u:
        return ""
    return u.rstrip("/") + "/"


def user_agent():
    """名乗り。about ページがあるときだけ、そのURLを入れる。

    about ページが無いあいだの頭は `ua_label`。**`site_id` ではない。**
    site_id は内部の鍵で、外に名乗る名前とは別の速さで決まる
    （site_id は records が0件のうちに、名乗りはドメインを検証してから）。
    `ua_label` が空なら site_id に落ちる。
    """
    head = about_url() or SITE.get("ua_label") or SITE.get("site_id") or "kujiraya"
    if about_url():
        head = "+" + head
    return "%s (%s; %s)" % (SITE.get("bot_name"), head, contact_url())
