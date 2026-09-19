#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""住所を、姉妹サイトで同じ形にそろえる。

正本は https://github.com/VirgoB77/ogataten-nippo/blob/main/docs/kyotsu-shiyo.md
（4. common/addr.py）。直すときは、まず正本を直してから各サイトにコピーする。


鯨屋（くじらや）の3サイト——大型店日報・競売公売・開発届出——を
「住所」で突き合わせて、市区町村ごとの横断ページを作るための土台。
役所ごとに書き方が違う住所を、1つの形に直して `addr_key` を作る。

    from common.addr import normalize
    normalize("大阪府", "大阪市北区", "梅田一丁目1番1号 グランフロント大阪")
    # → {"pref": "大阪府", "city": "大阪市北区", "city_code": "27127",
    #    "addr": "梅田1-1-1グランフロント大阪", "addr_key": "27127|梅田1-1-1"}

`addr` には建物名を残し、`addr_key` からは落とす。
同じ土地なら、どのサイトから来ても `addr_key` が一致する。

このファイルは3つのリポジトリに同じものを置く（コピーして使う）。
直したら3か所そろえること。Python 3 の標準ライブラリだけで動く。
"""

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
CODES_PATH = os.path.join(HERE, "city_codes.json")


# ---------------------------------------------------------------- 市区町村コード

_CODES = None          # (pref, city) -> code
_CODES_BY_CITY = None  # city -> [code, ...]  市名だけで引くとき用


def _load_codes():
    """総務省の全国地方公共団体コードを読む。1回だけ読んで持っておく。"""
    global _CODES, _CODES_BY_CITY
    if _CODES is not None:
        return
    _CODES, _CODES_BY_CITY = {}, {}
    try:
        with open(CODES_PATH, encoding="utf-8") as f:
            rows = json.load(f)["cities"]
    except (OSError, ValueError, KeyError):
        return
    for r in rows:
        _CODES[(r["pref"], r["city"])] = r["code"]
        _CODES_BY_CITY.setdefault(r["city"], []).append(r["code"])


def city_code(pref, city):
    """都道府県名と市区町村名から5桁のコードを引く。見つからなければ空文字。

    都道府県が空でも、市区町村名が全国で1つだけなら引ける（西宮市など）。
    同じ名前が複数ある町村（府中市・太子町など）は、都道府県が無いと決められない
    ので空文字を返す。推測で埋めない。
    """
    _load_codes()
    pref = (pref or "").strip()
    city = (city or "").strip()
    if not city:
        return ""
    if pref:
        return _CODES.get((pref, city), "")
    found = _CODES_BY_CITY.get(city, [])
    return found[0] if len(found) == 1 else ""


# ---------------------------------------------------------------- 文字をそろえる

# 全角の英数字を半角にする。記号は触らない（建物名の「＆」などを壊さないため）
_ZEN = "".join(chr(c) for c in
               list(range(0xFF10, 0xFF1A)) +    # ０-９
               list(range(0xFF21, 0xFF3B)) +    # Ａ-Ｚ
               list(range(0xFF41, 0xFF5B)))     # ａ-ｚ
_HAN = "".join(chr(ord(c) - 0xFEE0) for c in _ZEN)
_TO_HAN = str.maketrans(_ZEN, _HAN)

# ハイフンに見える記号をそろえる。カタカナの長音「ー」は入れない
# （「ハイツ」「タワー」などの建物名を壊してしまうため）
_DASHES = str.maketrans({
    "－": "-", "−": "-", "‐": "-", "‑": "-", "–": "-", "—": "-", "ｰ": "-",
})

_KANJI_DIGIT = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
                "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_KANJI_UNIT = {"十": 10, "百": 100, "千": 1000}


def kanji_to_int(s):
    """漢数字を算用数字にする。二十三 → 23、十一 → 11、三 → 3。"""
    total, current = 0, 0
    for ch in s:
        if ch in _KANJI_DIGIT:
            current = _KANJI_DIGIT[ch]
        elif ch in _KANJI_UNIT:
            unit = _KANJI_UNIT[ch]
            total += (current or 1) * unit
            current = 0
        else:
            return None
    return total + current


# 漢数字を直すのは、そのすぐ後ろが「丁目・番地・番・号」のときだけ。
# 地名そのものに入っている漢数字（三田市・九条）まで直すと、別の場所になってしまう。
_KANJI_NUM = re.compile(r"[〇零一二三四五六七八九十百千]+(?=丁目|番地|番|号)")

# 数字のうしろが町名の続きのときは、まだ番地に入っていない。
# 「甲子園七番町」「北十二条西」など。ここで切ると町名が消える。
_TOWN_AFTER_NUM = re.compile(r"^(番町|番丁|条|線|軒|丁目|町|丁)")


def _clean(text):
    """文字の見た目のちがいを、まとめてそろえる。"""
    s = (text or "").strip()
    s = s.translate(_TO_HAN).translate(_DASHES)
    # **空白を先に落とす**（2026-09-19 に順番を上げた）。
    # 前はハイフンにする4本より**後ろ**にあった。すると
    # 「梅田 1 丁目 1 番 1 号」のように空白が挟まった住所で、
    # `([0-9]+)丁目` が1本も当たらない。
    #
    #     空白なし  梅田1丁目1番1号  → 町丁目 梅田1
    #     空白あり  梅田 1 丁目…     → 町丁目 **梅田1丁目**
    #
    # 同じ場所が2つの鍵に割れて、姉妹サイトとつながらない。
    # しかも `梅田1丁目` という形は町丁目の一覧には無いので、
    # あとから当て直すこともできない。**先に落とせば①で決まる。**
    s = re.sub(r"[\s\u3000]+", "", s)
    s = _KANJI_NUM.sub(lambda m: str(kanji_to_int(m.group())), s)

    # 「大字」「字」は書く役所と書かない役所があるので、落としてそろえる
    s = s.replace("大字", "")
    s = re.sub(r"(?<![0-9])字", "", s)

    # 丁目・番地・番・号をハイフンにする。
    # ただし「7番町」「1号線」のように町名・道路名の一部のときは残す
    s = re.sub(r"([0-9]+)丁目", r"\1-", s)
    s = re.sub(r"([0-9]+)番地", r"\1-", s)
    s = re.sub(r"([0-9]+)番(?![町丁])", r"\1-", s)
    s = re.sub(r"([0-9]+)号(?![室棟館線])", r"\1-", s)

    s = re.sub(r"-{2,}", "-", s)       # 続いたハイフンを1本に

    # 「1号 グランフロント大阪」が「1-グランフロント大阪」になってしまう。
    # 番地の切れ目のハイフンは、後ろに数字が来るときだけ意味がある。
    # 数字のうしろにあって、次が数字でないハイフンは落とす。
    # 建物名の中のハイフン（OM-SQUARE）は、前が数字でないので残る。
    s = re.sub(r"(?<=[0-9])-(?![0-9])", "", s)
    s = s.strip("-")
    return s


def _town(core):
    """番地を落として、町丁目までにする。「角田町3-25」→「角田町」。

    ここで落とすのは**番地**の数字だけ。丁目の数字は町丁目の一部なので
    落としてはいけない（正本 4節「丁目は必ず含める」）。丁目があるかどうかは
    文字列の見た目では決まらないので、_chome_town() が元の住所を見て決める。
    """
    return re.sub(r"[0-9][0-9\-]*$", "", core).rstrip("-")


# 「N丁目」の N は町丁目の一部。「N番」の N は番地なので町丁目ではない。
# 正規化するとどちらも同じ「梅田1-」「角田町3-」になって見分けがつかなくなるので、
# ハイフンに置き換える**前**の住所を見て決める（正本 4節 ①）。
_CHOME = re.compile(r"([0-9]+)丁目")


def _chome_town(addr):
    """元の住所に「N丁目」があれば、町名＋丁目の番号までを返す。無ければ空文字。

    正本 4節 ①「正規化で自分がハイフンにした場所があれば、その手前まで（確実）」。
    **どこを置き換えたかは自分が知っている**ので、そこで切れば確実に決まる。
    入力にもとからあったハイフン（「梅田1-1-1」の1本目）と取り違えない。

        梅田一丁目1番1号  → 梅田1      「丁目」があるので 1 は丁目
        角田町3番25号     → （空）     「丁目」が無いので 3 は番地

    丁目が無いときは空文字を返し、呼ぶ側が _town() の番地落としに回す。
    """
    s = (addr or "").strip().translate(_TO_HAN).translate(_DASHES)
    # **空白を先に落とす。** `_clean()` と同じ順番。
    # ここが遅れると「梅田 1 丁目」で `([0-9]+)丁目` が当たらず、
    # ①が決められないまま②の入口へ流れる
    s = re.sub(r"[\s\u3000]+", "", s)
    s = _KANJI_NUM.sub(lambda m: str(kanji_to_int(m.group())), s)
    m = _CHOME.search(s)
    if not m:
        return ""
    head = s[:m.end(1)]                       # 丁目の番号まで含める
    head = head.replace("大字", "")
    head = re.sub(r"(?<![0-9])字", "", head)
    return re.sub(r"[\s\u3000]+", "", head)


def _core(addr):
    """建物名・部屋番号を落として、土地の部分だけにする。

    番地の並び（数字とハイフン）が終わったところで切る。
    「甲子園7番町1-2-3ハイツ101」なら「甲子園7番町1-2-3」。
    番地が無ければ、そのまま全部を返す（町名だけの住所）。

    ハイフンで部屋番号までつなげて書いてある住所（1-2-3-405）は、
    405 が部屋なのか枝番なのか区別できない。そこは切らずに残す。
    """
    i, end = 0, None
    while True:
        m = re.search(r"[0-9][0-9\-]*", addr[i:])
        if not m:
            break
        start, stop = i + m.start(), i + m.end()
        rest = addr[stop:]
        t = _TOWN_AFTER_NUM.match(rest)
        if t:
            i = stop + len(t.group())   # まだ町名の途中。次の数字を探す
            continue
        end = stop
        break
    return (addr[:end] if end else addr).rstrip("-")


def to_city(text, pref=""):
    """住所の文字から、都道府県と市区町村を取り出す。

        to_city("兵庫県西宮市甲子園町1-1") → ("兵庫県", "西宮市")
        to_city("大阪市北区梅田1-1-1")     → ("大阪府", "大阪市北区")

    総務省の一覧に載っている名前と突き合わせるので、推測しない。
    政令市は区まで。見つからなければ ("", "") を返す。

    競売・公売の行データを作るとき、**公開する前に必ずここを通す**。
    町丁目より細かいものが市区町村の欄に混ざらないようにするため。
    """
    _load_codes()
    s = (text or "").replace("　", " ").strip()
    if not s:
        return ("", "")
    best = None
    for (p, c), _code in _CODES.items():
        if pref and p != pref:
            continue
        if c and c in s:
            # いちばん長い名前を採る。「大阪市」より「大阪市北区」を優先する
            if best is None or len(c) > len(best[1]):
                best = (p, c)
    return best or ("", "")


# ---------------------------------------------------------------- 入口

def normalize(pref, city, addr):
    """住所を3サイト共通の形にして返す。

    戻り値は次の7つ。値が決められないものは空文字にする（推測で埋めない）。

        pref           都道府県名
        city           市区町村名
        city_code      全国地方公共団体コード5桁
        town           町丁目（丁目を含む）        例 "梅田1"
        addr           表示用の住所（市区町村から書く。建物名も残す）
                                                  例 "大阪市北区梅田1-1-1"
        addr_key       "<city_code>|<番地まで>"    例 "27127|梅田1-1-1"
        addr_key_town  "<city_code>|<町丁目まで>"  例 "27127|梅田1"

    鍵が2本あるのは、サイトによって出せる精度が違うため。
    番地まで分かっているもの同士は addr_key で、
    片方が町丁目までしか出せないときは addr_key_town で突き合わせる。
    **両方のキーを必ず出す。** 片方しか作れないときは、もう片方を空文字にする。
    """
    pref = (pref or "").strip()
    city = (city or "").strip()
    s = _clean(addr)

    # **収集先の市を、住所に被せない**（正本 4節・2026-09-19）。
    #
    # 住所の文字そのものが**別の市**を名乗っているなら、呼ぶ側の市は
    # 当たっていない。被せると、**形は正しいので検査を通るのに、
    # この世に無い住所ができる。**
    #
    #     normalize("大阪府", "大阪市北区", "兵庫県西宮市甲子園町1-1")
    #     → addr "大阪市北区兵庫県西宮市甲子園町1-1"、コードは大阪市北区
    #
    # 姉妹サイト（開発系）が実物で踏んだ。大阪市の一覧に他県の土地が
    # 入っていて、456件中454件が切れ、残り2件を呼ぶ側の市で埋めていた。
    # **2件を埋めるために454件を汚さない。**
    #
    # 食い違ったときは**空のまま返す。** 埋めるより、つながらないほうがよい
    # （正本 4節③「推測で埋めない」）。落ちた升は
    # `data/index-dropped.md` に出るので、黙って消えはしない。
    #
    # **住所から市が読めないときは、呼ぶ側の値を使う。** これは被せではない。
    # 公売の表のように「見出しに市、欄に番地」という正しい分かれ方があり、
    # そこまで拒むと読めるものまで捨てる（このサイトの実データ106行では
    # 105行が住所からも同じ市を読めて、食い違いは0件）。
    見えた = to_city(s)[1]
    if 見えた and city and 見えた != city:
        pref, city = "", ""

    # 「大阪府大阪市北区梅田1-1-1」のように頭から書いてあることがある。
    # pref / city と重なる部分は落として、後ろだけを addr にする
    for head in (pref + city, city, pref):
        if head and s.startswith(head):
            s = s[len(head):]
            break
    s = s.lstrip("-")

    code = city_code(pref, city)
    core = _core(s)

    # 丁目があるならそこまでが町丁目。無いときだけ番地を落として町名にする。
    # **丁目は必ず含める**（正本 4節）。「梅田」でまとめると、
    # 駅の北と南ほど違う梅田1〜3丁目が1つの升に混ざる。
    town = _chome_town(addr)
    if town:
        for head in (pref + city, city, pref):
            if head and town.startswith(head):
                town = town[len(head):]
                break
        town = town.lstrip("-")
    if not town:
        town = _town(core)
    # 表示用の住所は市区町村から書く。よそのサイトに渡したとき、
    # 市区町村の欄を見なくても場所が分かるようにするため
    display = (city + s) if (city and s) else (s or city)
    return {
        "pref": pref,
        "city": city,
        "city_code": code,
        "town": town,
        "addr": display,
        "addr_key": ("%s|%s" % (code, core)) if code and core else "",
        "addr_key_town": ("%s|%s" % (code, town)) if code and town else "",
    }
