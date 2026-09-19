#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""日付は日本時間で決める。

GitHub のサーバーは世界標準時（UTC）で動いている。
そのまま `date.today()` を使うと、日本ではもう15日なのにサーバーは14日、
ということが毎日9時間ぶん起きる。

ここを1か所にまとめておかないと、
「毎月1日と15日に見に行く」が1日ずれたり、
レポートの日付と保存ファイルの日付が食い違ったりする。
実際に2026-09-15の実行で、規約ページが取られずに飛ばされた。

**時刻ではなく、値を1回だけ決める。**

時間帯を日本時間に寄せるだけでは足りない。それは「たまたま日付をまたがない」
だけで、走る時刻が動けばまた起きる。1回の実行の中で時計を2回見ると、
**2回目が次の日になっていることがある**。

このサイトの実物（2026-09-19 に確かめた）。

    22:30 UTC  走り始める（＝日本時間の翌日 07:30）
    00:32 UTC  commit する（2時間かかる）

commit の時刻に `date -u` を打つと 09-19 が出て、**たまたま合っていた**。
取りに行くのに2時間かかって UTC の日付をまたぐから。
**速くなった日に、黙って1日戻る。**

だから、走り始めに `RUN_DATE` を1回決めて渡す。時計を見るのはここだけ。

    workflow の初手   RUN_DATE=$(TZ=Asia/Tokyo date +%F) → $GITHUB_ENV
    commit のとき     $RUN_DATE（date を2回打たない）
    Python の中       run_date() が RUN_DATE を読む

**読めない RUN_DATE が来たら落とす。** 黙って今日に倒すと、
渡したつもりで渡せていないことに気づけない。

    from common.jst import today, today_str
"""

import os
import re
from datetime import date, datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))

# 走り始めに決めた日を渡す入れ物。workflow が $GITHUB_ENV に置く
RUN_DATE_ENV = "RUN_DATE"
_YMD = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def now():
    """いまの日本時間。**時計を見るのはここだけ。**"""
    return datetime.now(JST)


def today():
    """この実行が「いつ」なのか。datetime.date を返す。

    `RUN_DATE` が渡されていればそれ。無ければ、いまの日本時間の日付。

    **読めない RUN_DATE が来たら落とす。** 黙って今日に倒すと、
    渡したつもりで渡せていないことに気づけない（正本 9節）。
    """
    raw = (os.environ.get(RUN_DATE_ENV) or "").strip()
    if not raw:
        return now().date()
    if not _YMD.match(raw):
        raise RuntimeError(
            "%s が読めない（%r）。YYYY-MM-DD で渡すこと。"
            "**黙って今日に倒さない。** 渡したつもりで渡せていないことに"
            "気づけなくなる" % (RUN_DATE_ENV, raw))
    try:
        return date.fromisoformat(raw)
    except ValueError as e:
        raise RuntimeError("%s が日付にならない（%r）: %s"
                           % (RUN_DATE_ENV, raw, e))


def today_str():
    """この実行の日付を 2026-09-15 の形で返す。"""
    return today().isoformat()
