#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""行データを「市区町村 × 種別 × 月」の数字にする。

競売と公売は、個別の物件を出さない（DESIGN 1.3 / 1.4、README「個票を出さない」）。
そのかわり、ここで出す数字を厚くして「結果が残っている」ことを値打ちにする。

出すもの（升＝市区町村 × 種別 × 月 ごと）:

    count          件数
    base_median    売却基準価額の中央値
    sale_median    売却価額の中央値
    ratio_median   落札率（売却価額 ÷ 売却基準価額）の中央値
    unsold         不売・取消の件数

中央値にするのは、1件の高額物件で平均が壊れるため。
不売・取消は、ほかがどこも出していない。ここが効く。

--------------------------------------------------------------------------
3つのガード（崩さない）
--------------------------------------------------------------------------

1. **市区町村より下の粒度に下りない。** 町丁目・学区・地番では絶対に束ねない
2. **期間は月単位以上。** 週ごと・日ごとにしない
3. **1つの升が1〜2件のときは実数を出さず "1-2" とまとめる**

小さい町では、件数が1件と分かるだけで「あの家だ」と分かってしまう。
1と2は、そこへ近づく道を最初から塞ぐため。3は、塞ぎきれなかった分の最後の蓋。
このガードは tests/test_aggregate.py で固定してある。
"""

import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from common import privacy  # noqa: E402
from common import report  # noqa: E402
from common.shukei import Families, NOT_PUBLIC  # noqa: E402
from common.addr import city_code as lookup_city_code  # noqa: E402
from common.jst import today as jst_today  # noqa: E402
from common.jst import today_str  # noqa: E402

ROWS_DIR = os.path.join(HERE, "data", "rows")
OUT_PATH = os.path.join(HERE, "data", "agg", "monthly.json")

# 中央値を出すのに要る最少の件数。これ未満なら null
MIN_FOR_MEDIAN = 3

# 売れなかった・やめた、と数える status
# **不調と取下げを同じ欄に混ぜない**（README「数字の出し方」）。
# 不調は「開札して売れなかった」、取下げは「開札の前に消えた」。
# 混ぜると、このサイトの値打ちである「出したけれど売れなかった」が水増しになる。
# 実データでも 2026-10 の14回のうち5回が取消で、混ぜると不調が5回多く出る
UNSOLD = ("不売", "不落")

# **実物で見た語だけを入れる**（正本 9節「数えるまでは足さない」）。
# 2026-09-19 に数えた。物件の単位で見えたのは「取下」1語だけ。
# 予定表5日分・物件一覧2日分を当たって、執行停止・期日変更・続行決定・停止決定は
# **1件も無かった**（BITの画面に出ていない）。
#
# **「取消」をここに入れない。** 取消は**回**の単位の語で、物件の取下げとは別のもの。
# 回には city_code が付けようがないので升にならず、段階の語を要らない
# （回の状態は data/agg/kaisatsu.json の「状態」に別立てで出している）。
# 前はここに 取消・中止・変更 が入っていて、物件のカードに取消が出た日に
# 黙って取下げへ合流する形だった。**見る前に語彙を育てていた。**
#
# 知らない語が来たら、段階を作らずに data/parse-unknown.md に出る（events を見ること）。
WITHDRAWN = ("取下げ",)

# **一覧から消えた、まだ裏が取れていない。** 語彙が足りないのとは別のもの。
# parse.py の merge_snapshot が付ける。一覧から消えることは、このサイトが
# 取下げを見つける主な手段なので、**ここが「読めなかった語」に混ざると、
# 語彙の穴の数が読めなくなる**。
# 裏取り（BIT「取下げ等の検索」）が済んで取下げと確かめられたものだけを
# WITHDRAWN に入れる。確かめる前に取下げへ寄せない。
GONE = "消えた（裏取り待ち）"

SOLD = ("売却", "落札", "売却済", "契約済")

# 段階。**入札中と売却済みを同じ升に混ぜない**（正本 3.1 の但し書き）
#
#   公告      … その月に公告された**回**の数（新規＋再公告）。市場の厚み
#   公告-新規 … そのうち、その物件が初めて公告された回だけ。新しく出た担保
#   結果      … その月に開札された回の数（落札＋不調）。落札率の分母
#   結果-落札 … そのうち売れた回。落札率の分子
#   結果-不調 … そのうち売れなかった回
#
# **結果と結果-落札を分けるのが大事。** 「売れた件数」をレコード数で数えると、
# 不調まで混ざって水増しになる。姉妹サイトの実測では、兵庫県の県有地売払いで
# 82回中61回（74%）が不調だった。分けていないと4倍近く多く見える。
#
# **数えるのは回。物件ではない。** 競売には
#   9月 公告 → 10月 開札 → 不売 → 11月 また公告
# という流れがある。物件で数えると11月の公告が消えてしまう。
#
# **新規と合計を分けるのが大事。** 混ぜると、不売が続く不況期に
# 件数が勝手に増えて、逆の読み方になる。これがいちばんこわい間違い。
# 段階の言い方は姉妹サイト共通で **予定／公告／結果** の3つ。
# その中の内訳は「-」でつなぐ（公告-新規、結果-落札、結果-不調）。
KOKOKU, KOKOKU_NEW = "公告", "公告-新規"
KOKOKU_RE = "公告-再公告"   # 2回目以降の公告。新規と足すと公告になる
KEKKA = "結果"              # その月に開札された回（落札＋不調）
KEKKA_OCHI = "結果-落札"     # そのうち売れた回
KEKKA_FUCHO = "結果-不調"    # そのうち売れなかった回
# **取下げは段階にしない**（正本 9節・2026-09-19 に訂正が来た）。
#
#     段階は値ではなく位置なので、鍵に入れてよい
#
# 取下げは「公告に至るまでの位置」ではなく「公告のあとに起きたこと」で、
# **位置ではなく値**。段階を鍵に入れてよい理由が、取下げには当てはまらない。
# 段階は **予定／公告／結果** の3つのまま。
#
# **では取下げをどこに入れるかは、まだ決まっていない。**
# 結果の欄にも置けない（結果は「その月に開札された回」で、取下げには入札が無い。
# 落札率の分母に入れると分母が水増しになる）。
# 候補は2つあって、どちらも問題を抱えている（正本 3.5 の終了の欄が候補）。
#
# 決まるまで、**升は作らず、行も捨てず、数だけ出す**。
# 「出していない」と「起きていない」を横断ハブから見分けられるようにする。
TORISAGE = "取下げ"   # 語としては残す。**升の段階には使わない**
# **「不明」という段階は作らない**（正本 9節・2026-09-19）。
#
# 段階の欄は空にして、実物を extra に残し、data/parse-unknown.md に出す。
# 正本4節③の住所と同じ形で、「空なら『決まらなかった』と分かるだけで済む」。
#
# **kind に出さないのが肝。** 出すと横断ハブで4サイトの「不明」が1つの塊になる。
# 競売の不明は「どの段階にも入らなかった」、大型店の不明は「設置者の欄が
# 読めなかった」。意味の違うものが、束ねた数だけ独り歩きする。
#
# **不明は値ではなく徴候**（正本 3.2「食い違いは、守りではなく徴候」）。
# 増えたら段階の語彙が足りていない印。減らすのが仕事で、固定するものではない。
# kind に出すと「そういう種別がある」という顔をして固定される。
NO_STAGE = ""               # 段階が決まらなかった印。升にしない

# 升に使ってよい項目。ここに無いものでは束ねない（ガード1・2）
BUCKET_FIELDS = ("system", "pref", "city", "city_code", "kind", "stage", "ym")


def mask_count(n):
    """1〜2件はぼかす。0件と3件以上はそのまま。

    中身は common/privacy.py。**出す値は必ずあちらを通す**（正本 5節）。
    """
    return privacy.bucket_count(n)


def median_or_none(values):
    """中央値。元になる件数が3未満なら null（出さない）。"""
    vals = [v for v in values if isinstance(v, (int, float))]
    if len(vals) < MIN_FOR_MEDIAN:
        return None
    m = statistics.median(vals)
    return round(m, 3) if isinstance(m, float) else m


def to_month(value):
    """日付を月にする。2026-09-24 → 2026-09。

    週や日では束ねない（ガード2）。ここが唯一の入口なので、
    ほかの場所で日付の粒度を選べないようにしてある。
    """
    s = str(value or "")
    return s[:7] if len(s) >= 7 else ""


def stage_of(row):
    """その1件（回）が、いまどの段階か。index.json の kind に使う。"""
    status = row.get("status") or ""
    if status in SOLD:
        return KEKKA_OCHI
    if status in UNSOLD:
        return KEKKA_FUCHO
    return KOKOKU


def month_kokoku(row):
    """公告として数える月。初めて見た日（フロー）。"""
    for k in ("first_seen", "notice_date", "bid_start"):
        if row.get(k):
            return to_month(row[k])
    return ""


def month_result(row):
    """結果として数える月。開札のあった月。"""
    for k in ("open_date", "bid_end", "last_seen"):
        if row.get(k):
            return to_month(row[k])
    return ""


def events(row):
    """その回が、どの升にいくつ入るか。

    1つの回が2つ以上の升に入る。9月に公告されて10月に売れた回は、
    9月の「公告」と10月の「売却」の両方に1ずつ入る。
    どちらも「その月に起きたこと」なので、二重計上ではない。
    """
    out = []
    ym = month_kokoku(row)
    if ym:
        out.append((KOKOKU, ym))
        # **新規と再公告を両方出す。** 片方だけ出すと、親（公告）との引き算で
        # もう片方の正確な件数が出る。1件なのか2件なのかまで分かる（正本 3.2）
        out.append((KOKOKU_RE if row.get("re_notice") else KOKOKU_NEW, ym))
    status = row.get("status") or ""
    ym2 = month_result(row)
    if ym2 and status in SOLD:
        out.append((KEKKA, ym2))
        out.append((KEKKA_OCHI, ym2))
    elif ym2 and status in UNSOLD:
        out.append((KEKKA, ym2))
        out.append((KEKKA_FUCHO, ym2))
    # **取下げの升は作らない。** 置き場が正本で決まっていない（上の説明）。
    # 結果の升にも入れない（結果は「その月に開札された回」で、取下げには
    # 入札が無い。落札率の分母に入れると分母が水増しになる）。
    # 行は捨てない。undecided() が拾って data/parse-unknown.md に出る
    return out


def gone(row):
    """一覧から消えた。**取下げか繰り越しか、まだ決められない。**

    `unresolved` とも `undecided` とも違う、3つめ。

        unresolved  読めなかった。語彙の穴。**こちらが減らす**
        undecided   読めている。置き場が正本で未定。**こちらでは減らせない**
        gone        消えた。**待たないと決められない**

    **取下げと繰り越しは別物**（2026-09-19、実務からの整理）。

        取下げ    手続きが止まる。以後、同じ物件は出てこない
        繰り越し  売却できず次回へ。次の期間の公告に**同じ物件がまた出る**

    **消えた物件を全部「取下げ」と数えると、繰り越し待ちが混ざって
    取下げ率が過大になる。** 見分けるには、消えた物件が次の期間に
    再登場するかを追うしかない。だから消えた日には決められない。

    化けたあとでは気づけない。消えた行はもう一覧に残っていないので、
    照らし合わせる相手がいない（正本 4節「繋がらなかったことは残るが、
    まとまってしまったことは残らない」）。**だから母集団の保存が先。**

    こちらは `merge_snapshot()` が消えた行を捨てずに `gone_on` を付けて残し、
    `seen`（見えた日の全部）を持っている。再登場は `seen` の切れ目で分かる。
    `property_key` に開札日を入れていないので、期間をまたいでも同じ鍵になる。

    **開札日が来ているかは見ない。** 取下げのいちばん多い形は
    「公告に出たあと、開札日より前に消える」。開札日で切ると、
    その形が丸ごと見えなくなる（2026-09-19 に実際そうなっていた）。
    """
    return bool(row.get("gone_on"))


def undecided(row):
    """読めているが、**置き場が正本で決まっていない**値か。

    `unresolved()` と分ける。混ぜてはいけない。

        unresolved  読めなかった。**語彙の穴。徴候。減らすのが仕事**
        undecided   読めている。**置き場が決まっていないだけ。こちらでは減らせない**

    混ぜると、語彙の穴がいくつあるのかが読めなくなる。
    こちらが直せるのは unresolved のほうだけ。
    """
    return (row.get("status") or "") in WITHDRAWN


def unresolved(row, today=None):
    """段階が決まらなかったか。**升は作らない。記録だけ残す。**

    前は「不明」という段階を作って升に出していた。やめた（正本 9節）。

    - `kind` に出すと、横断ハブで4サイトの「不明」が1つの塊になる
    - **不明は値ではなく徴候。** 増えたら段階の語彙が足りていない印で、
      減らすのが仕事。升にすると「そういう種別がある」顔をして固定される

    `True` を返した行は `data/parse-unknown.md` に出て、人が語を足す。

    **開札の月が分かっているのに、どの結果にも入らなかった**ものを見る。
    公告だけが付いた回（まだ開札していない）は、決まらなかったのではなく
    **まだ起きていない**ので、ここには入れない。
    """
    ym2 = month_result(row)
    if not ym2:
        return False
    # **開札日がまだ来ていない回は、決まらなかったのではなく、まだ起きていない。**
    # ここを見ないと、予定が入っているだけの回が全部「読めなかった」に出て、
    # 本当に読めなかったものが埋もれる
    day = row.get("open_date") or ""
    if day and day > (today or jst_today().isoformat()):
        return False
    if gone(row):
        return False        # 消えた行は語彙の穴ではない。gone() が拾う
    status = row.get("status") or ""
    # 取下げは**読めている**（置き場が決まっていないだけ）。undecided() が拾う
    return not (status in SOLD or status in UNSOLD or status in WITHDRAWN)


def bucket_key(row, stage, ym):
    """升の鍵。市区町村より細かいものは入れない（ガード1）。

    **あとから訂正される値を鍵に入れない**（正本の但し書き）。
    落札金額・応札者数・結果・面積・用途は鍵にしない。
    訂正公告で書き換わると、同じ回が2つに増えてしまう。
    """
    # コードが行データに無ければ、都道府県と市区町村から引く。
    # ここで引いておかないと、升に「どこの」が書けない
    code = row.get("city_code") or lookup_city_code(row.get("pref"),
                                                    row.get("city"))
    return (row.get("system") or "",
            row.get("pref") or "",
            row.get("city") or "",
            code or "",
            row.get("kind") or "その他",
            stage,
            ym)


# index.json の升。正本 6節は升を **city_code × kind × period の3本**で決めると
# 書き、「1 要素 = 1 つの升」としている。物件の種別（土地・マンション・戸建て）は
# その3本のどこにも書く場所が無い（kind は `<制度>/<種別>` の2段で、
# 正本 582行の指示どおり後ろには段階を入れている）。
#
# **軸を1本落としたまま升を分けると、同じ3つ組の升がいくつも出る。**
# 読む側はどれがどれか分からず、足すこともできない。しかも種別で割ったぶん
# 1〜2件の升が増えるので、伏せ字だらけになったうえに、
# 実数で出た升との引き算で伏せた値が戻る（正本 3.2）。
#
# そこで index.json 向けには**種別を畳んで**数え直す。種別ごとの内訳は
# data/agg/monthly.json に残るので、落としているわけではない。
INDEX_FIELDS = tuple(f for f in BUCKET_FIELDS if f != "kind")


# 結果の升は、子を足すと親になる（結果 ＝ 結果-落札 ＋ 結果-不調）。
# この関係があると引き算で伏せた升が戻るので、正本 3.2 の手当てが要る。
# 公告は「公告 ＝ 公告-新規 ＋ 再公告」だが再公告の升を出していないので、
# 引き算しても何も決まらない。まとまりとして扱わない。
RESULT_FAMILY = (KEKKA, KEKKA_OCHI, KEKKA_FUCHO)

# 公告も同じ形。公告 ＝ 公告-新規 ＋ 公告-再公告。
# 前は再公告の升を出していなかったが、**出さなくても引き算はできる。**
# 公告6 − 公告-新規5 ＝ 1 で、再公告が1件だと分かってしまう。
# 升として出していないものでも、正確に1件と分かれば 3.2 が止めたかったところに届く
KOKOKU_FAMILY = (KOKOKU, KOKOKU_NEW, KOKOKU_RE)

# **どんな親子があるかだけを、ここで登録する。**
# 守らせる仕組みは common/shukei.py にある（4サイトで同じ中身にできる部分）。
# 内訳を足すときは必ずここに書く。書き忘れると tests が拾う。
FAMILIES = Families(RESULT_FAMILY, KOKOKU_FAMILY)

PARENTS = FAMILIES.parents
CHILDREN = FAMILIES.children
family_of = FAMILIES.family_of


def aggregate(rows, fields=BUCKET_FIELDS, with_raw=False):
    """行データを升ごとにまとめる。

    `fields` で升の軸を選べる。既定は BUCKET_FIELDS（種別あり）で、
    index.json 向けには INDEX_FIELDS（種別を畳む）を渡す。
    **数えるのは1か所だけ。** 2か所で別々に数えると、数が食い違う。
    """
    drop = [i for i, f in enumerate(BUCKET_FIELDS) if f not in fields]
    buckets = {}
    for row in rows:
        for stage, ym in events(row):
            if not ym:
                continue
            key = bucket_key(row, stage, ym)
            if drop:
                key = tuple(v for i, v in enumerate(key) if i not in drop)
            b = buckets.setdefault(key, {"base": [], "sale": [], "ratio": [],
                                         "n": 0})
            b["n"] += 1
            if isinstance(row.get("base_price"), (int, float)):
                b["base"].append(row["base_price"])
            if stage != KEKKA_OCHI:
                continue
            # 落札の値段と倍率は、売れた升にだけ入れる
            if isinstance(row.get("sale_price"), (int, float)):
                b["sale"].append(row["sale_price"])
            r = row.get("ratio")
            if r is None and row.get("sale_price") and row.get("base_price"):
                r = row["sale_price"] / row["base_price"]
            if isinstance(r, (int, float)):
                b["ratio"].append(r)

    # **兄弟の升が欠けていたら 0 で足す**（正本 3.2 の決まり2）。
    # 出さないと「伏せた」のか「1件も無かった」のかが見分けられない
    if "stage" in fields:
        FAMILIES.fill_siblings(
            buckets, list(fields).index("stage"),
            lambda: {"base": [], "sale": [], "ratio": [], "n": 0})

    out = []
    for key, b in sorted(buckets.items()):
        cell = dict(zip(fields, key))
        count, label = privacy.count_pair(b["n"])
        if with_raw:
            # 引き算の手当てをするのに実数が要る。**出力の前に必ず落とす**
            cell["_n"] = b["n"]
        cell.update({
            "count": count,
            "count_label": label,
            "base_median": median_or_none(b["base"]),
            "sale_median": median_or_none(b["sale"]),
            "ratio_median": median_or_none(b["ratio"]),
        })
        out.append(cell)
    return out


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


UNKNOWN_PATH = os.path.join(HERE, "data", "parse-unknown.md")


def write_unresolved(rows):
    """段階が決まらなかった行を、人が見られるところに書き出す。件数を返す。

    **升は作らない。記録だけ残す**（正本 9節・2026-09-19）。
    「不明」という段階を作ると、横断ハブで4サイトの不明が1つの塊になる。

    **不明は値ではなく徴候。** ここが増えていたら、段階の語彙が足りていない印。
    減らすのが仕事で、固定するものではない。
    """
    bad = [r for r in rows if unresolved(r)]
    body = []
    if not bad:
        body.append("無かった。")
    else:
        body += [
            "**開札日が過ぎているのに、どの結果にも入らなかった行。**",
            "升は作っていない（「不明」という段階を作らない。正本 9節）。",
            "ここが増えていたら、段階の語彙が足りていない。",
            "`aggregate.py` の SOLD / UNSOLD / WITHDRAWN に語を足すこと。",
            "**実物で見るまで足さない**（見る前に足すと、横断ハブに空の語が増える）。",
            "",
            "| 制度 | 読めなかった status | 開札の月 | 件数 |",
            "| --- | --- | --- | --- |",
        ]
        n = {}
        for r in bad:
            k = (r.get("system") or "", r.get("status") or "（空）",
                 month_result(r))
            n[k] = n.get(k, 0) + 1
        for k in sorted(n):
            body.append("| %s | `%s` | %s | %d |" % (k + (n[k],)))
        # 消えた行はここに来ない（自分の章を持つ。gone() を見ること）
    report.put_chapter(UNKNOWN_PATH, "段階が決まらなかった行", "\n".join(body))

    # **読めているが置き場が決まっていない値は、別の章にする。**
    # 語彙の穴（上）と混ぜると、穴がいくつあるのかが読めなくなる
    hold = [r for r in rows if undecided(r)]
    body2 = []
    if not hold:
        body2.append("無かった。")
    else:
        body2 += [
            "**読めている。升にしていないだけ。**",
            "正本で置き場が決まっていないので、段階にも結果にも入れていない"
            "（正本 9節・2026-09-19）。",
            "",
            "- 段階にできない — 段階は**位置**（予定／公告／結果）。"
            "取下げは「公告のあとに起きたこと」で、位置ではなく**値**",
            "- 結果にできない — 結果は「その月に開札された回」。"
            "取下げには入札が無い。落札率の分母が水増しになる",
            "",
            "**こちらでは減らせない。** 正本が置き場を決めるまで、数だけ出す。",
            "",
            "| 制度 | 値 | 開札の月 | 件数 |",
            "| --- | --- | --- | --- |",
        ]
        n = {}
        for r in hold:
            k = (r.get("system") or "", r.get("status") or "（空）",
                 month_result(r))
            n[k] = n.get(k, 0) + 1
        for k in sorted(n):
            body2.append("| %s | `%s` | %s | %d |" % (k + (n[k],)))
    report.put_chapter(UNKNOWN_PATH, "置き場が決まっていない値",
                       "\n".join(body2))

    # **消えた物件。取下げか繰り越しか、まだ決められない。**
    lost = [r for r in rows if gone(r)]
    body3 = []
    if not lost:
        body3.append("無かった。")
    else:
        body3 += [
            "一覧から消えた物件。**取下げか繰り越しか、まだ決められない。**",
            "",
            "| | |",
            "| --- | --- |",
            "| 取下げ | 手続きが止まる。以後、同じ物件は出てこない |",
            "| 繰り越し | 売却できず次回へ。次の期間の公告に**同じ物件がまた出る** |",
            "",
            "**全部を取下げと数えると、繰り越し待ちが混ざって取下げ率が過大になる。**",
            "見分けるには、次の期間に再登場するかを追うしかない。",
            "消えた日には決められない。",
            "",
            "行は捨てていない（`gone_on` を付けて残してある）。",
            "`seen`（見えた日の全部）の切れ目で再登場が分かる。",
            "",
            "| 制度 | 消えた月 | 開札の予定月 | 件数 |",
            "| --- | --- | --- | --- |",
        ]
        n = {}
        for r in lost:
            k = (r.get("system") or "", (r.get("gone_on") or "")[:7],
                 month_result(r))
            n[k] = n.get(k, 0) + 1
        for k in sorted(n):
            body3.append("| %s | %s | %s | %d |" % (k + (n[k],)))
    report.put_chapter(UNKNOWN_PATH, "消えた物件（取下げか繰り越しか未判定）",
                       "\n".join(body3))
    return len(bad), len(hold), len(lost)


def main():
    rows = load_rows()
    cells = aggregate(rows)
    # **親（合計）の升は出さない**（正本 3.2）。
    # 公告 = 公告-新規 + 公告-再公告 なので、親を並べると
    # 「公告6 − 公告-新規5 = 再公告1」と、伏せた升が引き算で戻る。
    # 読者は子を足せばよい。子は fill_siblings で全部そろえてある。
    parents = [c for c in cells if FAMILIES.is_parent(c["stage"])]
    cells = [c for c in cells if not FAMILIES.is_parent(c["stage"])]
    out = {
        "generated_at": today_str(),
        "公開しない": NOT_PUBLIC,
        "粒度": "市区町村 × 種別 × 段階 × 月。これより細かくしない",
        "段階": "予定／公告／結果 の3つ。内訳は「-」でつなぐ。"
              "公告＝その月に公告された回（新規＋再公告）、公告-新規＝初めての回、"
              "結果＝開札された回（落札率の分母）、結果-落札＝そのうち売れた回、"
              "結果-不調＝売れなかった回。混ぜない",
        "件数": "count は機械が読む（null は1か2）。count_label は人に見せる",
        "件数のぼかし": "1〜2件の升は実数を出さず \"1-2\" と書く",
        "中央値": "元になる件数が3未満のときは null",
        "出していない升": "親（合計）の段階。%s。子を足せば出る" % "／".join(FAMILIES.parents),
        "cells": cells,
    }
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("行データ %d 件 → 升 %d 個" % (len(rows), len(cells)))
    bad, hold, lost = write_unresolved(rows)
    if bad:
        # **升にはしない。** 黙ってもいない
        print("  **段階が決まらなかった行: %d 件**（data/parse-unknown.md）。"
              "升は作っていない。語彙が足りていない印" % bad)
    if hold:
        print("  置き場が決まっていない値: %d 件（data/parse-unknown.md）。"
              "読めている。正本が置き場を決めるまで升にしない" % hold)
    if lost:
        print("  **消えた物件: %d 件**（data/parse-unknown.md）。"
              "取下げか繰り越しか、再登場を待たないと決められない" % lost)
    if parents:
        # 何を落としたかは黙らない
        print("  引き算で戻るので出さなかった親の升: %d 個（%s）"
              % (len(parents), "／".join(sorted({c["stage"] for c in parents}))))


if __name__ == "__main__":
    main()
