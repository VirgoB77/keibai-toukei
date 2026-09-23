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
    （`unsold` という欄は無い。**不調は升の段階として出す**
     → `競売/不調`。取消は回の語なので升にしない）

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
#   公告-初出 … そのうち、**こちらが初めて見た**回だけ。
#              「初めて公告された」ではない。こちらが見る前は知らない
#   結果      … その月に開札された回の数（落札＋不調）。落札率の分母
#   落札      … そのうち売れた回。落札率の分子
#   不調      … そのうち売れなかった回
#
# **結果と落札を分けるのが大事。** 「売れた件数」をレコード数で数えると、
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
# その中の内訳は「-」でつなぐ（公告-初出、公告-再出）。
#
# **結果の語は 落札／不調 の2つだけ**（正本 6節・2026-09-19）。
# 「売却」「不売」「売却済み」とは書かない。法令に近く、いちばん多く
# 使われていた語に4サイトでそろえた。
#
#     種別には段階も結果も入る
#     段階なら 競売/公告、結果なら **競売/落札・競売/不調**
#     **段階と結果を1つの升に混ぜない**
#     種別の中をさらに分けるときは - でつなぐ（競売/公告-初出）
#
# 前は `結果-落札` と書いていた。**これが「混ぜた」形。**
# 段階（結果）と結果（落札）が1つの升に入っていた。
# いまは 結果 が親、落札／不調 が子。子は親の接頭辞を持たない。
# **「新規」と名乗っていた。名乗れない語だった**（2026-09-19 に訂正）。
#
#     新規 / 再公告   **事実の主張**。こちらが見る前の回があると外れる
#     初出 / 再出     **観測の記述**。外れようがない
#
# こちらは 2026-09-17 から一覧を重ねている。7月に公告されて9月に再公告された
# 物件も、こちらには「初めて見た回」として届く。それを「新規」と呼ぶと、
# **持っていない知識を名乗る**ことになる。
#
# **主語を「こちら」にすると、外れなくなる。**
# だから数字の隣に「いつから見ているか」を必ず出す（index.json の observed）。
# それが無いと「初出」が読めない。
KOKOKU, KOKOKU_NEW = "公告", "公告-初出"
KOKOKU_RE = "公告-再出"     # こちらが前にも見ている回。初出と足すと公告になる
KEKKA = "結果"              # その月に開札された回（落札＋不調）。**親。出さない**
OCHI = "落札"               # そのうち売れた回
FUCHO = "不調"              # そのうち売れなかった回
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

# 升の軸を人が読む語にする。**粒度の文はここから組み立てる。**
# 手で書いた文だと、軸を足した日に文だけ古いまま残る。
# 実測（2026-09-20）: 軸は7本あるのに、粒度の文は
# 「市区町村 × 種別 × 段階 × 月」と4本しか名乗っていなかった。
# 都道府県は実データで3種（兵庫県66行・大阪府40行・空1行）ある。
BUCKET_NAME = {"system": "制度", "pref": "都道府県", "city": "市区町村",
               "city_code": "市区町村コード", "kind": "種別",
               "stage": "段階", "ym": "月"}


def ryudo(fields=BUCKET_FIELDS):
    """升の粒度を1行にする。**軸を足したら文も動く。**"""
    # 市区町村コードは市区町村と1対1なので、人に読ませる文では畳む
    見せる = [f for f in fields if f != "city_code"]
    return "×".join(BUCKET_NAME[f] for f in 見せる) + "。これより細かくしない"


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
        return OCHI
    if status in UNSOLD:
        return FUCHO
    return KOKOKU


def month_kokoku(row):
    """公告として数える月。**こちらが初めて見た日**（フロー）。

    **「その月に公告された」ではない。** 相手が公告した日は
    こちらの初見より前にありうる。実測（2026-09-20）: 106行のうち
    **4行**は閲覧開始日（view_start）が 2026-07／08 なのに、
    こちらの初見が 2026-09 なので 2026-09 の升に入っている。
    主語を「こちら」にすれば外れない（DESIGN「名乗れる語だけで数える」）。

    `view_start` をここに足さないこと。足すと、その日より前に
    公告されていたものを「その月に公告された」と名乗ることになる。
    """
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
    9月の「公告」と10月の「落札」の両方に1ずつ入る。
    どちらも「その月に起きたこと」なので、二重計上ではない。
    """
    out = []
    ym = month_kokoku(row)
    if ym:
        out.append((KOKOKU, ym))
        # **初出と再出を両方出す。** 片方だけ出すと、親（公告）との引き算で
        # もう片方の正確な件数が出る。1件なのか2件なのかまで分かる（正本 3.2）
        out.append((KOKOKU_RE if row.get("saishutsu") else KOKOKU_NEW, ym))
    status = row.get("status") or ""
    ym2 = month_result(row)
    if ym2 and status in SOLD:
        out.append((KEKKA, ym2))
        out.append((OCHI, ym2))
    elif ym2 and status in UNSOLD:
        out.append((KEKKA, ym2))
        out.append((FUCHO, ym2))
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
    if status in SOLD or status in UNSOLD or status in WITHDRAWN:
        return False
    # **語が書いてあるなら、読めている**（正本 6節・2026-09-19）。
    # 「取消」のように、読めたが置き場の無い語がここに来る。
    # 欄が空なら、そもそも結果を読んでいない。`unobserved()` が拾う
    if status:
        return True
    # 欄が空で、結果のページを取りに行っている制度なら、
    # 読んだのに結果が無かったということ。これも語彙の穴
    return row.get("system") in KEKKA_YOMERU


def unobserved(row, today=None):
    """決めるのに要るページを、**まだ取りに行っていない**。

    `unresolved`（読めなかった）は**試したという主張**になる。
    試していないものを、そう名乗らない（正本 6節・2026-09-19）。

        unresolved  取りに行って、読んだが語が分からなかった → 語彙を足す
        unobserved  決めるのに要るページを取りに行っていない → 出どころを足す

    **減らす手が違うので、同じ箱に入れない。**

    実測（2026-09-19）。競売の結果は1枚も取りに行っていないので、
    開札日が過ぎた行はここへ来る。

        2026-09-19    0 件（開札日が全部先）
        2026-10-03   37 件
        2026-12-25  105 件（106行のうち）

    **語が書いてあるなら、ここには来ない。**「取消」のように読めたが
    置き場の無い語は `unresolved` のほう（読めている。語彙の穴）。
    ここに来るのは**欄が空のまま開札日が過ぎた**行だけ。

    **一覧では見ている行だけを数える。** 一覧そのものを見ていない行は
    ここに入れない（それは出どころの表の話）。この行たちは公告の升に
    入っているので、**分母には入る**。
    """
    ym2 = month_result(row)
    if not ym2:
        return False
    # 開札日がまだ来ていない回は、取りに行っていないのではなく**まだ起きていない**
    day = row.get("open_date") or ""
    if day and day > (today or jst_today().isoformat()):
        return False
    if gone(row):
        return False
    status = row.get("status") or ""
    if status in SOLD or status in UNSOLD or status in WITHDRAWN:
        return False
    # **語が書いてあるなら、読めている。** 置き場が無いだけなので語彙の穴。
    # ここに来るのは**欄が空のまま開札日が過ぎた**行だけ
    if status:
        return False
    return row.get("system") not in KEKKA_YOMERU


# ---------------------------------------------------------------- 数が合うこと
# **足したときに数が合うこと**（正本 3.2・2026-09-19）。
#
#     升の合計 ＋ not_counted の3つ ＝ 見た行の数
#     合わなければ、黙って落としている
#
# **この形のままでは、このサイトでは閉じない。** 実データで確かめた（106行）。
# 1つの行が2つ以上の升に入るため（9月に公告されて10月に売れた回は、
# 9月の公告と10月の落札の両方に1ずつ入る）。さらに、取下げになった行は
# **公告の升にも入ったまま**でなければならない。公告から外すと母集団が痩せ、
# 取下げ率の分母が消える（正本 3.5「母集団の保存が先」）。
#
#     実測 2026-09-19   公告-初出 106 ＋ not_counted 1 ＝ 107 ≠ 106
#
# 取下げの1行が、公告-初出にも not_counted.undecided にも入っている。
# **どちらも正しい。** 9月に公告されたのは事実で、取下げで消えたのも事実。
#
# そこでこちらは、正本の1つの等式を**2つに分けて**確かめる。
# 食い違いとして正本に報告ずみ（docs/seihon-toiawase.md #11）。
#
#   ① 行方の保存（在庫）… 1行は必ず1つの行方に入る。足すと見た行の数
#   ② 内訳の保存（流量）… 子の升を足すと親の升になる（公告・結果）
#
# ①が「黙って落としていないか」、②が「登録表が正しいか」を見る。

# 行方。**上から当たった1つで決まる。順番に意味がある。**
#
#   落札・不調  結果が出た。**いちばん強い**（開札まで行った）
#   取下げ      手続きが止まった（index.json の not_counted.undecided）
#   消えた      一覧から消えた。取下げか繰り越しか未確定（同 gone）
#   見に行っていない  決めるのに要るページを、まだ取りに行っていない（同 unobserved）
#   読めない    取りに行って、読んだが語が分からなかった（同 unresolved）
#   待ち        まだ開札を迎えていない。**落ちているのではない**
#
# **「見に行っていない」を「読めない」より先に見る**（正本 6節・2026-09-19）。
# 2つは排他だが（下の KEKKA_YOMERU で分かれる）、**どちらを先に見るかを書く**。
# 先に来るのは原因が外にあるほう。語をいくつ足しても減らないのはこちら。
#
# **「待ち」は正本の3つに無い、4つめ。** 実データでは106行のうち105行が
# ここに入る。これを数えないと①が閉じない。index.json には出していない
# （欄の名前は正本6節が決める。勝手に足さない。正本 11節）。
YUKUE = ("落札", "不調", "取下げ", "消えた", "見に行っていない", "読めない", "待ち")

# index.json の not_counted の欄に対応する行方（正本 6節で名前が決まった4つ）
YUKUE_KEY = {"取下げ": "undecided", "消えた": "gone",
             "見に行っていない": "unobserved", "読めない": "unresolved"}

# **結果のページを取りに行って、読めている制度。**
#
# ここに無い制度は、開札日が過ぎても「読めなかった」ではなく
# **「見に行っていない」**（正本 6節・2026-09-19）。
#
#     unresolved  取りに行って、読んだが語が分からなかった → こちらが語彙を足す
#     unobserved  決めるのに要るページを、まだ取りに行っていない → こちらが出どころを足す
#
# **減らす手が違うので、同じ箱に入れない。**
# 語をいくつ足しても `unobserved` は1件も減らない。
#
# いまは空。競売の結果は `bit-result` が画面遷移 POST で URL を持たず
# `enabled: false`、読み取りも無い（`parse.INBOX_READABLE`）。
# **読み取りを書いた日に、ここへ足す。**
# 忘れると `unobserved` のまま止まるので、検査で留めてある。
KEKKA_YOMERU = ()


def yukue(row, today=None):
    """その行が、いまどこにいるか。**1行は必ず1つだけ。**

    `YUKUE` の順に見て、最初に当たったもので決まる。
    足すと必ず見た行の数になる（そうでなければ黙って落としている）。
    """
    status = row.get("status") or ""
    if status in SOLD:
        return OCHI
    if status in UNSOLD:
        return FUCHO
    if undecided(row):
        return "取下げ"
    if gone(row):
        return "消えた"
    # **「見に行っていない」を先に見る。** 原因が外にあるほうが先
    if unobserved(row, today):
        return "見に行っていない"
    if unresolved(row, today):
        return "読めない"
    return "待ち"


def yukue_conflicts(row, today=None):
    """**合図どうしが食い違っている行。**

    前はここで「`gone_on` が立っている」を無条件に合図に数えていた。
    **それは食い違いではない。** `parse.merge_snapshot()` は、その日の一覧に
    出てこなかった行すべてに `gone_on` を付ける。売れた物件も不売の物件も、
    開札が済めば一覧から落ちる。**普通の一生**が毎回「重なり」として鳴り、
    結果が溜まるほど鳴り続ける（正本 9節「誤報を出す見張りは、そのうち
    誰も見なくなる」）。2026-09-19 に指摘されて直した。

    `status` は1つの文字列なので、落札と不調、結果と取下げは同時に立たない。
    **本当に食い違うのは1つだけ。**

        開札日より前に一覧から消えたのに、結果が出ている

    消えたあとに結果が出ることはない。どちらかの読みが間違っている。
    """
    status = row.get("status") or ""
    gone_on = row.get("gone_on") or ""
    day = row.get("open_date") or ""
    if not (gone_on and day and gone_on < day):
        return []
    if status in SOLD or status in UNSOLD:
        return ["開札日(%s)より前に消えた(%s)のに、結果が出ている(%s)"
                % (day, gone_on, status)]
    return []


def cell_axes(cell):
    """升の鍵のうち、段階以外の軸。**升ごとに数えるために要る。**"""
    return tuple(cell.get(f) for f in BUCKET_FIELDS
                 if f != "stage" and f in cell)


def kazu_ga_au(rows, cells=None, today=None, cell_rows=None):
    """**足したときに数が合うか。** 合わない中身を返す。

    `cells` を渡すと②（内訳の保存）も見る。渡さなければ①だけ。
    戻すのは辞書。`食い違い` が空なら合っている。

    **最初の1件で止まらない**（正本 9節）。全部見てから返す。

    ## 2026-09-19 に、どちらも鳴らない形だったのを直した

    ①は `行方の合計 != 見た行の数` を見ていた。**これは恒真。**
    `yukue()` は必ず6つのどれかを返し、行ごとに1つ足すので、合計は
    いつでも行の数に等しい。看板に「黙って落としていないか」と書いて、
    **1つも確かめていなかった。**

    本当に黙って落ちるのは「**行方は付くのに升が1つもできない行**」。
    日付の列を読み落とすと `events()` が空を返し、升にも `not_counted` にも
    出ないまま消える。いまはそれを見る。

    ②は段階ごとの合計を**全体で1本**に畳んでいた。`events()` は1行から
    親と子をちょうど1つずつ出すので、全体で足すと **親 ＝ 子の合計** が
    恒等的に成り立つ。市や月のどこで食い違っても、別の升の逆向きの
    食い違いと打ち消しあう。**升ごとに見る。**

    ## ③ 行と升を突き合わせる（2026-09-19 に足した）

    ①②だけでは、**升のまとまりが丸ごと消えても鳴らない。**
    ①は行から `events()` を計算し直すだけで、**書き出した升に実際に
    入ったか**を見ていない。②は「在る升」の親子しか見ないので、
    ある市の升が親も子も一緒に消えると、そのまとまりが現れないだけで
    何も言わない。

    実測（2026-09-19）: 1つの市の升を落としても `食い違い: []` のまま通り、
    `counts_by_city` が 92 → 90 に減って、**その市が丸ごと公開データから
    消えたまま出た**。テスト428本も全部通った。

    だから **子の升の実数の合計** と **行から数えた子の出来事** を比べる。

    ## 母集団は `cell_rows` で渡す

    `make_index` は個票に出した行を升から外す（`counted`）。
    升を作った母集団と、行方を数える母集団が違う。
    **同じ `rows` で比べると、個票が1件出た瞬間に誤報で止まる**
    （正本 9節「誤報を出す見張りは、そのうち誰も見なくなる」）。
    `cell_rows` を渡さなければ `rows` と同じ。
    """
    # **行方の語は全部並べる。0でも出す**（正本 6節・2026-09-19）。
    # 起きなかった語が欄ごと消えると、「0件だった」と
    # 「そもそも数えていない」が見分けられない。**欠けているキーは0ではない。**
    yuk = {y: 0 for y in YUKUE}
    no_cell, kasanari = [], []
    for r in rows:
        y = yukue(r, today)
        yuk[y] = yuk.get(y, 0) + 1
        # **升にも not_counted にも出ない行**。これが「黙って落ちる」の実体。
        # 2つある。
        #   ① 升が1つもできない          日付の列を読み落とした
        #   ② 落札と名乗るのに落札の升が無い  結果の月だけ読めていない
        # ②は①より見つけにくい。公告の升には入るので、行が消えた顔をしない
        if y not in YUKUE_KEY:
            stages = {st for st, _ym in events(r)}
            if not stages:
                no_cell.append((y, "升が1つもできない"))
            elif y in (OCHI, FUCHO) and y not in stages:
                no_cell.append((y, "%s と読めているのに %s の升が無い"
                                   % (y, y)))
        kasanari += yukue_conflicts(r, today)

    bad = []
    why = {}
    for y, w in no_cell:
        why[w] = why.get(w, 0) + 1
    for w in sorted(why):
        bad.append("%s行が %d 件ある。日付の列が読めていない見込み"
                   % (w + "（行方あり）の", why[w]))
    for c in kasanari:
        bad.append("合図が食い違う行: " + c)

    uchiwake = []
    if cells is not None:
        # **升ごとに数える。** 全体で1本に畳むと、逆向きの食い違いが
        # 打ち消しあって鳴らない
        per = {}
        欠け = 0
        for c in cells:
            n = c.get("_n")
            if n is None:
                # **1つでも欠けたら止める**（2026-09-19）。
                # 前は「全部無い」ときしか鳴らなかったので、
                # 一部の升だけ `_n` が欠けると②が**その升だけ黙って飛ばし**、
                # 親だけ残った升では「子が欠けている」と**ありもしない
                # 食い違い**を報せた。`with_raw=True` は全升に無条件で
                # 付けるので、一部だけ欠けるのは渡し方が間違っている
                欠け += 1
                continue
            per.setdefault(cell_axes(c), {})[c["stage"]] = n
        if cells and 欠け:
            raise ValueError(
                "升 %d 個のうち %d 個に実数(_n)が無い。内訳の保存を見られない。"
                "aggregate(..., with_raw=True) で作った升を、"
                "実数を落とす前に渡すこと" % (len(cells), 欠け))
        for axes in sorted(per, key=lambda a: tuple(str(v) for v in a)):
            for d in FAMILIES.check_sums(per[axes]):
                d = dict(d, 升=axes)
                uchiwake.append(d)
                # **どの升かを書く。** 書かないと、同じ1行が升の数だけ
                # 並ぶ（実測で66行、`sort -u` すると1行）。
                # 数だけ並べても、どこを見ればよいか分からない
                どこ = "／".join(str(v) for v in axes if v)
                if d["親の数"] is None:
                    bad.append("%s の親の升が無いのに子がある（%s）。"
                               "親を落とす前の升を渡すこと" % (d["親"], どこ))
                elif d["欠けている子"]:
                    bad.append("%s の子が欠けている（%s）: %s"
                               % (d["親"], どこ, "・".join(d["欠けている子"])))
                else:
                    bad.append("%s の升 %d と、子の合計 %d が合わない（%s）"
                               % (d["親"], d["親の数"], d["子の合計"], どこ))

        # **升に出る段階は、全部まとまりに登録されていること**（2026-09-19）。
        #
        # 子が親の接頭辞を持たなくなったので、`undeclared()` は
        # **「-」を含む名前しか拾えない。** 接頭辞を持たない段階を
        # `events()` に足して登録を忘れると、どの見張りにも掛からずに
        # `counts_by_city` に出る（取下げを結果に足す、がまさにこの形）。
        # ②は登録されたまとまりしか見ず、③も登録された語しか数えない。
        知らない = sorted({c["stage"] for c in cells
                        if c["stage"] not in FAMILIES.parents
                        and c["stage"] not in FAMILIES.children})
        if 知らない:
            bad.append("まとまりに登録されていない段階が升に出ている: %s。"
                       "`FAMILIES` に足すこと（足さないと引き算の手当てが"
                       "掛からない）" % "・".join(知らない))

        # ③ **行と升を突き合わせる。** 升のまとまりが丸ごと消えるのは
        # ①②のどちらにも掛からない
        母 = rows if cell_rows is None else cell_rows
        for 役, 語 in (("子", FAMILIES.children), ("親", FAMILIES.parents)):
            升 = sum(n for d in per.values()
                     for st, n in d.items() if st in 語)
            行 = sum(1 for r in 母 for st, ym in events(r)
                     if ym and st in 語)
            if 升 != 行:
                bad.append("%sの升の実数合計 %d と、行から数えた%sの出来事 %d が"
                           "合わない。升がまとまりごと落ちている見込み"
                           % (役, 升, 役, 行))
    return {
        "見た行": len(rows),
        "行方": yuk,
        "升にならない行": len(no_cell),
        "食い違う合図": len(kasanari),
        "内訳": uchiwake,
        "食い違い": bad,
    }


def yukue_gyou(d):
    """行方を1行にする。**7語すべてを出す。0でも出す**（正本 6節）。

    同じ規則を `write_kazu` の表（上）は守っていたのに、
    画面に出すこの1行だけが `if kazu["行方"].get(y)` で 0 を落としていた。
    実データ 2026-09-20 では `行方: 取下げ 1／待ち 105` としか出ず、
    **落札・不調・消えた・見に行っていない・読めない の5語が画面から消えていた。**
    起きなかった語が消えると、「0件だった」と「そもそも数えていない」が
    見分けられない。**欠けているキーは0ではない。**
    """
    return "行方: " + "／".join("%s %d" % (y, d.get(y, 0)) for y in YUKUE)


def write_kazu(rows, cells=None, today=None, cell_rows=None):
    """数が合うかを `data/parse-unknown.md` の章に書く。合わなければ落とす。

    **黙って通さない。** 合わない日は index.json を作らずに止める。
    生データは workflow の `if: always()` で保存ずみなので、
    止めても取り直せないものは失われない（正本 9節）。
    """
    d = kazu_ga_au(rows, cells, today, cell_rows)
    body = [
        "**1行は必ず1つの行方に入る。足すと見た行の数になる。**",
        "正本の「升の合計 ＋ not_counted ＝ 見た行の数」は、"
        "1行が2つ以上の升に入るこのサイトでは閉じない。"
        "行方（在庫）と内訳（流量）に分けて見ている"
        "（docs/seihon-toiawase.md #11）。",
        "",
        "| 行方 | 件数 | index.json の欄 |",
        "| --- | ---: | --- |",
    ]
    for y in YUKUE:
        body.append("| %s | %d | %s |"
                    % (y, d["行方"].get(y, 0), YUKUE_KEY.get(y, "（出していない）")))
    body.append("| **合計** | **%d** | 見た行 %d |"
                % (sum(d["行方"].values()), d["見た行"]))
    if d["升にならない行"]:
        body += ["", "**升が1つもできない行が %d 件ある。**"
                     "行方は付いているのに、升にも not_counted にも出ていない。"
                     "日付の列が読めていない見込み。" % d["升にならない行"]]
    if d["食い違う合図"]:
        body += ["", "**合図が食い違う行が %d 件ある。**"
                     "開札日より前に消えたのに結果が出ている、という形。"
                     % d["食い違う合図"]]
    if d["食い違い"]:
        body += ["", "**合っていない。**"] + ["- " + b for b in d["食い違い"]]
    report.put_chapter(UNKNOWN_PATH, "数が合うこと", "\n".join(body))
    if d["食い違い"]:
        raise RuntimeError(
            "数が合わない。黙って落としている。\n  "
            + "\n  ".join(d["食い違い"])
            + "\n詳しくは data/parse-unknown.md の「数が合うこと」")
    return d


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
# 正本 6節「種別には段階も結果も入る」のとおり後ろには段階を入れている）。
#
# **軸を1本落としたまま升を分けると、同じ3つ組の升がいくつも出る。**
# 読む側はどれがどれか分からず、足すこともできない。しかも種別で割ったぶん
# 1〜2件の升が増えるので、伏せ字だらけになったうえに、
# 実数で出た升との引き算で伏せた値が戻る（正本 3.2）。
#
# そこで index.json 向けには**種別を畳んで**数え直す。種別ごとの内訳は
# data/agg/monthly.json に残るので、落としているわけではない。
INDEX_FIELDS = tuple(f for f in BUCKET_FIELDS if f != "kind")


# 結果の升は、子を足すと親になる（結果 ＝ 落札 ＋ 不調）。
# この関係があると引き算で伏せた升が戻るので、正本 3.2 の手当てが要る。
# 公告は「公告 ＝ 公告-初出 ＋ 公告-再出」だが再出の升を出していないので、
# 引き算しても何も決まらない。まとまりとして扱わない。
RESULT_FAMILY = (KEKKA, OCHI, FUCHO)

# 公告も同じ形。公告 ＝ 公告-初出 ＋ 公告-再出。
# 前は再公告の升を出していなかったが、**出さなくても引き算はできる。**
# 公告6 − 公告-初出5 ＝ 1 で、再出が1件だと分かってしまう。
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
            if stage != OCHI:
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


def write_unresolved(rows, today=None):
    """段階が決まらなかった行を、人が見られるところに書き出す。件数を返す。

    **数えるのは `yukue()` の1か所だけ**（正本 9節・2026-09-19）。
    前はここで `unresolved()` `undecided()` `gone()` を別々に呼んでいた。
    3つは排他ではないので、同じ行が2つの章に入り、
    **同じファイルの中で「数が合うこと」の表と件数が食い違っていた。**

    **升は作らない。記録だけ残す**（正本 9節・2026-09-19）。
    「不明」という段階を作ると、横断ハブで4サイトの不明が1つの塊になる。

    **不明は値ではなく徴候。** ここが増えていたら、段階の語彙が足りていない印。
    減らすのが仕事で、固定するものではない。
    """
    bad = [r for r in rows if yukue(r, today) == "読めない"]
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
    hold = [r for r in rows if yukue(r, today) == "取下げ"]
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
    lost = [r for r in rows if yukue(r, today) == "消えた"]
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
            # **`status` の列を落とさない**（2026-09-19）。
            # 一覧から消えるのは取下げを見つける主な手段なので、
            # 「読めない語」と「消えた」は同じ行で起きやすい。
            # `unresolved()` は消えた行を外すので、status の列をここで
            # 出さないと、**読めなかった語がどこにも現れない**。
            # 語彙の穴を減らすのがこちらの仕事なのに、徴候が黙る
            "| 制度 | 消えたときの status | 消えた月 | 開札の予定月 | 件数 |",
            "| --- | --- | --- | --- | --- |",
        ]
        n = {}
        for r in lost:
            k = (r.get("system") or "", r.get("status") or "（空）",
                 (r.get("gone_on") or "")[:7], month_result(r))
            n[k] = n.get(k, 0) + 1
        for k in sorted(n):
            body3.append("| %s | `%s` | %s | %s | %d |" % (k + (n[k],)))
    report.put_chapter(UNKNOWN_PATH, "消えた物件（取下げか繰り越しか未判定）",
                       "\n".join(body3))
    # **回の数と物件の数は別**（このファイルの上の「数えるのは回。物件ではない」）。
    # 「消えた物件: %d 件」と名乗りながら、数えていたのは行（回）だった。
    # 同じ物件の2つの回が消えれば 2 と出る。物件は1つ。
    return (len(bad), len(hold), len(lost),
            len({r.get("property_key") or r.get("key") for r in lost}))


def monthly_doc():
    """`data/agg/monthly.json` に載せる説明。**読む人がここだけで読める形に。**

    main() の中に埋めていたので、**出している説明を検査が一度も読めなかった。**
    切り出したのは、説明の語が中身とずれていないかを見るため（3段目）。
    """
    return {
        "公開しない": NOT_PUBLIC,
        "粒度": ryudo(),
        "段階": "予定／公告／結果 の3つ。段階の内訳は「-」でつなぐ。"
              "公告＝その月にこちらが見た回（初出＋再出）、公告-初出＝こちらが初めて見た回、"
              "結果＝開札された回（落札率の分母）。"
              "**結果の語は 落札／不調 の2つだけ**（正本 6節）。"
              "落札＝そのうち売れた回、不調＝売れなかった回。"
              "段階と結果を1つの升に混ぜない",
        "件数": "count は**回**の数（物件の数ではない）。"
              "count は機械が読む（null は1か2）。count_label は人に見せる",
        "件数のぼかし": "1〜2件の升は実数を出さず \"1-2\" と書く",
        "中央値": "元になった**値**の個数が3未満のときは null。"
                "件数（回の数）とは別もので、値が欠けている回があると食い違う",
        "出していない升": "親（合計）の段階。%s。子を足せば出る" % "／".join(FAMILIES.parents),
    }


def main():
    rows = load_rows()
    cells = aggregate(rows, with_raw=True)

    # **数が合うかを、書き出す前に確かめる**（正本 3.2・2026-09-19）。
    # 合わない日は monthly.json を書かずに止める。
    # 集計は毎回作り直せるので、書かずに止めても取り直せないものは失われない。
    # 生データは workflow の `if: always()` で保存ずみ（正本 9節）。
    kazu = write_kazu(rows, cells, today_str())
    print(yukue_gyou(kazu["行方"]))

    # **実数は出力に残さない**（with_raw は引き算の手当てと検査のためだけ）
    for c in cells:
        c.pop("_n", None)

    # **親（合計）の升は出さない**（正本 3.2）。
    # 公告 = 公告-初出 + 公告-再出 なので、親を並べると
    # 「公告6 − 公告-初出5 = 再出1」と、伏せた升が引き算で戻る。
    # 読者は子を足せばよい。子は fill_siblings で全部そろえてある。
    parents = [c for c in cells if FAMILIES.is_parent(c["stage"])]
    cells = [c for c in cells if not FAMILIES.is_parent(c["stage"])]
    out = dict(monthly_doc(), generated_at=today_str(), cells=cells)
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print("行データ %d 件 → 升 %d 個" % (len(rows), len(cells)))
    bad, hold, lost, lost_bukken = write_unresolved(rows, today_str())
    if bad:
        # **升にはしない。** 黙ってもいない
        print("  **段階が決まらなかった行: %d 件**（data/parse-unknown.md）。"
              "升は作っていない。語彙が足りていない印" % bad)
    if hold:
        print("  置き場が決まっていない値が書いてある行: %d 行"
              "（data/parse-unknown.md）。"
              "読めている。正本が置き場を決めるまで升にしない" % hold)
    if lost:
        # **回と物件を両方出す。** 同じ物件の2つの回が消えれば 回2／物件1
        print("  **消えた回: %d 回（物件 %d 件）**（data/parse-unknown.md）。"
              "取下げか繰り越しか、再登場を待たないと決められない"
              % (lost, lost_bukken))
    if parents:
        # 何を落としたかは黙らない
        print("  引き算で戻るので出さなかった親の升: %d 個（%s）"
              % (len(parents), "／".join(sorted({c["stage"] for c in parents}))))


if __name__ == "__main__":
    main()
