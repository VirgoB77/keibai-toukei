#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""どこまで見たか（data/agg/shuroku.json）。

升は**見たところにしか出ない**。だから「升が無い」を「0件」と読んでよいかは、
升のほうを見ても分からない。ここで決まる。

正本 3.2「伏せた升と、本当に0件の升は、見た目で分ける」を地図で守るには、
状態が3つでは足りず4つ要る。

    ① 見た。0件だった              → いちばん薄い階級
    ② 見た。1〜2件だった            → 別の見た目＋凡例「1〜2件」
    ③ 見ていないが、別の出どころで0と分かる → いちばん薄い階級**でよい**
    ④ 見ていない                   → 斜線・未収録。階級の色を塗らない

**③ が要る。** 堺支部・岸和田支部の物件一覧は読んでいないが、
売却スケジュールに閲覧可能・入札期間中の回が1つも無いので0件と言える。
物件一覧は「入札中・閲覧中の物件」しか出さないので、回が無ければ空になる。

**0 にも出典が要る**（正本 3.5）。0 は記録が無いので付ける先が無い、と見えるが、
そうではない。**0 を証明した別の記録**が source_url と fetched_on を持っている。
ここではそれを写す。

見た単位は**裁判所**であって市区町村ではない。管轄は sources.json に
自由文で書いてあり（「南河内」「泉州」「播磨一帯」）、市区町村コードに
落ちていない。落とすには裁判所の管轄区域を写す作業が要るが、
それは推測で埋めてはいけない（正本 4節）。**だから自由文のまま持つ。**
直し方を間違えても元に戻せる（正本 9節）。

    python3 shuroku.py
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from common.jst import today_str  # noqa: E402
from common.shukei import NOT_PUBLIC  # noqa: E402

SCHEDULE_DIR = os.path.join(HERE, "data", "schedule")
ROWS_DIR = os.path.join(HERE, "data", "rows", "keibai")
OUT = os.path.join(HERE, "data", "agg", "shuroku.json")

LIVE = ("閲覧可能", "入札期間中")


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def kankatsu(sources, court_id):
    """管轄の書き方。**一次情報の書き方のまま写す。**"""
    for src in sources:
        if src.get("court_id") == court_id and src.get("kind") == "bit-schedule":
            note = src.get("note") or ""
            i = note.find("管轄")
            if i >= 0:
                return note[i:].split("。")[0]
    return ""


def build(sources):
    out = []
    for src in sources:
        if src.get("kind") != "bit-schedule":
            continue
        name = src["name"].replace("BIT 売却スケジュール ", "")
        if not src.get("court_id"):
            # **番号が無いものを黙って落とさない。**
            # 豊岡支部は BIT の裁判所一覧に載っておらず、番号が引けない。
            # 落とすと、収録範囲そのものに穴が開く。
            # 「見ていない」として出し、理由を一次情報の言い方のまま写す
            out.append({"見た単位": "裁判所", "id": "", "name": name,
                        "管轄": kankatsu(sources, src.get("court_id")),
                        "状態": "見ていない",
                        "なぜ": (src.get("note") or "").split("。")[0]})
            continue
        cid = src["court_id"]
        rows = read_json(os.path.join(ROWS_DIR, "%s.json" % cid))
        sch = read_json(os.path.join(SCHEDULE_DIR, "%s.json" % cid))
        item = {"見た単位": "裁判所", "id": cid, "name": name,
                "管轄": kankatsu(sources, cid)}

        if rows and rows.get("rows"):
            one = rows["rows"][0]
            item.update({
                "状態": "見た",
                "物件": len(rows["rows"]),
                "source_url": one.get("source_url") or "",
                "fetched_on": one.get("last_seen") or one.get("first_seen") or "",
            })
        elif sch and sch.get("rows"):
            live = [r for r in sch["rows"] if (r.get("status") or "") in LIVE]
            one = sch["rows"][0]
            if live:
                item.update({
                    "状態": "見ていない",
                    "なぜ": "閲覧可能・入札期間中の回が %d ある。"
                            "一覧を読むまで何件あるか分からない" % len(live),
                })
            else:
                # **0 を証明したのは、物件一覧ではなく売却スケジュール。**
                # その記録の出典をそのまま写す（正本 3.5）
                item.update({
                    "状態": "見ていないが0と言える",
                    "物件": 0,
                    "0の根拠": "売却スケジュールに閲覧可能・入札期間中の回が"
                                "1つも無い。物件一覧は入札中・閲覧中の物件しか"
                                "出さないので、回が無ければ空になる",
                    "source_url": one.get("source_url") or "",
                    "fetched_on": one.get("fetched_on") or "",
                })
        else:
            item.update({"状態": "見ていない", "なぜ": "予定表も読めていない"})
        out.append(item)
    return sorted(out, key=lambda x: (x["id"] == "", x["id"]))


def main():
    sources = read_json(os.path.join(HERE, "sources.json"))["sources"]
    ranges = build(sources)
    doc = {
        "generated_at": today_str(),
        "公開しない": NOT_PUBLIC,
        "何これ": "どこまで見たか。升は見たところにしか出ないので、"
                  "「升が無い」を「0件」と読んでよいかはここで決まる",
        "見た単位": "裁判所。市区町村ではない",
        "状態は4つ": "見た／見た（0件）／見ていないが別の出どころで0と言える／見ていない",
        "0の出典": "0 を証明した別の記録の source_url と fetched_on を写す（正本 3.5）",
        "範囲": ranges,
        "割り当て": [],
        "割り当てが空な理由":
            "収録範囲（裁判所）を市区町村に割り当てられていない。"
            "管轄が sources.json に自由文で書いてあり、「南河内」「泉州」"
            "「播磨一帯」は市区町村コードに落ちない。落とすには裁判所の"
            "管轄区域を写す作業が要るが、推測で埋めてはいけない（正本 4節）。"
            "**割り当てられないものは、割り当てない。**"
            "地図は割り当ての無いところを「この範囲は◯◯裁判所の管轄だが、"
            "市区町村までは割り切れない」とそのまま出す。嘘の精度を作らない",
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write("\n")
    n = {}
    for r in ranges:
        n[r["状態"]] = n.get(r["状態"], 0) + 1
    print("収録範囲 %d 単位を data/agg/shuroku.json に置いた（%s）"
          % (len(ranges), " / ".join("%s %d" % kv for kv in sorted(n.items()))))


if __name__ == "__main__":
    main()
