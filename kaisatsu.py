#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""開札の回の集計。物件が1件も無くても出せる数字（data/agg/kaisatsu.json）。

BIT の売却スケジュールは**開札の回**の予定表で、物件も住所も当事者も
1件も含まない。だから個人情報の心配がそもそも起きない層になる。

**この数字は index.json の counts_by_city には入れられない。**
正本 6節の升は `city_code × kind × period` の3本が必須だが、開札の回は
裁判所の予定であって市区町村のものではない。神戸地方裁判所本庁の管轄だけで
市区町村は15以上あり、1市に割り当てれば嘘になり、管轄の全市に配れば
同じ1回を15回数えることになる。**推定で city_code を付けない**（正本 4節「推測で埋めない」）。
置き場所を正本に足してもらうまでは、ここ（非公開側の集計）に置く。

数え方の決まり:

- 数えるのは**回**。物件ではない。1回に何件の物件が出るかは、まだ1件も分かっていない
- 「農地専用の回」と書く。「農地の回」ではない。BITの予定表に
  「★は農地専用のスケジュールです。**ただし，それ以外のスケジュールについても
  農地が含まれる場合があります**」と書いてある
- 並べ替えない。裁判所は court_id の昇順に固定する。
  件数順に並べ替えるのは順位そのもので、正本 3.3 に触れる
- 1〜2件の升は実数を出さない（正本 3.2）。そのぶん細かい層はほとんど伏せ字になるので、
  粗い層（庁×年・府県×月・庁×全期間）も一緒に出す。どの層を使うかは出すときに選ぶ
- 状態の「空」を1つの意味として扱わない。公告日がまだ来ていない予定枠と、
  読み取れなかったものが混ざりうる。**公告日で分けて数える**

    python3 kaisatsu.py
"""

import json
import os
import statistics
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from common import privacy  # noqa: E402
from common.jst import today, today_str  # noqa: E402
from common.shukei import NOT_PUBLIC  # noqa: E402

SCHEDULE_DIR = os.path.join(HERE, "data", "schedule")
OUT = os.path.join(HERE, "data", "agg", "kaisatsu.json")

# 裁判所と都道府県。court_id の頭2桁ではなく、名前で決める（推定で付けない）
PREF = {"33111": "大阪府", "33131": "大阪府", "33141": "大阪府",
        "33311": "兵庫県", "33331": "兵庫県", "33332": "兵庫県"}

WEEK = "月火水木金土日"

# 測る区間。名前は BIT の欄の言葉にそろえる
GAPS = (("処分→公告", "disposal_date", "notice_date"),
        ("公告→入札開始", "notice_date", "bid_start"),
        ("入札期間", "bid_start", "bid_end"),
        ("入札締切→開札", "bid_end", "open_date"),
        ("公告→開札", "notice_date", "open_date"),
        ("開札→売却決定", "open_date", "decision_date"),
        ("売却決定→確定", "decision_date", "confirm_date"))


def to_date(s):
    try:
        y, m, d = (int(x) for x in (s or "").split("-"))
        return date(y, m, d)
    except (ValueError, AttributeError):
        return None


def load():
    """開札の回を全部読む。裁判所名も一緒に持つ。"""
    rows, names = [], {}
    if not os.path.isdir(SCHEDULE_DIR):
        return rows, names
    for name in sorted(os.listdir(SCHEDULE_DIR)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(SCHEDULE_DIR, name), encoding="utf-8") as f:
            d = json.load(f)
        names[d["court_id"]] = d.get("name", "").replace(
            "BIT 売却スケジュール ", "")
        rows += d.get("rows", [])
    return rows, names


def median_days(rows, a, b):
    """区間の日数の中央値。元になる回が3未満なら出さない。"""
    v = []
    for r in rows:
        x, y = to_date(r.get(a)), to_date(r.get(b))
        if x and y:
            v.append((y - x).days)
    if len(v) < 3:
        return None, len(v)
    return int(statistics.median(v)), len(v)


def reached(rows, key, today):
    """その欄の日付が、もう過ぎている回の数。

    日数の中央値は**予定表の上の間隔**であって、待った実績ではない。
    128回のうち確定日まで過ぎているのは1回しかない。
    「113日かかっている」ではなく「予定表では113日あいている」としか言えない。
    """
    n = 0
    for r in rows:
        dt = to_date(r.get(key))
        if dt and dt <= today:
            n += 1
    return n


def tally(rows, key):
    """升ごとの件数。1〜2件は伏せる（正本 3.2）。"""
    n = {}
    for r in rows:
        k = key(r)
        if k is None:
            continue
        n[k] = n.get(k, 0) + 1
    out = []
    for k in sorted(n):
        count, label = privacy.count_pair(n[k])
        out.append({"升": list(k) if isinstance(k, tuple) else k,
                    "count": count, "count_label": label})
    return out


# **このファイルの中では、粗いほうの数を伏せない。**
#
# 2026-09-17 の点検で、伏せたつもりの数が同じファイルの中で戻ることが分かった。
# **値は書かない**（正本 3.2「伏せ方を説明する文書に、実物の値を書かない」）。
# 形だけ書くと、3か所でこうなっていた。
#
#     合計.◯◯ = null  なのに、同じ数を指す別の欄が実数で出ていた（2行下）
#     合計.◯◯ = null  なのに、日数[*].◯◯.n が同じ数を出していた
#     合計.◯◯ = null  なのに、裁判所[] の内訳を足すと同じ数になった
#
# 言い換えを1つずつ塞ごうとしたが、塞ぎきれない。**このファイルは同じ回を
# 5つの粗さで数えているので、粗いほうを伏せても細かいほうを足せば戻る。**
# 庁×月を足せば庁×年になり、府県×月×農地を足せば農地専用の回になる。
# 粗さを1つに減らせば塞げるが、それはこのファイルの用途
# （どの粗さで出すかを後で選べるように並べておく）をなくすことになる。
#
# だから、中で伏せるのをやめる。**中途半端な伏せ字は「伏せてある」という
# **伏せてあると思い込ませる**（伏せた数の2行下に、同じ数が実数で書いてあった）。
# 守るのは置き場所のほう：このファイルは data/public/ に行かない。
# 伏せるのは公開するときで、1つの粗さを選んで写す、その1回だけ。
#
# **升1つ1つの 1〜2件 は、いままでどおり伏せる**（正本 3.2）。
# そちらは粗さの話ではなく升の話なので、どの粗さを選んでも効き続ける。
#
# この判断は正本に入った（2026-09-17）。3.2 の2つの節がそれ。
#
#     「粗さが混ざるファイルは、升ごとの手当てでは直らない。置き場所で分ける」
#     「中途半端に伏せるくらいなら、伏せない」
#
# 決まり1（合計の升は出さない）は升の決まりで、ファイル全体には効かない、
# というのが結論。**問いを「何を伏せるか」から「どれを公開するか」に変える。**


def build(rows, names, today):
    farm = [r for r in rows if r.get("farmland")]
    gen = [r for r in rows if not r.get("farmland")]

    # 公告日が来ているかで分ける。「状態が空」を1つの意味にしない
    published = [r for r in rows
                 if to_date(r.get("notice_date")) and
                 to_date(r["notice_date"]) <= today]
    ahead = [r for r in rows if r not in published]

    gaps = {}
    for label, a, b in GAPS:
        gaps[label] = {
            "全体": dict(zip(("中央値", "n"), median_days(rows, a, b))),
            "一般の回": dict(zip(("中央値", "n"), median_days(gen, a, b))),
            "農地専用の回": dict(zip(("中央値", "n"), median_days(farm, a, b))),
        }

    # 裁判所ごとの「予定が見えている先」。並べ替えず court_id の昇順で固定
    courts = []
    for cid in sorted(names):
        mine = [r for r in rows if r.get("court_id") == cid]
        days = sorted({r["open_date"] for r in mine if r.get("open_date")})
        last = to_date(days[-1]) if days else None
        week = {}
        for d in days:
            dt = to_date(d)
            if dt:
                w = WEEK[dt.weekday()]
                week[w] = week.get(w, 0) + 1
        # **ここも privacy.py を通す。** 前は生の件数をそのまま出していたので、
        # 1件・2件の庁がそのまま読めた（正本 3.2）
        n_all, l_all = privacy.count_pair(len(mine))
        n_farm, l_farm = privacy.count_pair(
            sum(1 for r in mine if r.get("farmland")))
        # **内訳は全部出す**（正本 3.2 決まり2）。農地専用だけ出して一般を出さないと、
        # 回 − うち農地専用 で一般が戻る。兄弟をそろえてから親を判定する
        n_gen, l_gen = privacy.count_pair(
            sum(1 for r in mine if not r.get("farmland")))
        n_day, l_day = privacy.count_pair(len(days))
        courts.append({
            "court_id": cid,
            "name": names[cid],
            "pref": PREF.get(cid, ""),
            "回": n_all, "回_label": l_all,
            "うち農地専用": n_farm, "うち農地専用_label": l_farm,
            "うち一般": n_gen, "うち一般_label": l_gen,
            "開札日": n_day, "開札日_label": l_day,
            "最後の開札日": days[-1] if days else "",
            "開札の曜日": {w: privacy.count_pair(c)[1]
                          for w, c in sorted(week.items())},
        })

    def ym(r):
        return (r.get("open_date") or "")[:7] or None

    status_cells = tally(published, lambda r: (r.get("status") or "（空）",))
    pref_month_all = tally(rows, lambda r: (PREF.get(r.get("court_id"), ""),
                                            ym(r)) if ym(r) else None)
    pref_farm = tally(
        rows, lambda r: (PREF.get(r.get("court_id"), ""), ym(r),
                         "農地専用" if r.get("farmland") else "一般")
        if ym(r) else None)

    # 粗いほうの升も、そのまま出す（上の説明を見ること）。
    # 細かいほうを足せば戻るので、伏せても伏せたことにならない
    pref_month = pref_month_all

    susumi = {
        label: reached(rows, key, today) for label, key in
        (("公告日が来た回", "notice_date"), ("入札が始まった回", "bid_start"),
         ("入札が終わった回", "bid_end"), ("開札日が過ぎた回", "open_date"),
         ("売却決定が過ぎた回", "decision_date"),
         ("確定日が過ぎた回", "confirm_date"))
    }

    doc = {
        "generated_at": today_str(),
        "公開しない": NOT_PUBLIC,
        "何これ": "開札の回の集計。物件・住所・当事者を1件も含まない",
        "数えているもの": "開札の**回**。物件の数ではない。1回に何件出るかは未取得",
        "日数について": "予定表の上の**間隔**であって、待った実績ではない。"
                        "128回のうち確定日まで過ぎているのは1回しかない。"
                        "「113日かかっている」ではなく「予定表では113日あいている」",
        "粗さについて": "**このファイルは同じ回を5つの粗さで数えている**"
                        "（裁判所／庁×月／庁×年／府県×月／府県×月×農地）。"
                        "庁×月を足せば庁×年になり、府県×月×農地を足せば"
                        "一般の回・農地専用の回になる。"
                        "**粗いほうを伏せても、細かいほうを足せば戻るので、"
                        "このファイルの中では粗いほうを伏せていない。**"
                        "中途半端に伏せると「伏せてある」と思い込ませる"
                        "（2026-09-17 まで、伏せた数の2行下に、同じ数を指す別の欄が実数で出ていた）。"
                        "守るのは置き場所のほう。出すときは1つの粗さだけを選んで "
                        "data/public/ に写し、そこで正本 3.2 を当てる",
        "升の伏せ字": "**升1つ1つの 1〜2件 は伏せてある**（count は null、"
                      "count_label は \"1-2\"）。そちらは粗さの話ではなく升の話なので、"
                      "どの粗さを選んでも効き続ける（正本 3.2）",
        "農地について": "「農地専用の回」と書く。BITの予定表に「★は農地専用の"
                        "スケジュールです。ただし，それ以外のスケジュールに"
                        "ついても農地が含まれる場合があります」とある",
        "市区町村について": "開札の回は裁判所の予定なので city_code を付けられない。"
                            "推定で付けない（正本 4節）。だから index.json の "
                            "counts_by_city には入れていない",
        "件数のぼかし": "1〜2件の升は実数を出さず count_label に \"1-2\" と書く（正本 3.2）",
        "並び": "裁判所は court_id の昇順。件数順に並べ替えない（正本 3.3）",
        "時点": today_str(),
        "合計": {
            "回": len(rows),
            "一般の回": len(gen),
            "農地専用の回": len(farm),
            "開札日の範囲": [min((r["open_date"] for r in rows), default=""),
                             max((r["open_date"] for r in rows), default="")],
            "公告まで進んだ回": len(published),
            "まだ公告前の回": len(ahead),
        },
        "どこまで進んだか": susumi,
        "状態": status_cells,
        "日数": gaps,
        "裁判所": courts,
        "庁×月": tally(rows, lambda r: (r.get("court_id"), ym(r))
                       if ym(r) else None),
        "庁×年": tally(rows, lambda r: (r.get("court_id"), (ym(r) or "")[:4])
                       if ym(r) else None),
        "府県×月": pref_month,
        "府県×月×農地": pref_farm,
    }

    return doc


def main():
    rows, names = load()
    out = build(rows, names, today())
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("開札の回 %d 件を data/agg/kaisatsu.json に置いた" % len(rows))
    print("  このファイルは公開しない。粗さが5つ混ざっている（data/public/ だけが公開用）")


if __name__ == "__main__":
    main()
