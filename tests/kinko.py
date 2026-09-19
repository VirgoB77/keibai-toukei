#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""金庫（生データ）が見えているかを、テストの側から確かめる。

公開用のリポジトリには生データが入らない（正本 9節）。
走るときは、公開用の Actions が deploy key で金庫を `_raw/` に checkout し、
`ln -s` で今までのパスにつなぐ。**つながっていれば data/rows がある。**

だから、金庫が要るテストは2通りの顔を持つ。

    素で clone した公開用の木   金庫が無い。**skip が正しい**
    Actions の中               金庫がある。**走らないとおかしい**

**「金庫が無いから落ちた」を「テストが壊れた」と読ませない。**
理由が分かる形で skip する。

そして CI の中では skip させない。金庫がつながっていないのに走り続けると、
**その日の出力が空のまま公開側に載る**（正本 9節「鳴らせていない見張り」）。
"""

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 金庫にしか無いもの。1つでも欠けていたら、つながっていない
MARKS = ("data/rows", "data/agg", "data/raw")


def missing():
    """つながっていない置き場。全部あれば空。"""
    return [m for m in MARKS if not os.path.isdir(os.path.join(ROOT, m))]


def present():
    return not missing()


def need(case):
    """金庫が要るテストの先頭で呼ぶ。無ければ skip、CI なら落とす。"""
    gone = missing()
    if not gone:
        return
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
        case.fail(
            "**金庫がつながっていない**（%s が無い）。\n"
            "公開用の Actions は deploy key で金庫を _raw/ に checkout し、\n"
            "ln -s で今までのパスにつなぐ。つながっていないまま走ると、\n"
            "その日の出力が空のまま公開側に載る。\n"
            "Secret RAW_DEPLOY_KEY と、金庫の Deploy keys を見ること"
            % "・".join(gone))
    case.skipTest(
        "金庫が見えていない（%s が無い）。"
        "公開用の木を素で clone したときは、これが正しい" % "・".join(gone))
