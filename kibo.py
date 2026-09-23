#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""開発許可が要る土地の広さを、偵察レポートに一覧で足す。

跡地ファイルの面積の下限（`make_cross.py`）は、この数字から決める。
元になる表は common/kaihatsu_kibo.json。調べた出典もそこに書いてある。

    python3 kibo.py
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from common import report  # noqa: E402
from common.jst import today_str  # noqa: E402

DATA = os.path.join(HERE, "common", "kaihatsu_kibo.json")
REPORT = os.path.join(HERE, "data", "recon-report.md")


def main():
    with open(DATA, encoding="utf-8") as f:
        d = json.load(f)

    lines = [
        "跡地ファイルに入れる土地の下限を決めるための表。",
        "**この広さ未満の土地は、あとで開発されても開発許可の記録に残らない。**",
        "跡地として拾っても「その後どうなったか」の線が引けないので、そこで切る。",
        "",
        "根拠は都市計画法29条1項1号と同法施行令19条。原則は1,000平米だが、",
        "三大都市圏の既成市街地等では500平米。条例で300平米まで下げられる。",
        "",
        "**いま実際に効いている下限: %d 平米。**" % d["default_sqm"],
        "`common/kaihatsu_kibo.json` の `city_overrides` に載っている"
        "市町村だけ、その数字を使う（いま %d 件）。"
        % len(d.get("city_overrides") or {}),
        "",
        "**下の表は法律の整理で、そのままは効いていない。**",
        "「播磨・但馬など」のような範囲は、どの市町村コードが入るかの一覧が"
        "まだ無いので、コードから引けない。",
        "実測（2026-09-20）: 姫路市（播磨）は表では 1,000㎡ だが、"
        "実際は既定値の 500㎡ で拾っている。",
        "**推測で市町村の一覧を作らない**（正本 9節）。",
        "",
        "| 都道府県 | 範囲 | 法律上の広さ | いま効いているか | 分かっていること |",
        "| --- | --- | ---: | --- | --- |",
    ]
    kiiteinai = 0
    for a in d["areas"]:
        if a["sqm"] == d["default_sqm"]:
            kiki = "既定値と同じ"
        else:
            kiki = "**効いていない**（%d㎡ で拾っている）" % d["default_sqm"]
            kiiteinai += 1
        lines.append("| %s | %s | %d㎡ | %s | %s |"
                     % (a["pref"], a["範囲"], a["sqm"], kiki, a["note"]))
    lines.append("")
    lines.append("**表の広さと、いま効いている下限が違う範囲: %d 件。**" % kiiteinai)
    lines.append("")

    if d["city_overrides"]:
        lines.append("市町村ごとに確認できたもの:")
        lines.append("")
        for code, sqm in sorted(d["city_overrides"].items()):
            lines.append("- `%s` … %s㎡" % (code, sqm))
        lines.append("")
    else:
        lines.append("市町村ごとに数字を確かめたものは、まだ無い。")
        lines.append("")

    lines.append("## まだ確かめていないこと")
    lines.append("")
    for u in d["unconfirmed"]:
        lines.append("- %s" % u)
    lines.append("")
    lines.append("確かめたら `common/kaihatsu_kibo.json` の `city_overrides` に足す。")
    lines.append("**低いほうに合わせる。** 推測では埋めない。")
    lines.append("")

    gov = d.get("権限を持つ自治体（大阪府・2025-04-01時点）", {})
    if gov:
        lines.append("## 大阪府内で開発許可の権限を持つ自治体（2025-04-01 時点）")
        lines.append("")
        lines.append("条例を置けるのはこれらの自治体なので、引き下げを調べる先はここになる。")
        lines.append("")
        for label, names in gov.items():
            if label == "source":
                continue
            lines.append("- **%s**: %s" % (label, "・".join(names)))
        lines.append("")
        lines.append("出典: %s" % gov.get("source", ""))
        lines.append("")

    lines.append("（この章は kibo.py が %s に作り直した）" % today_str())
    lines.append("")

    # 足すのではなく差し替える。絞って動かした回に章が二重にならないように
    report.put_chapter(REPORT, "開発許可が要る土地の広さ（跡地の面積の下限）", "\n".join(lines))
    print("開発許可の規模要件を偵察レポートに足した"
          "（いま効いている下限 %d 平米 / 表とずれている範囲 %d 件）"
          % (d["default_sqm"], kiiteinai))


if __name__ == "__main__":
    main()
