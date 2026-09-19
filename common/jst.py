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

    from common.jst import today, today_str
"""

from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))


def now():
    """いまの日本時間。"""
    return datetime.now(JST)


def today():
    """今日の日付（日本時間）。datetime.date を返す。"""
    return now().date()


def today_str():
    """今日の日付（日本時間）を 2026-09-15 の形で返す。"""
    return today().isoformat()
