#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""個人が特定できる組み合わせを、恒久的に固定しないための層。

正本は https://github.com/VirgoB77/ogataten-nippo/blob/main/docs/kyotsu-shiyo.md
（3.1 個人情報 / 3.2 小さい母数 / 5. privacy.py）。
直すときは、まず正本を直してから4サイトにコピーする。

**出力する値は必ずここを通す。通さない経路を作らない。**
迂回していないかは tests/test_privacy.py が公開ファイルを走査して確かめる。

考え方:

- 一次情報の側が公開していても、こちらは残る。行政の公告は数か月で消えるが、
  こちらのサイトは消えない。「消えない」ことが、そのまま責任になる
- 法人かどうかが**確かめられないときは個人として扱う**。推測で法人にしない
- 地番と氏名の**両方を落とす必要はない。片方でよい。** 両方落とすと値打ちが消える

Python 3 の標準ライブラリだけで動く。
"""

import json
import os
import re

# ---------------------------------------------------------------- 法人の見分け

# 法人格を表す語（正本 5節）。
# **★の4行を落とすと、公報と自治体の一覧表がほとんど読めない。**
# 大型店日報の実データ（設置者1,003種）で数えたところ、
# ★を入れないと275種（27%）が「個人」に化けた。入れたら22人になった。
# 公報はPDFから字を起こすので、「株式会社」より「㈱」のほうが多い。
CORP_WORDS = (
    "株式会社", "有限会社", "合同会社", "合資会社", "合名会社", "相互会社",
    "特定目的会社", "投資法人", "有限責任事業組合",
    "一般社団法人", "公益社団法人", "一般財団法人", "公益財団法人",
    "社団法人", "財団法人",
    "医療法人", "学校法人", "宗教法人", "社会福祉法人",
    "独立行政法人", "地方独立行政法人", "国立大学法人",
    "特定非営利活動法人", "NPO法人", "弁護士法人", "税理士法人",
    "生活協同組合", "農業協同組合", "漁業協同組合", "事業協同組合",
    "協同組合", "組合", "信用金庫", "信用組合",
    "公社", "公団", "事業団", "機構", "振興会", "協会", "連合会",
    "商工会", "会館", "センター", "COOP", "コープ", "生協",
    # ★丸囲み
    "㈱", "㈲", "㈳", "㈶", "㈴", "㈻", "㈷",
    # ★括弧書き（括弧は下でそろえてから見る）
    "(株)", "(有)", "(同)", "(資)", "(名)", "(福)", "(医)", "(相)",
    # ★潰れた表記。「株赤ちゃん本舗」。人名に「株」は出てこない。
    # 「有」は有田・有村など姓に出るので単独では入れない
    "株",
    # ★外国法人
    "Co.", "Ltd", "Inc", "LLC", "L.L.C", "Corp", "K.K.", "PLC",
    "S.L", "S.A", "N.V", "B.V", "GmbH", "A/S", "Pty",
    "エルエルシー", "リミテッド", "コーポレーション", "ホールディングス",
)
_CORP = re.compile("|".join(re.escape(w) for w in CORP_WORDS), re.I)

# 国と地方公共団体。法人格の語を持たないが個人ではない
# （大阪市／兵庫県／大阪市交通局／○○町教育委員会）
#
# **末尾1字で見分けてはいけない。** 「都道府県市区町村$」で当てると、
# 中村・西村・木村・川村・山田弘道 がそろって官公庁＝法人になる。
# 法人になると氏名がそのまま index.json に出て、**地番も丸められない**。
# 姉妹サイトが個人121件の地番を出した事故と、出口は同じ（正本 3.1）。
#
# 地方公共団体は名前が決まっているので、**実物の一覧と突き合わせる**。
# common/city_codes.json は総務省の全国地方公共団体コードから作ってある。
# 「山田弘道」は一覧に無いので当たらない。「大阪市」は当たる。
_GOV_ORGAN = re.compile(
    r"(教育委員会|選挙管理委員会|監査委員|人事委員会|農業委員会|"
    r"交通局|水道局|下水道局|病院局|企業局|消防局|環境局|港湾局|"
    r"議会|役所|役場|支所|出張所|公舎|公社)$")

# 国の側。こちらは語がはっきりしている
_GOV_NATION = re.compile(r"(省|庁|財務局|国税局|税務署|裁判所|検察庁|"
                         r"法務局|地方整備局|運輸局|労働局)$|^国$|^国土交通省")


def _gov_names():
    """全国の都道府県名と市区町村名。地方公共団体を名指しで見分けるために使う。"""
    names = set()
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "city_codes.json"), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return names
    for row in data.get("cities", []):
        for key in ("pref", "city"):
            v = (row.get(key) or "").strip()
            if v:
                names.add(v)
    return names


_GOV_NAMES = _gov_names()

# 括弧は半角と全角が混ざる。「(有）」という実物がある。見る前にそろえる
_BRACKETS = str.maketrans({"（": "(", "）": ")", "〔": "(", "〕": ")"})

# 名前ではない文言。「個人」に変えてはいけない。
#
# **正本5節の表に合わせる**（2026-09-19）。9節が「名前の欄の『不明』の扱いは
# 5節で決まっている」と5節を指しているのに、5節の表には `未定` しか
# 載っていなかった。**指した先に無いのは通らない**ので、正本側に
# `未詳` `不明` `なし` `無し` が足された。こちらはそのうち3語が
# 抜けていた（実際に通して確かめた: 未詳 ✗ / 不明 ✗ / 無し ✗）。
#
# 抜けていた間も、地番が出る側には倒れていない。拾えなかった語は
# 法人名でないので `個人`（町丁目まで）に落ちていた。**きつい側**。
# 直すのは、名前でないものを人として数えると個人の件数が水増しになるから。
#
# **`無し` と `無し（確認ずみ）` は別物**（NAME_COLUMN_ABSENT を見ること）。
# こちらは「名前の欄に書いてある文言」、あちらは「名前の欄が無いと確かめた」。
# 取り違えると、名前の欄がある出どころが undisclosed を名乗って地番が出る。
# だから端で留め、`無し（確認ずみ）` には当たらないようにしてある。
# `$` ではなく `\Z` を使う（`$` は末尾の改行の手前にも当たる）。
#
# **2つに割ってある。「名前ではない」は同じでも、当事者の扱いが違う。**
#
#     当事者がいない  未定・なし・該当なし … そこに相手がいない
#     読めなかった    不明・未詳・無し     … **相手はいる。こちらが読めていない**
#
# 前者は `none`（当事者を持たない制度のレコード）でよい。
# **後者を `none` にしてはいけない。** `none` は `redact_addr()` が
# 地番まで出してよい側で、「欄はあるが読めていない → individual（町丁目まで）」
# という正本 5節の決まりと逆を向く。
#
# 2026-09-19、一度これを間違えた。5節の表に語を足すとき、
# `is_boilerplate()`（名前かどうか）だけを見て、`classify_party()`
# （当事者の扱い）を見ていなかった。**不明・未詳・無しが
# individual から none に倒れていた**（ゆるい側）。
# **語を1つ足すときは、その語が通る関数を最後まで追う。**
_PLACEHOLDER_NONE = ("未定", "なし", "該当なし")
_PLACEHOLDER_UNKNOWN = ("不明", "未詳", "無し")
_PLACEHOLDER = _PLACEHOLDER_NONE + _PLACEHOLDER_UNKNOWN
# **語は `re.escape()` を通す。** 正本5節の表に括弧つきの語
# （`(未定)` のような）が足された日に、黙って別の正規表現になる
_BOILERPLATE = re.compile(r"^[(（]?未定[)）]?|^未定|営む店舗|^[―—\-－ー]+\Z|"
                          r"^[(（]?未定\d+者[)）]?\Z|"
                          + "|".join(r"^%s\Z" % re.escape(w)
                                     for w in _PLACEHOLDER))
_UNREADABLE = re.compile("|".join(r"^%s\Z" % re.escape(w)
                                  for w in _PLACEHOLDER_UNKNOWN))

# 列がずれて住所が入ったもの。丁目・番地・番・号と数字が並ぶ
_ADDRESS = re.compile(r"\d+\s*(丁目|番地|番|号)|[0-9０-９]+[-－‐]\d")

# カタカナだけ／ローマ字入り。戸籍の氏名はこの形にならない
_KATAKANA_ONLY = re.compile(r"^[ァ-ヶーｦ-ﾟ・＆&\s]+$")
# 一覧には「オークワ ほか」のように、共同の設置者を「ほか」で省く書き方がある。
# 見る前に落とす
_HOKA = re.compile(r"[\s　]*(ほか|他|外)\s*\d*\s*(名|者|社)?$")
_HAS_ROMAJI = re.compile(r"[A-Za-zＡ-Ｚａ-ｚ]")

# 個人の氏名のかわりに出す文字
PERSON = "個人"

# 件数をぼかす境目。1〜2件は実数を出さない
SMALL = 2
SMALL_LABEL = "1-2"

# 率を伏せる境目。**0件は伏せない**（下の suppress_rate を見ること）
MIN_POPULATION = 500
RATE_SMALL = 2      # 1件か2件のとき伏せる。0件は含まない


def clean_name(name):
    """名前を見る前に、括弧と空白をそろえる。"""
    s = (name or "").strip().translate(_BRACKETS)
    return re.sub(r"[\s　]+", " ", s).strip()


def drop_hoka(name):
    """末尾の「ほか」「他3名」を落とす。共同の設置者の書き方。"""
    return _HOKA.sub("", clean_name(name)).strip()


def is_boilerplate(name):
    """名前ではない文言か（未定・物品販売業を営む店舗・―）。"""
    return bool(_BOILERPLATE.search(clean_name(name)))


def is_unreadable(name):
    """名前ではないが、**当事者がいないわけでもない**文言か（不明・未詳・無し）。

    `is_boilerplate()` は「名前ではない」を見る。こちらは
    「**そこに相手がいないのか、こちらが読めていないのか**」を分ける。
    読めていないだけなら、きつい側（individual）に倒す（正本 5節）。
    """
    return bool(_UNREADABLE.search(clean_name(name)))


def looks_like_address(name):
    """列がずれて住所が入っていないか。"""
    return bool(_ADDRESS.search(clean_name(name)))


def is_truncated_corp(name, others=()):
    """途中で切れた法人名か。

    見分け方: **同じデータの中の別の名前の、先頭部分になっていたら**、
    それは切れた法人名であって人名ではない。
    「三井住友ファイナンス」は「三井住友ファイナンス＆リース株式会社」の頭。
    **人名は、ほかの名前の頭にはならない。**

    見つけても置き換えたり消したりしない。消すと「＆リース株式会社」だけが残る。
    """
    s = clean_name(name)
    if not s or len(s) < 3:
        return False
    for other in others:
        o = clean_name(other)
        if o != s and o.startswith(s):
            return True
    return False


def is_gov(name):
    """国か地方公共団体か。法人格の語を持たないが個人ではない。

    **末尾の1字では決めない。**「〜村」「〜町」「〜道」で終わる氏名は
    いくらでもある（中村・西村・山田弘道）。法人と取り違えると、
    氏名がそのまま出て、地番も丸められなくなる。迷ったら個人に倒す（正本 3.1）。
    """
    s = clean_name(name)
    if not s or looks_like_address(s):
        return False
    if _GOV_NATION.search(s):
        return True
    # 地方公共団体そのもの（大阪市・兵庫県）
    if s in _GOV_NAMES:
        return True
    # 地方公共団体＋その機関（大阪市交通局・○○町教育委員会）
    if _GOV_ORGAN.search(s):
        return any(s.startswith(n) and len(s) > len(n) for n in _GOV_NAMES)
    return False


def is_corp(name):
    """法人か。含まなければ個人として扱う。

    空や None も個人扱い。**確かめられないものを法人にしない。**
    ただし、カタカナだけ・ローマ字入り・官公庁は法人として扱う。
    戸籍の氏名はその形にならない。
    """
    s = clean_name(name)
    if not s or is_boilerplate(s) or looks_like_address(s):
        return False
    if _CORP.search(s):
        return True
    if is_gov(s):
        return True
    core = drop_hoka(s)
    if _KATAKANA_ONLY.match(core) or _HAS_ROMAJI.search(core):
        return True
    return False


# 名前の正体。party_kind と一緒に、なぜそう決めたかを返すために使う
REASON_CORP = "法人"
REASON_GOV = "官公庁"
REASON_BOILERPLATE = "名前ではない文言"
# **読めなかった。当事者がいないのとは違う**（正本 5節・2026-09-19）
REASON_UNREADABLE = "読めなかった"
REASON_ADDRESS = "住所らしい（列ずれの疑い）"
REASON_TRUNCATED = "切れた法人名"
REASON_PERSON = "個人"
REASON_EMPTY = "名前が空"


def classify_party(name, others=(), disclosed=True):
    """名前の正体を見分けて (party_kind, 理由) を返す。

    `is_corp()` が False でも、氏名とはかぎらない。
    文言・住所・切れた法人名の3つを先に見る（正本 5節）。
    """
    s = clean_name(name)
    if not s:
        return (UNDISCLOSED if not disclosed else INDIVIDUAL), REASON_EMPTY
    if is_unreadable(s):
        # **読めなかっただけ。相手はいる。**
        # `none` にすると地番まで出してよい側に倒れる（正本 5節）
        return INDIVIDUAL, REASON_UNREADABLE
    if is_boilerplate(s):
        return NONE, REASON_BOILERPLATE
    if looks_like_address(s):
        return INDIVIDUAL, REASON_ADDRESS
    if _CORP.search(s):
        return CORP, REASON_CORP
    if is_gov(s):
        return CORP, REASON_GOV
    core = drop_hoka(s)
    if _KATAKANA_ONLY.match(core) or _HAS_ROMAJI.search(core):
        return CORP, REASON_CORP
    if is_truncated_corp(s, others):
        return INDIVIDUAL, REASON_TRUNCATED
    return INDIVIDUAL, REASON_PERSON


def redact_name(name, names=()):
    """画面に出す用。法人ならそのまま。個人なら "個人" を返す。

    `names` は、そのレコードに並ぶ他の名前（任意・渡さなくてよい）。

    **`names` は戻り値を1文字も変えない。伏せ方は1ミリも変わらない。**
    変わるのは、呼ぶ側が付ける名札（開発系の `classify()`）だけ——
    つまり「この伏せ方でよかったのか」に人があとから気づけるかどうかだけ。
    伏せるか伏せないかを `names` に頼らせない。頼った瞬間、渡し忘れが穴になる。

    名前そのものが無いとき（公表されていないとき）も個人扱いになる。
    競売と公売は所有者名が公表されないので、必ずここに落ちる。

    **このサイトには本番の呼び出しが1つも無い**（2026-09-19 時点）。
    画面を作っていないため。出す値は `party_for_index()` を通している。
    正本 5節「呼んでいなくても、署名があるものは置いてそろえる」で置いてある。
    """
    name = (name or "").strip()
    return name if is_corp(name) else PERSON


def party_for_index(name):
    """index.json の `party` に入れる値。法人名だけ。個人は空文字。

    正本 6節が「個人は空文字」と決めているので、
    画面に出す `redact_name`（"個人" と書く）とは分けてある。
    """
    name = (name or "").strip()
    return name if is_corp(name) else ""


# 当事者（所有者・落札者）の種類。機械にだけ伝える印（正本 5節）
CORP = "corp"                # 法人と分かった
INDIVIDUAL = "individual"    # 個人（法人と確かめられない場合を含む）
UNDISCLOSED = "undisclosed"  # 一次情報の側が名前を載せていない
NONE = "none"                # そもそも当事者を持たない制度のレコード


# 「名前の欄が無い」と**確かめた**出どころだけが undisclosed を名乗れる
NAME_COLUMN_ABSENT = "無し（確認ずみ）"


def party_kind(name, disclosed=True):
    """当事者の出し方。上の4つのどれかを返す。

    `disclosed=False` は「**欄が無いことを確かめた**」という意味。
    確かめていないものに使ってはいけない。

        欄が無いことを確認ずみ  → undisclosed （地番まで出してよい）
        欄はあるが読めていない  → individual  （町丁目まで）
        調べていない            → individual  （町丁目まで）

    調べていない出どころは individual から始める。
    undisclosed は、調べたあとで初めて名乗れる。
    「法人か確かめられないときは個人として扱う」のと同じで、
    **わからない側はきつい側に倒す**。

    姉妹サイトで、結果表の「契約相手方」の列を読み落としたために
    名前が空になり、undisclosed に化けて、個人121件の地番が出た事故がある。
    欄はあった。読んでいなかっただけだった。
    """
    if not disclosed:
        return UNDISCLOSED
    return CORP if is_corp(name) else INDIVIDUAL


def name_absent_confirmed(name_column):
    """その出どころは「名前の欄が無い」と確かめてあるか。

    sources.json の name_column を渡す。確かめてあるときだけ True。

    **括弧と空白をそろえてから比べる**（2026-09-19）。
    ここだけ `clean_name()` を通さない生の文字列比較だったので、
    半角で `無し(確認ずみ)` と書くと黙って「未確認」に落ちた。
    倒れる向きはきつい側（町丁目まで）なので地番は漏れないが、
    **1枚読んで確かめた人の仕事が、書き方の違いで消える。**
    このファイルのほかの判定は全部 `clean_name()` を通している。
    """
    return clean_name(name_column) == clean_name(NAME_COLUMN_ABSENT)


def redact_addr(addr, kind, town=""):
    """所在地の細かさ。`kind` は party_kind() の戻り値（正本 5節）。

    **"individual" のときだけ町丁目まで丸める。**
    corp / undisclosed / none は地番まで出してよい。

    ただしこれは共通仕様の**下限**。このサイトの跡地ファイルは、
    これより厳しく「いつでも町丁目まで」にしてある（make_cross.py）。
    厳しいぶんには問題ない。

    `addr` は common/addr.py が整形したあとの文字列を渡す。
    町丁目より後ろ（数字とハイフンの並び）を落とすだけなので、
    町名の中の数字（甲子園7番町）は残る。

    `town` には normalize() が出した町丁目を渡す。**丁目を落とさないために要る**
    （下の to_town() を見ること）。
    """
    s = (addr or "").strip()
    if kind != INDIVIDUAL:
        return s
    return to_town(s, town)


def to_town(addr, town=""):
    """住所から番地を落として町丁目までにする。

    **町丁目には丁目を含める**（正本 4節「丁目は必ず含める」）。ところが
    正規化したあとの文字列では、丁目の数字も番地の数字も同じ「中津3-1-1」の
    形になっていて、**文字列だけでは見分けられない**。見分けられるのは
    元の住所に「丁目」の字があるかを見た normalize() だけ。

        中津3丁目1番1号 → 中津3-1-1   3 は丁目 → 町丁目は 中津3
        角田町3番25号   → 角田町3-25  3 は番地 → 町丁目は 角田町

    どちらも「中津3-1-1」「角田町3-25」の形なので、後ろの数字を落とすやり方だと
    前者の丁目まで一緒に落ちる。normalize() の結果が手元にあるなら、
    その `town` を渡すこと。渡せないときは、丁目も落ちる粗いほうに倒す（きつい側）。
    """
    s = (addr or "").strip()
    if not town:
        return re.sub(r"[0-9][0-9\-]*$", "", s).rstrip("-")
    # 「大阪市北区中津3-1-1」→「大阪市北区中津3」。頭の市区町村名はそのまま残す
    i = s.rfind(town)
    return s[:i + len(town)] if i >= 0 else town


def suppress_rate(count, population):
    """率を伏せるべきか。人口500人未満、または件数が1件か2件で True。

    0件は False（率も 0 を出す）。伏せるのは率×人口で件数が戻るからで、
    0件は件数そのものを 0 と出しているため戻るものが無い（正本 3.2）。

    **前は「2件以下」で書いてあったので、0件も伏せていた。**
    そうすると0件の升が率の地図で「率を出していない」灰色に落ち、
    すぐ上の「0件はいちばん薄い階級の色」と食い違う
    （街頭窃盗統計が実物で見つけ、2026-09-17 に正本が直った）。

    **人口の小ささも、0件には効かない**（2026-09-19 に直した）。
    前はここに「人口500人未満なら率そのものが跳ねる」と書いて、
    人口を先に見ていた。だから `suppress_rate(0, 400)` が True になり、
    **0件なのに率を伏せていた。**

        9件 ÷ 400人 の率に 400 を掛ければ 9件が戻る
        0件 は、何を掛けても 0

    戻る先が無いものを伏せても、守っているものは無い。
    守っていないのに、**本当に0件の升が率の地図で灰色に落ちる。**
    「0件はいちばん薄い階級の色」と食い違う。
    件数の側で一度直した不具合が、人口の小さい升だけでもう一度起きていた。

    **条件を並べるときは、どれを先に見るかも決める**（正本 3.2）。
    ここは **3段。2段ではない**（2026-09-19 に正本が足した）。

        1. 人口が0        True。**率そのものが定義できない**（0では割れない）
        2. 0件            False。率も 0 を出す
        3. 小人口・1〜2件  True

    1段目が抜けていると、2段目で0件を通したあとに **0で割る**。
    姉妹サイト（街頭窃盗統計）が実データで踏んだ。人口0の町丁目が54件あった。
    こちらは率を出していないので割り算は起きないが、
    **署名をそろえている以上、返す値もそろえる**（正本 5節）。
    """
    try:
        count = int(count)
        population = int(population)
    except (TypeError, ValueError):
        return True
    if population <= 0:
        return True                       # **いちばん先。** 0では割れない
    if count == 0:
        return False                      # 次。戻る先が無い
    return population < MIN_POPULATION or count <= RATE_SMALL


def bucket_count(n):
    """件数の表示。1〜2件は "1-2"、それ以外はそのまま。

    0件は0のまま。小さな自治体では、1件と分かるだけで個人の特定につながる。
    """
    try:
        n = int(n)
    except (TypeError, ValueError):
        return n
    if n == 0:
        return 0
    return SMALL_LABEL if n <= SMALL else n


def masked(n):
    """升の値そのもの。1件と2件は None、0件と3件以上はその数（正本 5節）。

    `bucket_count()` は**人に見せる文字列**、`masked()` は**機械が持つ値**。
    6節の `count` / `count_label` の2本立てと、そのまま対応する。
    **出力に実数を書く経路は、必ずこれを通す。**

    2026-09-17 に正本へ足された。それまで count 側を返す関数が無く、
    3つのサイトが同じ判断をそれぞれ手で書いていた。たまたま3つとも
    合っていたので誰も気づかなかった。

    **このサイトでは `count_pair()` の中から呼んでいる。**
    判断を2か所に置かないため。
    """
    try:
        n = int(n)
    except (TypeError, ValueError):
        return None
    if n == 0:
        return 0
    return None if n <= SMALL else n


# 当事者を指す列名（正本 5節）。**4サイトぶんを合わせて持つ。**
# 呼んでいない語も落とさない。落とすと地番が出る側なので、足すのはきつい側。
# 新しい列名に出会ったサイトは、**2サイト目を待たずにここへ足す**。
PARTY_WORDS = (
    "氏名", "名義", "代表者", "代表取締役", "届出者", "申請者", "設置者",
    "小売業者", "事業者", "所有者", "世帯主",
    "落札者", "落札者名", "契約相手方", "契約の相手方", "買受人", "譲受人",
)

# **語を含んでいても、名前の欄ではないものがある。**
# 「設置者対応」（設置者がどう応じたか）「設置者意見」のように、
# 語のうしろに別の意味の語が来る形。**名前は列名の末尾に来る。**
NOT_PARTY_TAILS = ("対応", "意見", "の有無", "有無", "区分", "数", "状況", "備考")


def is_party_column(label):
    """その列名は当事者（人の名前）の欄か（正本 5節）。

    語が末尾に来ているかを見る。「設置者」は当事者だが
    「設置者対応」は当事者ではない。

    **ここを落とすと、名前が空になり undisclosed に化けて地番が出る。**
    姉妹サイトで実際に起きた（結果表の「契約相手方」の列を読み落とし、
    個人121件の地番が出た）。だから語は4サイトぶんを合わせて持つ。
    """
    lab = (label or "").strip()
    if not lab:
        return False
    for w in PARTY_WORDS:
        i = lab.find(w)
        if i < 0:
            continue
        tail = lab[i + len(w):].strip("　 ：:（(")
        if not tail:
            return True
        if not tail.startswith(NOT_PARTY_TAILS):
            return True
    return False


def count_pair(n):
    """(count, count_label) の2つを返す（正本 6節）。

        実数    count   count_label
        3以上   12      "12"
        1か2    None    "1-2"
        0       0       "0"

    機械は count を見る。None なら「1か2のどれか」と読む。
    人に見せるのは count_label のほう。
    **両方いる。** count_label だけだと足し算ができず、
    count だけだと、伏せたのか本当に0なのかが見分けられない。
    """
    try:
        int(n)
    except (TypeError, ValueError):
        return None, SMALL_LABEL
    # **判断は masked() と bucket_count() の2つだけに置く。**
    # ここで書き直すと、同じ決まりが3か所になる（正本 5節）
    return masked(n), str(bucket_count(n))


# 人が住んでいるかもしれない印（正本 5節）。**4サイトぶんを合わせて持つ。**
# 当事者の語と同じで、落とす側に倒れるだけなので、語は多いほうに倒す。
# 「店舗兼住宅」のように事業用の語と混じっていても、落とすほうを採る。
# 「住宅」は地名や事業名にも出る（「○○住宅第1地区」）。それでも入れる。
_RESIDENTIAL_USE = (
    "居宅", "共同住宅", "集合住宅", "住宅", "マンション", "アパート",
    "長屋", "寄宿舎", "寮", "社宅", "戸建", "テラスハウス", "文化住宅",
    "宿舎", "住居",
)
# 住居系の用途地域はすべて名前に「住居」か「住宅」が入る
# （第一種低層住居専用地域〜準住居地域、田園住居地域）。商業・工業は住まいではない
_RESIDENTIAL_ZONING = re.compile(r"住居|住宅")
# 区分所有（マンションの一室）の気配。部屋番号は3〜4桁で出る
#   「…12番13-1406号」「（○○○○211）」
_ROOM_NO = re.compile(r"[-－‐]\s*(\d{3,4})\s*号|[（(][^）)]{0,12}?(\d{3,4})[）)]")
# **落としすぎない。「○番街区」は住居表示の街区であって部屋番号ではない。**
# ここまで落とすと土地が1件も残らなくなる
_NOT_ROOM = re.compile(r"\d+\s*番?\s*街区|\d+\s*丁目|\d+\s*番地")
# 個票の可否を決めるときに見る欄。役所によって書く場所が違うので全部見る
_USE_FIELDS = ("kind", "use", "genkyo", "現況", "building_use", "kind_raw",
               "former_use", "title", "madori", "zoning", "address")


def residential_reason(*texts):
    """人が住んでいるかもしれないか。個票にしてよければ空文字、しないなら理由。

    渡すのは「その物件が何か」を表す文字列（地目・用途地域・建物概要・所在地など）。
    **並べる順は問わない。** 呼ぶ側が欄をどう並べるかに、判定を依存させない。

        residential_reason("宅地 居宅 木造・平家建")  → "居住用途の建物"
        residential_reason("倉庫")                     → ""

    **判定に迷ったら空文字を返さない。** 個票にしない側に倒す（正本 3.1）。

    **行を消さず、落とした理由を残す。** 集計には数えるので、
    「個票にしない」という印を立てるだけにする。
    """
    text = " ".join(str(t or "") for t in texts)
    if not text.strip():
        # 何も分からない。**分からないものは個票にしない側に倒す**
        return "何を指す物件か分からない"
    for w in _RESIDENTIAL_USE:
        if w in text:
            return "居住用途の建物"
    if "間取" in text or re.search(r"\d+\s*[LDKSldks]{1,3}\b", text):
        return "間取りが書いてある"
    # 部屋番号らしき数字。ただし街区・丁目・番地は除く
    without = _NOT_ROOM.sub(" ", text)
    if _ROOM_NO.search(without):
        return "区分所有の部屋番号らしき数字がある"
    return ""


def is_lived_in(row):
    """人が住んでいる可能性があるか。**迷ったら「住んでいる」に倒す**。

    正本 3.1「人が住んでいる可能性があるものは、個票として扱わない
    （競売・公売の入札中物件、居住用途の建物、住居系用途地域）」。
    3つのうち「競売・公売の入札中物件」は、このサイトでは段（system）ごと
    個票から外してあるので、ここで見るのは残る2つ（居住用途・住居系用途地域）。

    個票とは、住所や物件が特定できる形で1件ずつ残すもの。
    集計に数えるのは構わない。恒久的に固定してはいけないのは「住所」であって
    「件数」ではない。

    **判定そのものは `residential_reason()` が持つ**（正本 5節）。
    ここは行から文字列を集めて渡すだけ。理由が要るときは
    `lived_in_reason(row)` を呼ぶ。
    """
    return bool(lived_in_reason(row))


def lived_in_reason(row):
    """`is_lived_in()` の理由。個票にしてよければ空文字。

    **落とした理由を残す**（正本 5節）。
    「なぜこの行を個票にしなかったのか」を人があとから確かめられないと、
    落としすぎているかどうかも測れない。
    """
    if _RESIDENTIAL_ZONING.search(row.get("zoning") or ""):
        return "住居系の用途地域"
    if row.get("madori"):
        return "間取りが書いてある"
    return residential_reason(*[row.get(k) for k in _USE_FIELDS])


def parent_leaks(parent_n, child_ns):
    """親の升を出すと、伏せた子の升が引き算で戻るか（正本 3.2）。

        結果 6 ／ 落札 4 ／ 不調 1-2   →   6 − 4 ＝ 2

    1件なのか2件なのかまで分かってしまい、伏せた意味が消える。

    正本 3.2 は「伏せた升がまとまりの中でちょうど1つになったら、もう1つ伏せる」
    と書くが、**その伏せ方は 6節 の書き方では表せない。** 6節 の count_label は
    `null` ＝「1か2」という意味しか持たないので、4件の升を伏せると「1-2」になり、
    伏せたのではなく**嘘をついたことになる**。

    そこで同じ 3.2 のもう一方の決まりを使う。
    「いちばん簡単なのは、**両方の粗さを出さないこと。**
      迷ったら細かいほうだけ出す。粗いほうは読者が足せばよい」

    つまり親（粗いほう）を出さない。子だけ出せば、読者は足せるし、
    伏せた子は範囲でしか分からない。落札率の分母は
    「落札 ＋ 不調」で読者が作れる。

    子が1つでも伏せてあれば親は出さない。
    子が全部伏せてあっても、親が4なら (2,2) に一意に決まるので同じこと。
    """
    if parent_n is None:
        return False                  # 親を出さないなら引き算する材料が無い
    return any(n is None or n <= SMALL for n in child_ns)


# このサイト自身が使う語。**人名ではないと分かっているものだけ**を並べる。
# 見張りは「迷ったら拾う」側なので、ここを増やすときは1語ずつ確かめること。
# 「戸建て」のような種別の語まで拾うと、見張りが毎回鳴って誰も見なくなる
OUR_WORDS = frozenset((
    # 種別（aggregate の升の kind）
    "土地", "戸建て", "マンション", "その他",
    # 段階（正本 9節。内訳は「-」でつなぐので fullmatch には掛からない）
    "予定", "公告", "結果",
    # 結果の語（正本 6節・2026-09-19。**落札／不調 の2つだけ**）。
    # 「不調」は漢字2文字で、見張りの網（2〜8文字）に素で掛かる。
    # ここに無いと、自分が書き出した語を自分の見張りが人名として拾う
    "落札", "不調",
    # 名前ではない文言。段階の語ではない（_PLACEHOLDER を見ること）
    "取下げ", "不明", "未定", "未詳",
    # 制度
    "競売", "公売", "国有財産", "公有財産",
    # 当事者の出し方（正本 5節）
    "個人",
))


def looks_like_person_name(value):
    """個人名らしき値か。公開ファイルの見張りに使う。

    法人格の語を含まないのに、日本語の名前らしい形をしているものを拾う。
    厳密ではないので、**迷ったら拾う**側に倒してある。
    """
    s = (value or "").strip()
    if not s or is_corp(s) or s == PERSON:
        return False
    # 漢字・ひらがな・カタカナだけで2〜8文字
    if not re.fullmatch(r"[一-龥ぁ-んァ-ヶー々]{2,8}", s):
        return False
    # **1文字の地名の字で外さない。** 「市区町村県府都道」を1字ずつ除くと、
    # 中村花子・西村健一・山田弘道といったありふれた氏名が、見張りの網から
    # そろって抜ける。見張りは「迷ったら拾う」側でなければ意味がない。
    # 地方公共団体かどうかは is_gov() が名指しで見分ける（末尾1字では決めない）
    if s in OUR_WORDS:
        return False
    NG = ("個人", "法人", "土地", "建物", "工場", "倉庫", "店舗", "事務所",
          "病院", "旅館", "住宅", "農地", "山林", "宅地", "雑種地",
          "落札", "入札", "公売", "競売", "滞納", "差押")
    return not any(w in s for w in NG)
