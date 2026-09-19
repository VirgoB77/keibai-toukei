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
        "**いまの既定値: %d 平米**（確認できた市町村は下の一覧の数字を使う）" % d["default_sqm"],
        "",
        "| 都道府県 | 範囲 | 広さ | 分かっていること |",
        "| --- | --- | --- | --- |",
    ]
    for a in d["areas"]:
        lines.append("| %s | %s | %d㎡ | %s |"
                     % (a["pref"], a["範囲"], a["sqm"], a["note"]))
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
    print("開発許可の規模要件を偵察レポートに足した（既定値 %d 平米）"
          % d["default_sqm"])


if __name__ == "__main__":
    main()
