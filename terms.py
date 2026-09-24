#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""利用規約の条文を、そのまま控えに残す。

弁護士に見てもらうときに、こちらの要約ではなく**元の文そのもの**が要る。
recon.py が保存したページ（data/raw/<id>/<日付>.html）から文字だけを抜き、

    data/terms/<id>.txt      規約の全文（その日の控え）
    data/recon-report.md     の末尾に「利用規約」の章を足す

の2つを作る。新しく取りに行かない。recon.py が取ってきた分をそのまま使う。

当たり（どの条文が何に効くか）はこのファイルの NOTES に書いてある。
これは**こちらの読みであって、結論ではない**。結論は弁護士に出してもらう。
"""

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import recon  # noqa: E402
from common import report  # noqa: E402
from common import torikata  # noqa: E402  取得元の4語はここ1か所
from common.jst import today_str  # noqa: E402

RAW_DIR = os.path.join(HERE, "data", "raw")
OUT_DIR = os.path.join(HERE, "data", "terms")
REPORT = os.path.join(HERE, "data", "recon-report.md")

# 規約として控えを取るもの。kind が terms のものと、BITのご利用条件
TERMS_KINDS = ("terms",)

# どの条文が何に効くかの当たり。左が「集計（数字だけ使う）」に効くもの、
# 右が「転載（文や表をそのまま載せる）」に効くもの。
NOTES = {
    "bit-policy": {
        "集計": "「本来の趣旨以外の目的での使用」を禁じる条項。"
                "一覧に出ている数値を集めて統計にする行為が、"
                "ここに当たるかどうかが最大の論点。"
                "BITの趣旨は「買受希望者への情報提供」なので、"
                "買う人向けの相場統計は趣旨の内側だという読みもできるが、"
                "断定できない。**ここが確認事項の本体**",
        "転載": "「改ざん・無断転載」を禁じる条項。"
                "物件の個票・3点セット・一覧表をそのまま載せるのは正面からぶつかる。"
                "だから個票は出さないと決めている（DESIGN 1.3）",
        "その他": "同意ボタンを押させない規約なので、契約としての拘束力が"
                  "どこまであるかも見てもらう。"
                  "**運営は最高裁判所から委託を受けた株式会社日立社会情報サービス**で、"
                  "規約はその会社が置いたもの。相手が国ではなく私企業である点は、"
                  "拘束力の見方に効くかもしれない。"
                  "アクセスログを保守・セキュリティ・利用状況の統計分析に使うと"
                  "書いてある点も確認",
    },
    "terms-nta": {
        "集計": "公共データ利用規約（第1.0版）。CC BY 4.0 互換で、"
                "出典を書けば加工も商用利用もできる。**集計は問題にならない見込み**",
        "転載": "出典の書き方（サイト名とページURL）と、"
                "加工したときに「加工した」と別記する義務がある。"
                "国が作ったように見せてはいけない",
        "その他": "公売情報サイトが本体の規約と同じ扱いかを確かめる",
    },
    "terms-osaka-pref": {
        "集計": "数値そのものに著作権はないので集計は通る見込みだが、"
                "府の規約が独自条件を足していないかを見る",
        "転載": "複製・転用の可否と、出典表記の指定",
        "その他": "オープンデータカタログに公売情報が載っているかは別途確認",
    },
    "terms-hyogo-pref": {
        "集計": "サイト全体の著作権ページ。私的使用と引用を除いて"
                "複製・転用を認めない書き方（shutten で確認済み）。"
                "数値の集計が「引用」の枠に入るかを見てもらう",
        "転載": "無断の複製・転用は不可。表をそのまま載せない",
        "その他": "オープンデータカタログ（CC BY 4.0）側には"
                  "公売・県有地の情報が登録されていない",
    },
    "terms-osaka-city": {
        "集計": "CC BY 4.0 で出していると明記。出典を書けば集計も転載もできる",
        "転載": "第三者が権利を持つ素材が混じる場合があり、"
                "それは掲載ページに書いてあるとは限らない、と断ってある。"
                "**写真は取らないと決めているのでここは避けられる**",
        "その他": "ページごとに CC BY 4.0 の表示があるかを見る",
    },
    "terms-kobe-city": {
        "集計": "利用規約・リンク・免責のページ。独自条件の有無を見る",
        "転載": "掲載情報の著作権の扱い",
        "その他": "市有地売却と市税の公売の両方にかかる",
    },
}


def newest_raw(src_id):
    """その収集先の、いちばん新しい控えを返す。無ければ None。"""
    d = os.path.join(RAW_DIR, src_id)
    if not os.path.isdir(d):
        return None
    names = sorted(n for n in os.listdir(d)
                   if n.endswith(".html") and "--" not in n)
    return os.path.join(d, names[-1]) if names else None


def to_plain_text(path):
    """保存したHTMLから、画面に出る文字だけを取り出す。"""
    with open(path, "rb") as f:
        raw = f.read()
    text, _ = recon.to_text(raw, "")
    s = recon.Scanner()
    try:
        s.feed(text)
    except Exception:
        return ""
    body = "".join(s.text)
    body = re.sub(r"[ \t　]+", " ", body)
    body = re.sub(r"\n\s*\n\s*\n+", "\n\n", body)
    lines = [ln.strip() for ln in body.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def main():
    with open(os.path.join(HERE, "sources.json"), encoding="utf-8") as f:
        sources = json.load(f)["sources"]

    targets = [s for s in sources if s.get("kind") in TERMS_KINDS]
    os.makedirs(OUT_DIR, exist_ok=True)

    lines = [
        "弁護士に見てもらうための材料。こちらの要約ではなく、元の文そのものを置いてある。",
        "取ってきた日の控えなので、あとで文面が変わっても、そのとき何が書いてあったかが残る。",
        "全文は `data/terms/<id>.txt` にも同じものがある。",
        "",
        "**下の「当たり」はこちらの読みであって、結論ではない。**",
        "どの条文が「数字だけ使うこと（集計）」に効き、どの条文が"
        "「そのまま載せること（転載）」に効くか、の見当をつけたもの。",
        "",
    ]

    done = 0
    for src in targets:
        path = newest_raw(src["id"])
        note = NOTES.get(src["id"], {})
        lines.append("## %s" % src["name"])
        lines.append("")
        lines.append("- id: `%s`" % src["id"])
        lines.append("- URL: %s" % (src.get("url") or "（未確認）"))
        lines.append("- 取得元の欄: **%s**（%s）"
                     % (torikata.go(src) or "（書いていない）",
                        torikata.riyuu(src) or "理由が書いていない"))
        止める = torikata.naze_toranai(src)
        if 止める:
            lines.append("- **まだ取っていない（%s）**" % 止める)
            lines.append("")
            continue
        if note:
            lines.append("- **集計に効きそうな条文**: %s" % note.get("集計", "—"))
            lines.append("- **転載に効きそうな条文**: %s" % note.get("転載", "—"))
            if note.get("その他"):
                lines.append("- あわせて見てもらう点: %s" % note["その他"])
        if not path:
            lines.append("- **控えがまだ無い**（recon.py を1回動かすと取れる）")
            lines.append("")
            continue

        body = to_plain_text(path)
        with open(os.path.join(OUT_DIR, "%s.txt" % src["id"]), "w",
                  encoding="utf-8") as f:
            f.write("出典: %s\n取得日: %s\n\n%s\n"
                    % (src.get("url"), os.path.basename(path)[:10], body))
        lines.append("- 控え: `data/terms/%s.txt`（%s 取得・%d 文字）"
                     % (src["id"], os.path.basename(path)[:10], len(body)))
        lines.append("")
        lines.append("<details><summary>ここから規約の全文</summary>")
        lines.append("")
        lines.append("```")
        lines.append(body)
        lines.append("```")
        lines.append("")
        lines.append("</details>")
        lines.append("")
        done += 1

    lines.append("## まだ確かめていない規約")
    lines.append("")
    lines.append("- 財務省・近畿財務局（国有財産）。政府標準利用規約系の見込みだが未確認")
    lines.append("- 堺市（市有地売却）")
    lines.append("")
    lines.append("（この章は terms.py が %s に作り直した）" % today_str())
    lines.append("")

    # 足すのではなく差し替える。絞って動かした回に章が二重にならないように
    report.put_chapter(REPORT, "利用規約（全文の控え）", "\n".join(lines))
    print("規約の控え %d 本を data/terms/ に置き、偵察レポートに章を足した" % done)


if __name__ == "__main__":
    main()
