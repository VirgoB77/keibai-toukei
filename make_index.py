#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""姉妹サイトと突き合わせるための index.json を作る。

鯨屋（くじらや）の3サイト——大型店日報・競売公売・開発届出——は、
それぞれ index.json を同じ形で出す。市区町村コードと住所の鍵（addr_key）が
そろっているので、あとから「この土地について、3つのサイトが何を言っているか」を
1つのページにまとめられる。

    python3 make_index.py

出したもの: data/public/index.json
（公開リポジトリへ送るのは**公開用の Actions**の仕事。公開用はまだ作っていない）

--------------------------------------------------------------------------
だれの話を個票で出すか（いちばん大事なところ）
--------------------------------------------------------------------------

index.json に1件ずつ載せるのは、次のどちらかを満たすものだけ。

  (a) 所有者・落札者が法人名義（株式会社・有限会社・合同会社など）
  (b) 物件の用途が 店舗・事務所・工場・倉庫・商業地・工業地 のいずれか

それ以外（個人名義の居宅・区分マンションなど）は1件ずつ載せず、
市区町村ごとの件数だけを counts_by_city に入れる。
個人名・債務者名は party に入れない（法人名だけ）。

さらに、競売と公売は**中身にかかわらず個票を出さない**。
差押えや滞納は誰かの不幸で、設計書（DESIGN 1.3 / 1.4）で
「個票は公開しない・住所は市区町村までしか持たない」と決めているため、
(a)(b) を判定する材料（所有者名・詳しい用途・地番）がそもそも手元に無い。
競売・公売は全部 counts_by_city に入る。

個票が出るのは国有財産と公有財産。売り手が役所自身で、個人情報がない。
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from aggregate import FAMILIES, INDEX_FIELDS  # noqa: E402
from aggregate import aggregate as make_cells  # noqa: E402
from aggregate import stage_of  # noqa: E402
from aggregate import unresolved as aggregate_unresolved  # noqa: E402
from aggregate import undecided as aggregate_undecided  # noqa: E402
from aggregate import gone as aggregate_gone  # noqa: E402
from common import privacy  # noqa: E402
from common import report  # noqa: E402
from common import site  # noqa: E402
from common.jst import today_str  # noqa: E402
from common.addr import normalize  # noqa: E402
from common.shukei import yoyuu  # noqa: E402

# site は**このサイトの名前**であって、公開先の置き場の名前ではない。
# 正本 6節の id は `<site>:<source>:<date>:<連番>` で「サイトをまたいで衝突しないこと」。
# ic-log は、公開先として書いてあった既存のリポジトリの名前（いまは採らない）。
# 開発系サイトの生成物も同じ場所に入る予定なので、site に使うと衝突する。
# 名乗りは common/site.json の1か所から配る（正本 3.4）。
SITE = os.environ.get("SITE") or site.SITE["site_id"]
PREFIX = os.environ.get("SITE_PREFIX") or site.id_prefix()
SITE_NAME = os.environ.get("SITE_NAME", "競売統計")
# **退役した置き場のURLを書き置かない**（正本 9節）。公開先が決まるまでは空。
# 空なら個票のURLを出さない（いま records は0本なので空で困らない）
BASE_URL = os.environ.get("SITE_URL") or site.SITE.get("site_url") or ""

ROWS_DIR = os.path.join(HERE, "data", "rows")
OUT_PATH = os.path.join(HERE, "data", "public", "index.json")

# 差押え・滞納の段。中身にかかわらず個票を出さない
PRIVATE_SYSTEMS = ("keibai", "kobai")

# 事業用の目印。ここに当たるものは、個人名義でも個票にしてよい
BUSINESS_USE = re.compile(r"店舗|事務所|工場|倉庫|商業地|工業地")

# 段ごとの制度名。index.json の kind は <制度>/<種別> の形にする（正本 6節）。
# 正本の例が「公有地売却/落札」なので、後ろは物件の種類ではなく**段階**を書く。
# 物件の種類（土地・マンション）は集計のほうで別の軸として持っている。
SYSTEM_LABEL = {"keibai": "競売", "kobai": "公売",
                "kokuyu": "国有財産", "koyu": "公有財産"}


def corp_name(name):
    """法人名ならそのまま返す。個人名・空なら空文字を返す。

    中身は common/privacy.py。**出す値は必ずあちらを通す**（正本 5節）。
    """
    return privacy.party_for_index(name)


def is_business_use(row):
    """用途が事業用か。種別・原文・用途地域・跡地の用途のどれかで見る。"""
    text = " ".join(str(row.get(k) or "") for k in
                    ("kind", "kind_raw", "zoning", "former_use", "title"))
    return bool(BUSINESS_USE.search(text))


def shows_detail(row):
    """この1件を index.json に個票として出してよいか。

    競売・公売は、中身にかかわらず出さない（このファイルの冒頭を見よ）。

    **落とすほうを先に見る。** 正本 3.1「人が住んでいる可能性があるものは、
    個票として扱わない（競売・公売の入札中物件、居住用途の建物、
    住居系用途地域）」。法人が買った土地でも、そこに居宅が建っていれば
    住んでいる人がいる。買い手が誰かと、住んでいる人がいるかは別の話。
    """
    if row.get("system") in PRIVATE_SYSTEMS:
        return False
    if privacy.is_lived_in(row):
        return False
    return bool(corp_name(row.get("winner_name")) or is_business_use(row))


def pick_date(row):
    """その1件を並べるときの日付。開札日 → 入札締切 → 最初に見た日 の順。"""
    for k in ("open_date", "bid_end", "bid_start", "first_seen"):
        v = row.get(k)
        if v:
            return v
    return ""


def make_title(row):
    """一覧に出す見出し。個人が特定できる言葉は入れない。"""
    parts = [row.get("city") or row.get("pref") or "",
             row.get("former_use") or "",
             row.get("kind") or ""]
    title = " ".join(p for p in parts if p).strip()
    return title or (row.get("seller") or "")


def detail_url(row):
    """詳細ページのURL。個票ページは Phase 4 で作る。"""
    system, key = row.get("system"), row.get("key")
    if not system or not key:
        return ""
    safe = re.sub(r"[^A-Za-z0-9._-]", "-", str(key))
    return "%s%s/%s.html" % (BASE_URL, system, safe)


def load_rows():
    """data/rows/<段>/*.json を全部読む。まだ無ければ空。"""
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


def build(rows, today=None):
    """行データから index.json の中身を組み立てる。"""
    today = today or today_str()
    records, seq = [], {}
    # 切れた法人名は「同じデータの中の別の名前の先頭か」で見分けるので、
    # 先に全部の名前を集めておく
    names = [r.get("winner_name") for r in rows if r.get("winner_name")]

    for row in rows:
        a = normalize(row.get("pref"), row.get("city"), row.get("address"))
        code = a["city_code"]

        if not shows_detail(row):
            continue     # 個票にはしない。件数は下の counts_by_city で数える

        src = (row.get("sources") or [row.get("system") or ""])[0]
        d = pick_date(row)
        seq[(src, d)] = seq.get((src, d), 0) + 1
        kind, _reason = privacy.classify_party(row.get("winner_name"), names)
        corp = kind == privacy.CORP
        records.append({
            # **id の頭は接頭辞。site_id ではない**（正本 6節
            # 「接頭辞は site と同じでも短い別名でもよい。一致は求めない」）。
            # 1つ目が「どのサイトか」、2つ目が「競売か公売か」で役割が違う
            "id": "%s:%s:%s:%d" % (PREFIX, src, d, seq[(src, d)]),
            "title": make_title(row),
            "kind": "%s/%s" % (SYSTEM_LABEL.get(row.get("system"), "その他"),
                               stage_of(row)),
            "date": d,
            "pref": a["pref"],
            "city": a["city"],
            "city_code": code,
            # town を渡すのは、丁目を落とさないため（正本 4節・privacy.to_town）
            "addr": privacy.redact_addr(
                a["addr"], privacy.CORP if corp else privacy.INDIVIDUAL,
                a["town"]),
            "addr_key": a["addr_key"] if corp else "",
            "addr_key_town": a["addr_key_town"],
            "party": corp_name(row.get("winner_name")),
            # party が空文字のとき、伏せたのか当事者がいないのかを機械に伝える
            # undisclosed を名乗れるのは「名前の欄が無い」と**確かめた**出どころだけ。
            # 確かめていないものは individual（町丁目まで）に倒す。
            # 読み落とした列が undisclosed に化けて地番が出る経路を塞ぐ。
            #
            # **行データが名乗る party_kind をそのまま通さない。**
            # 前は `row.get("party_kind") or ...` だったので、行データに
            # "undisclosed" と書いてあれば検査を飛ばして出ていた。
            # 出す値は必ず privacy.py を通す（正本 5節「通さない経路を作らない」）
            "party_kind": privacy.classify_party(
                row.get("winner_name"), names,
                disclosed=not privacy.name_absent_confirmed(
                    row.get("name_column")))[0],
            "url": detail_url(row),
            "source_url": row.get("source_url") or "",
            "fetched_on": row.get("last_seen") or row.get("first_seen") or "",
        })

    records.sort(key=lambda r: (r["date"], r["id"]), reverse=True)

    # 升は city_code × kind × period の3本で決まる（正本 6節）。**1要素＝1升。**
    # 物件の種別はこの3本に書く場所が無いので、ここでは畳んで数え直す
    # （種別ごとの内訳は data/agg/monthly.json に残る）。
    # 集計そのものは aggregate.py で行う。2か所で別々に数えない
    #
    # **個票に出した行は、ここで数えない**（正本 6節）。
    # 個票は番地まで、升は市区町村まで。同じ行を両方に出すと、
    # 粗さの違う親と子を両方出すことになり、引き算で伏せた升が戻る。
    # 実測（架空データ）：国有財産4行のうち3行が個票に出ると、
    # 升が実数4を出し、読者が数えられる個票が3で、4−3=1 と残りが確定した。
    #
    # **個票に出さなかった行は、升に残す**（正本 9節「黙って捨てない」）。
    # だから制度（system）ごとに丸ごと外すのではなく、行ごとに shows_detail で分ける。
    # 制度で外すと、同じ制度の中の「個票にしないと決めた行」まで消える。
    counted = [r for r in rows if not shows_detail(r)]
    everything = make_cells(counted, INDEX_FIELDS, with_raw=True)
    cells = [c for c in everything if c.get("city_code")]
    # 市区町村コードが引けない升は index に出せない（升の3本のうち1本が空になる）。
    # **黙って捨てない。** 落ちているものは落ちていると分かる形で残す（正本 9節）
    # 控えは counted だけでなく全行から作る。個票に出した行で
    # 市区町村コードが引けないものも、控えに残さないと黙って消える
    dropped = [c for c in make_cells(rows, INDEX_FIELDS, with_raw=True)
               if not c.get("city_code")]

    # **親の升を出さない**（正本 3.2「合計の升と、内訳の升を、両方出さない」）。
    # 理由は2つあって、どちらも同じ直し方になる。
    #
    # 1. 引き算で戻る。結果 ＝ 結果-落札 ＋ 結果-不調 なので、
    #    「結果6 − 結果-落札4 ＝ 2」で伏せた升の正確な値が出る（値は架空）
    # 2. 足し算が二重になる。公告-新規は公告の**内数**なので、
    #    並べて出すと「公告66 ＋ 公告-新規66 ＝ 132」と読める（物件は106件）
    #
    # 親を出さなければ、残る升は互いに重ならず、足し算がそのまま正しくなる。
    # 合計（公告・結果）が要る読者は、子を足せばよい（正本 3.2 172-173行）。
    drop = {id(c) for c in cells if FAMILIES.is_parent(c["stage"])}

    by_city = []
    for cell in cells:
        if id(cell) in drop:
            continue
        by_city.append({
            "city_code": cell["city_code"],
            "city": cell["city"],
            "kind": "%s/%s" % (SYSTEM_LABEL.get(cell["system"], "その他"),
                               cell["stage"]),
            "period": cell["ym"],
            "count": cell["count"],
            "count_label": cell["count_label"],
        })
    by_city.sort(key=lambda c: (c["city_code"], c["kind"], c["period"]))
    return {
        "site": SITE,
        "site_name": SITE_NAME,
        "generated_at": today,
        "records": records,
        "counts_by_city": by_city,
        # **升にしていない行の数**（正本 9節・2026-09-19）。
        # kind に出すと、横断ハブで4サイトの「不明」が1つの塊になる。
        # 競売の不明は「どの段階にも入らなかった」、大型店の不明は
        # 「設置者の欄が読めなかった」。意味の違うものが束ねた数だけ独り歩きする。
        # **升ではないので、市区町村も種別も月も付かない。数だけ。**
        # 0 なら 0 と書く（黙って捨てていないことが分かる）。
        #
        # **2つを分ける。混ぜると、語彙の穴がいくつあるのかが読めなくなる。**
        #   unresolved  読めなかった。語彙の穴。**こちらが減らす**
        #   undecided   読めている。置き場が正本で決まっていない。**こちらでは減らせない**
        #
        # 欄の名前は正本6節にまだ無い。**blessing 待ち**（docs/seihon-toiawase.md）
        "not_counted": {
            "unresolved": sum(1 for r in rows if aggregate_unresolved(r)),
            "undecided": sum(1 for r in rows if aggregate_undecided(r)),
            # 消えた。**取下げか繰り越しか、再登場を待たないと決められない**
            "gone": sum(1 for r in rows if aggregate_gone(r)),
        },
        "_dropped": dropped,      # 呼ぶ側が人に知らせるためのもの。出力からは外す
        "_yoyuu": measure_yoyuu(cells, drop),
    }


def measure_yoyuu(cells, drop):
    """まとまりごとの余裕を測る（正本 3.2「余裕も出す」）。

    **真の件数が要るので、ここでしか測れない。** `by_city` は `_n` を
    落としたあとなので、そちらでは測れない（落としてあるのは設計どおり）。

    まとまりの取り方は2つ。どちらも「親が1つ出たら、その中の伏せた升が
    引き算で狭まる」関係にある。

        市区町村 × 月   … 段階をまたいだ合計が出たら狭まる
        段階 × 月       … 府県や全体の合計が出たら狭まる

    `k` が 1 のまとまりは、**親が1度どこかに出た瞬間に確定する。**
    記事や SNS も「どこか」に入る。
    """
    live = [c for c in cells if id(c) not in drop]
    out = []
    for name, key in (("市区町村×月", lambda c: (c["city_code"], c["city"], c["ym"])),
                      ("段階×月", lambda c: (c["stage"], c["ym"]))):
        groups = {}
        for c in live:
            groups.setdefault(key(c), []).append(c.get("_n") or 0)
        for k2 in sorted(groups):
            d = yoyuu(groups[k2])
            if d["k"]:
                out.append({"まとまり": name, "升": list(k2), **d})
    return out


YOYUU_PATH = os.path.join(HERE, "data", "yoyuu.md")


def write_yoyuu(rows):
    """余裕を、人が見られるところに書き出す。余裕0のまとまりの数を返す。

    **値はここに置く。決定は docs/kiji-no-tane.md に置く。**
    余裕そのもの（k と m）を公開側に書くと、m が出て組合せが減る。
    このファイルは公開しない（先頭の1行と tests/test_public.py が見張る）。
    """
    # **当てる組合せが1通りしかないまとまりは、親を出さない。例外なし**（正本 3.2）
    tight = [r for r in rows if r["組合せ"] == 1]
    lines = [report.not_public("伏せた升の余裕"), ""]
    lines += [
        "正本 3.2「**「引き算で戻る升 0」だけでは足りない。余裕も出す**」。",
        "",
        "戻る升を数えて0になっても、いまのデータでぎりぎり成り立っている",
        "だけかもしれない。升が減る・件数が増えて伏せる升が減る・月が1つ増える。",
        "どれでも同じ作りのまま戻るようになる。",
        "",
        "    k    伏せた升の数",
        "    m    そのうち2件だった升の数",
        "    余裕 = min(m, k − m)",
        "",
        "親の合計から引けば伏せた升の**和**は出るので、`m` は確定すると思ってよい。",
        "守っているのは和ではなく「**どの m 個が2件か**」の組合せのほう。",
        "**`k` が1なら、和が分かった時点で確定する。**",
        "",
        "**足してから測るのではなく、足す前に測る。**",
        "年・市・種別を足すときは、足す前にここを見ること。",
        "",
        "| まとまり | k | m | 余裕 | 組合せ |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for r in sorted(rows, key=lambda r: (r["まとまり"], r["余裕"], r["k"])):
        lines.append("| %s %s | %d | %d | **%d** | %d |"
                     % (r["まとまり"], "／".join(str(x) for x in r["升"]),
                        r["k"], r["m"], r["余裕"], r["組合せ"]))
    lines += [
        "",
        "## 当てる組合せが1通りしかないまとまり",
        "",
        "正本 3.2「**当てる組合せが1通りしかないまとまりは、親を出さない。"
        "例外なし。**」（2026-09-18）。",
        "`C(k, m) = 1` は「伏せた升がすべて確定する」という意味で、"
        "伏せていないのと同じ。**`k = 1` は常にこれに当たる。**",
        "",
        "    k=1   → 1通り        確定する",
        "    k=2   → 最大 2通り    ほぼ確定する",
        "    k=4   → 最大 6通り",
        "    k=10  → 最大 252通り",
        "    k=20  → 最大 184,756通り",
        "",
        "**そのまとまりの親（合計）が1度でもどこかに出たら、"
        "中の伏せた升が全部そのまま決まる。**",
        "「どこか」には記事も SNS も入る。`index.json` に合計欄が無いことは",
        "`tests/test_public.py` が見張っているが、**記事は機械では止まらない。**",
        "",
        "いま組合せが1通りのまとまり: **%d / %d**。" % (len(tight), len(rows)),
        "",
        "**しきい値はまだ無い。** まとまりの性質がサイトによって違うので、",
        "4サイトの実測が出そろってから決まる（正本 3.2）。",
        "それまでは**親を出さない側に倒す**。出さない判断のほうが、あとから戻せる。",
        "",
        "## だから出さないもの（`docs/kiji-no-tane.md` の表と同じ）",
        "",
        "- **市区町村ごとの合計**（段階をまたいで足した数）",
        "- **段階ごとの合計**（府県計・全体計）",
        "- 裁判所ごとの物件数の合計（`data/agg/shuroku.json` の「物件」）",
        "",
        "子（内訳）だけを出す。読者が足すのは構わない。"
        "**こちらが足して見せると、伏せた升が戻る。**",
    ]
    with open(YOYUU_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip("\n") + "\n")
    return len(tight)


RATIO_PATH = os.path.join(HERE, "data", "jissuu-ritsu.md")

# 地図に色を塗る単位。**升が出た市ではなく、塗るはずの市ぜんぶ。**
OUR_PREFS = ("大阪府", "兵庫県")


def map_units():
    """地図に色を塗る単位の数（政令市は区で数え、親の市は数えない）。

    大阪市・堺市・神戸市は、それ自身と区の両方が市区町村コードの表に載っている。
    升は区で立つので、親の市まで数えると分母が3つ増える。
    """
    with open(os.path.join(HERE, "common", "city_codes.json"),
              encoding="utf-8") as f:
        cities = json.load(f)["cities"]
    ours = [c for c in cities if c["pref"] in OUR_PREFS]
    # 区を持っている市を探す。「大阪市」＋「大阪市西区」のように、
    # 名前の頭が市の名前で、末尾が「区」のものがあれば、その市は親
    parents = set()
    for c in ours:
        if not c["city"].endswith("区"):
            continue
        for p2 in ours:
            if c is not p2 and c["city"].startswith(p2["city"]):
                parents.add((p2["pref"], p2["city"]))
    return [c for c in ours if (c["pref"], c["city"]) not in parents]


def shown_ratio(by_city, units):
    """層（kind）ごとに、実数が出せた升の割合を数える。

    **正本 3.2「判定は『実数が出せた升の割合』で見る」**（2026-09-17 に入った）。
    伏せ字の割合で機械判定すると、本当に0件ばかりの層がすり抜ける。
    街頭窃盗統計のひったくりは伏せ字 12.7% で、実数が出せた升は 0.7% しかなかった。

    **分母は地図に色を塗る単位。** 「データがあった市」を分母にすると、
    見ていない市が消えて判定が甘くなる。
    """
    n_units = len(units)
    per = {}
    for c in by_city:
        d = per.setdefault(c["kind"], {"実数": 0, "伏せ字": 0, "升の0": 0})
        if c["count"] is None:
            d["伏せ字"] += 1
        elif c["count"] == 0:
            d["升の0"] += 1
        else:
            d["実数"] += 1
    for kind, d in per.items():
        d["升あり"] = d["実数"] + d["伏せ字"] + d["升の0"]
        # **「升なし」は「0件」ではない。** 見ていないところにも升は立たない
        # （data/agg/shuroku.json）。混ぜると、正本 3.2 が分けろと言っている
        # 2つを混ぜることになる
        d["升なし"] = n_units - d["升あり"]
        d["実数の割合"] = (100.0 * d["実数"] / n_units) if n_units else 0.0
    return per


def write_ratio(by_city, units):
    """実数が出せた升の割合を、人が見られるところに書き出す。"""
    per = shown_ratio(by_city, units)
    lines = [report.not_public("実数が出せた升の割合"), ""]
    lines += [
        "正本 3.2「ほとんどが伏せ字になる層は、出し方を考える」。",
        "**判定は「伏せ字の割合」ではなく「実数が出せた升の割合」で見る**"
        "（2026-09-17 に正本が直った）。",
        "伏せ字の割合で機械判定すると、本当に0件ばかりの層がすり抜ける。",
        "街頭窃盗統計のひったくりは伏せ字 12.7%・本当に0件 86.6% で、",
        "実数が出せた升は 0.7% しかなく、7手口すべてがすり抜けた。",
        "",
        "分母は**地図に色を塗る単位**（%s の %d 区市町）。"
        % "・".join(OUR_PREFS) % len(units) if False else
        "分母は**地図に色を塗る単位**（%s の %d 区市町）。"
        % ("・".join(OUR_PREFS), len(units)),
        "「データがあった市」を分母にすると、見ていない市が消えて判定が甘くなる。",
        "",
        "**「升なし」は「0件」ではない。** 見ていないところにも升は立たない。",
        "どこを見たかは `data/agg/shuroku.json`。",
        "",
        "| 層 | 実数 | 伏せ字 | 升の0 | 升なし | **実数の割合** |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for kind in sorted(per):
        d = per[kind]
        lines.append("| `%s` | %d | %d | %d | %d | **%.1f%%** |"
                     % (kind, d["実数"], d["伏せ字"], d["升の0"],
                        d["升なし"], d["実数の割合"]))
    lines += [
        "",
        "## 割合が低い層をどうするか（正本 3.2 の4つ）",
        "",
        "1. **期間を長くまとめる**",
        "2. **粒度を市区町村に上げる**（ここは既に市区町村なので、府県まで上げる）",
        "3. **種別をまとめて1つの層にする**（まとめたら細かいほうは出さない）",
        "4. **その層は出さない**",
        "",
        "**境目の数字は正本に書かれていない。** 手がかりは正本に載っている実物2つだけ。",
        "",
        "| | 実数の割合 | 正本の扱い |",
        "| --- | ---: | --- |",
        "| 街頭窃盗統計 ひったくり（町丁目） | 0.7% | 出せない。市区町村に上げた |",
        "| 街頭窃盗統計 車・バイク（町丁目） | 69.7% | 出せる |",
        "",
        "**決まるまで、このサイトは地図を出さない。** 境目を自分で決めない"
        "（正本 11節）。",
    ]
    with open(RATIO_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines).rstrip("\n") + "\n")
    return per


DROPPED_PATH = os.path.join(HERE, "data", "index-dropped.md")


def write_dropped(dropped):
    """index に出せなかった升を、人が見られるところに書き出す（正本 9節）。

    **黙って捨てない。** 落ちているものは落ちていると分かる形で残す。
    黙って捨てると、市区町村の書き方がずれていることに何年も気づかないまま、
    歯抜けの集計が積み上がる。
    """
    lines = [report.not_public("index.json に出せなかった升")]
    if not dropped:
        lines.append("無かった。")
    else:
        lines += [
            "市区町村コードが引けなかったので `counts_by_city` に出していない。",
            "升は `city_code × kind × period` の3本で決まるので、"
            "1本でも空だと升にならない。",
            "**推測でコードを埋めない**（正本 4節）。",
            "`common/city_codes.json` にその市区町村があるか、"
            "`pref` / `city` の書き方が合っているかを見ること。",
            "",
            "| 都道府県 | 市区町村 | 段階 | 月 | 件数 |",
            "| --- | --- | --- | --- | --- |",
        ]
        for c in dropped:
            lines.append("| %s | %s | %s | %s | %s |"
                         % (c.get("pref") or "（空）", c.get("city") or "（空）",
                            c.get("stage"), c.get("ym"), c.get("count_label")))
    lines.append("")
    with open(DROPPED_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    rows = load_rows()
    index = build(rows)
    dropped = index.pop("_dropped", [])
    yoyuu_rows = index.pop("_yoyuu", [])
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
        f.write("\n")
    write_dropped(dropped)
    tight = write_yoyuu(yoyuu_rows)
    if tight:
        print("**当てる組合せが1通りのまとまり: %d 個**。"
              "親を出さない（例外なし。正本 3.2）（data/yoyuu.md）" % tight)
    units = map_units()
    per = write_ratio(index["counts_by_city"], units)
    for kind in sorted(per):
        d = per[kind]
        print("  %s: 実数が出せた升 %d / %d（%.1f%%）"
              % (kind, d["実数"], len(units), d["実数の割合"]))
    if dropped:
        print("**市区町村コードが引けず index に出せなかった升: %d 個**"
              "（data/index-dropped.md）" % len(dropped))
    print("行データ %d 件 → 個票 %d 件 / 件数だけ %d 市区町村"
          % (len(rows), len(index["records"]), len(index["counts_by_city"])))


if __name__ == "__main__":
    main()
