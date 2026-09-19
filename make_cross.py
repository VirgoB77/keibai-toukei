#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""姉妹サイトに渡す「跡地」の横断ファイルを作る。

    出したもの: data/cross/atochi.json

学校跡地・庁舎跡地は、競売にも公売にも出ない。自治体や国が自分の財産として
一般競争入札で売るもので、滞納処分による公売とは別の制度。
このファイルで拾うのは「**法人が使っていた工場・倉庫・店舗などが売りに出た**」ほう。
工場跡地が売れた数年後に、そこに大型店の届出が出る——という線を、
姉妹サイト（大型店日報）と町丁目の鍵でつなぐためのもの。

--------------------------------------------------------------------------
入れる条件（ぜんぶ満たすものだけ）
--------------------------------------------------------------------------

本当の関門は「**人が住んでいないか**」と「**売却が済んでいるか**」の2つ。
面積はその代理でしかないので、居住用途は名指しで落とす。

  必ず落とす（1つでも当たれば入れない）
   - 建物用途に 居宅・共同住宅・アパート・マンション・寄宿舎・長屋・住宅 を含む
   - 種別が「マンション」「区分所有」
   - 用途地域が住居系
   - 売却が済んでいない（入札中・入札予定）

  残す（ぜんぶ満たすもの）
   - 種別が「土地」または「土地建物」
   - 現況または建物用途が 工場・倉庫・店舗・事務所・ホテル・病院 など
   - 用途地域が工業系または商業系
   - 土地面積が **500平米以上**

500平米には理屈がある。大阪・兵庫の都市部（近畿圏の既成市街地等）では、
**開発許可が要るのが500平米から**（都市計画法施行令19条1項）。
それ未満の土地は、あとで開発されても記録に残らないので、
跡地として拾っても「その後」の線が引けない。
市によっては条例で300平米まで下げているところがあるので、
確認できた市町村は common/kaihatsu_kibo.json の数字を使う（低いほうに合わせる）。

「売却が済んでいるものだけ」も大事。まだ売れていない物件を固定化すると、
そこに人がいる可能性のあるものを、よそのサイトに焼き付けてしまう。

所有者名（party）は出さない。裁判所も税務署も所有者名を公表していないので、
法人かどうかを確かめようがない。**確かめられないものは出さない。**

住所は町丁目まで。地番は出さない。鍵も粗いほう（addr_key_town）だけ。

--------------------------------------------------------------------------
いまは出力を止めてある
--------------------------------------------------------------------------

BIT・国税庁・自治体の利用規約の確認が済むまで、ファイルを書かない。
コードとテストは先に作ってあるので、確認が済んだら環境変数だけで開く。

    ATOCHI=on python3 make_cross.py

止まっている理由は data/terms/ の規約メモと README に書いてある。
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import aggregate  # noqa: E402  段階と結果の語は aggregate が持つ
from common import privacy  # noqa: E402
from common import site  # noqa: E402
from common.jst import today_str  # noqa: E402
from common.addr import normalize  # noqa: E402

# site には**このサイトの名前**を入れる（正本 6節）。公開先の置き場の名前ではない
SITE = os.environ.get("SITE") or site.SITE["site_id"]
PREFIX = os.environ.get("SITE_PREFIX") or site.id_prefix()
BASE_URL = os.environ.get("SITE_URL") or site.SITE.get("site_url") or ""
OUT_PATH = os.path.join(HERE, "data", "cross", "atochi.json")
ROWS_DIR = os.path.join(HERE, "data", "rows")

# 規約の確認が済むまで false。開けるのは人の判断で
ENABLED = os.environ.get("ATOCHI", "").lower() in ("on", "1", "true", "yes")

KIND_OK = ("土地", "土地建物")
KIND_NG = ("マンション", "区分所有")
USE_OK = re.compile(r"工場|倉庫|店舗|事務所|ホテル|旅館|病院|診療所|事業所")
ZONING_OK = re.compile(r"工業|商業")

# 人が住んでいる建物の呼び名。1つでも当たれば入れない。
# 「店舗兼住宅」のように事業用の語と混じっていても、落とすほうを採る
USE_NG = re.compile(r"居宅|共同住宅|アパート|マンション|寄宿舎|長屋|住宅|"
                    r"住居|戸建|宿舎")
# 住居系の用途地域はすべて名前に「住居」が入る
# （第一種低層住居専用地域〜準住居地域、田園住居地域）
ZONING_NG = re.compile(r"住居")

# **語は aggregate から借りる。写さない**（正本 9節「数えるのは1か所だけ」）。
# 前はここに同じ並びを書き写していたので、`aggregate.SOLD` に語を1つ足しても
# 跡地の横断ファイルには効かなかった。**語彙が2か所にあると、必ず片方が古くなる。**
SOLD = aggregate.SOLD


def _load_kibo():
    """開発許可が要る広さ。確認できた市町村の数字と、既定値を返す。"""
    path = os.path.join(HERE, "common", "kaihatsu_kibo.json")
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d.get("default_sqm", 500), d.get("city_overrides", {})
    except (OSError, ValueError):
        return 500, {}


DEFAULT_SQM, CITY_SQM = _load_kibo()


def min_sqm(city_code):
    """その市区町村で、跡地として拾う下限。低いほうに合わせる。"""
    return CITY_SQM.get(city_code or "", DEFAULT_SQM)


def use_of(row):
    """現況または建物用途。書いてある場所が役所によって違うので順に見る。"""
    for k in ("use", "genkyo", "現況", "building_use", "kind_raw", "former_use"):
        v = (row.get(k) or "").strip()
        if v and USE_OK.search(v):
            return v
    return ""


# 競売・公売は、中身にかかわらず跡地に出さない。
# DESIGN 1章の決定（競売・公売の個票は公開しない・住所は市区町村までしか持たない）と
# 正本 3.1。工業地域の工場でも、競売の物件なら渡さない
PRIVATE_SYSTEMS = ("keibai", "kobai")


def is_residential(row):
    """人が住んでいる建物か。迷ったら「住んでいる」と答える側に倒す。

    判定そのものは privacy.py に置いてある。**出す値は必ずあそこを通す**（正本 5節）。
    ここでは、跡地だけに効く種別のふるい（マンション・区分所有）を足す。
    """
    if (row.get("kind") or "") in KIND_NG:
        return True
    return privacy.is_lived_in(row)


def is_atochi(row):
    """跡地として姉妹サイトに渡してよいか。

    落とすほうを先に見る。事業用の語と住まいの語が混じっていたら
    （「店舗兼住宅」など）、落とすほうを採る。
    """
    if row.get("system") in PRIVATE_SYSTEMS:
        return False
    if is_residential(row):
        return False
    if (row.get("status") or "") not in SOLD:
        return False
    if (row.get("kind") or "") not in KIND_OK:
        return False
    if not use_of(row):
        return False
    if not ZONING_OK.search(row.get("zoning") or ""):
        return False
    a = normalize(row.get("pref"), row.get("city"), row.get("address"))
    area = row.get("area_sqm")
    if not isinstance(area, (int, float)) or area < min_sqm(a["city_code"]):
        return False
    # 町丁目までの住所が無いものは出せない
    return bool(a["addr_key_town"])


def sold_date(row):
    """売却日。開札日 → 契約日 → 最後に見た日。"""
    for k in ("open_date", "contract_date", "sale_date", "last_seen"):
        if row.get(k):
            return row[k]
    return ""


def build(rows):
    """条件に合う行だけを、渡す形にして並べる。"""
    out, seq = [], {}
    for row in rows:
        if not is_atochi(row):
            continue
        a = normalize(row.get("pref"), row.get("city"), row.get("address"))
        d = sold_date(row)
        src = (row.get("sources") or [row.get("system") or ""])[0]
        seq[(src, d)] = seq.get((src, d), 0) + 1
        key = re.sub(r"[^A-Za-z0-9._-]", "-", str(row.get("key") or ""))
        out.append({
            # **id の頭は接頭辞。site_id ではない**（正本 6節
            # 「接頭辞は site と同じでも短い別名でもよい。一致は求めない」）。
            # 1つ目が「どのサイトか」、2つ目が「競売か公売か」で役割が違う
            "id": "%s:%s:%s:%d" % (PREFIX, src, d, seq[(src, d)]),
            "kind": "跡地/%s" % (row.get("kind") or "その他"),
            "date": d,
            "city_code": a["city_code"],
            "city": a["city"],
            # 共通仕様は undisclosed なら地番まで許すが、
            # 跡地ファイルは**いつでも町丁目まで**にしてある。厳しいぶんは問題ない
            "addr": privacy.to_town(a["addr"], a["town"]),
            "addr_key_town": a["addr_key_town"],
            "use": use_of(row),
            "area_sqm": row.get("area_sqm"),
            "url": "%s%s/%s.html" % (BASE_URL, row.get("system"), key)
                   if key else "",
            "source_url": row.get("source_url") or "",
            "fetched_on": row.get("last_seen") or row.get("first_seen") or "",
        })
    out.sort(key=lambda r: (r["date"], r["id"]), reverse=True)
    return {
        "site": SITE,
        "generated_at": today_str(),
        "何これ": "法人が使っていた工場・倉庫・店舗などの跡地。売却済みのものだけ",
        "所有者名": "出さない（公表されていないので法人か確かめようがない）",
        "住所": "町丁目まで。地番は出さない",
        "records": out,
    }


def load_rows():
    rows = []
    if not os.path.isdir(ROWS_DIR):
        return rows
    for system in sorted(os.listdir(ROWS_DIR)):
        d = os.path.join(ROWS_DIR, system)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if not name.endswith(".json"):
                continue
            with open(os.path.join(d, name), encoding="utf-8") as f:
                data = json.load(f)
            items = data if isinstance(data, list) else data.get("rows", [])
            for r in items:
                r.setdefault("system", system)
                rows.append(r)
    return rows


def main():
    rows = load_rows()
    cross = build(rows)
    if not ENABLED:
        print("跡地ファイルは止めてある（規約の確認待ち）。"
              "条件に合ったのは %d 件。出すときは ATOCHI=on を付ける"
              % len(cross["records"]))
        return
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(cross, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("跡地 %d 件を出した" % len(cross["records"]))


if __name__ == "__main__":
    main()
