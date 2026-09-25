#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""検査の中だけで使う、偽の門の道具（common/kado.py）。

`tests/test_kado.py` の `Oki`（一時フォルダに git を作り、カード・承認・
相手台帳を置く）と同じ形。あちらを直に import せず、ここに小さく作り直した
（`Oki` は `TestCase` で、ほかの検査ファイルから import すると unittest の
収集に紛れ込む。`tests/kinko.py` と同じ、手伝いのモジュールとして置く）。

**本番のコードには「検査のときは通す」道を作らない。** 偽物はここ、
検査の中だけ。

    import nise_kado          # kinko.py と同じ、裸の import
"""
import contextlib
import email.message
import io
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
import urllib.response

from common import kado

UA = "kujiraya archive bot (+https://example.invalid/about; https://example.invalid/form)"
REPO = "keibai-toukei"


class Nise(urllib.request.BaseHandler):
    """偽の相手。URL ごとに (status, headers, body) を返し、来た URL を全部控える。

    `tests/test_kado.py` の `Nise` と同じ形（あちらを直に import せず作り直した。
    `Oki` と同じ理由——unittest の収集に紛れ込ませないため）。
    """
    handler_order = 50

    def __init__(self, kotae):
        self.kotae = kotae
        self.kita = []

    def _open(self, req):
        self.kita.append(req.full_url)
        status, headers, body = self.kotae.get(req.full_url, (404, {}, b""))
        if isinstance(status, Exception):
            raise status
        msg = email.message.Message()
        for k, v in headers.items():
            msg[k] = v
        r = urllib.response.addinfourl(io.BytesIO(body), msg, req.full_url, status)
        r.msg = "nise"
        return r

    https_open = _open
    http_open = _open


def git(root, *args, env=None):
    e = dict(os.environ)
    e.update({"GIT_AUTHOR_NAME": "運営者", "GIT_AUTHOR_EMAIL": "unei@example.invalid",
              "GIT_COMMITTER_NAME": "運営者", "GIT_COMMITTER_EMAIL": "unei@example.invalid"})
    e.update(env or {})
    subprocess.run(["git", "-C", root] + list(args), check=True,
                   capture_output=True, env=e)


def card(**kae):
    """カード1枚。既定は「取ってよい」に要る欄を全部満たしている。"""
    c = {
        "取得元": "ためしの一覧", "相手": "ためし相手", "source種別": "行政",
        "対象URL": "https://example.invalid/data/list.html",
        "対象host": ["example.invalid"],
        "個人情報を含みうる": "分からない", "当事者に個人がありうる": "分からない",
        "個票の粒度": "集計のみ（個票なし）", "所在地の扱い": "個人の所在地は無い",
        # 個人情報・個票の取得前ゲート（民間公開Web v3 §6）。未決なら門が通さない
        "氏名を含みうる": "いいえ", "個人の電話番号を含みうる": "いいえ",
        "個人の生活住所を含みうる": "いいえ",
        "privateに保存する予定": "取得したページそのまま", "publicに出す予定": "件数の集計だけ",
        "公開時の粒度": "市区町村・月ごとの件数",
        "規約確認日": "2026-09-20",
        "規約証跡": {"規約URL": "https://example.invalid/kiyaku.html"},
        "正規提供手段": "無し", "正規提供手段の理由": "API も CSV も無い",
        "承認対象の行為": ["自動取得", "内部保存"],
        "承認する取得方法": {"URL範囲": ["https://example.invalid/data/"],
                         "対象種類": "HTML", "ページ送り・深さ": "1段",
                         "API/feed": "なし", "承認頻度": "1日1回"},
        "重要な原文": "「このサイトの情報は、出典を記載すれば自由に利用できます」",
        "統括判定案": "取ってよい",
        "判定理由": "利用条件が複製・加工・商用を明示的に許している",
        "肯定根拠番号": "1", "不確定事項": "なし", "専門家確認": "不要",
        "再確認期限": "2099-12-31", "カード版": 1,
    }
    c.update(kae)
    return c


def shounin_of(cid, c, ai=False, bot=False, **kae):
    """カード `c`（id=`cid`）にそのまま効く承認の中身。"""
    s = {"カード": cid, "運営者承認": "承認", "承認したカード版": c["カード版"],
         "承認時カード指紋": kado.card_shimon(c), "承認日": "2026-09-24"}
    s.update(kae)
    return s


def repo(cards, daicho=None, shounin=None, ai_shounin=()):
    """一時フォルダに、カード・相手台帳・承認を置いた git の置き場を作る。

    `shounin` は {カードid: 承認の中身}。`ai_shounin` に挙げた id の承認だけは
    AI の commit の印（Co-Authored-By: Claude）を付けて保存する
    （＝そのカードは承認が数えられない、を作るため）。

    戻り値は root のパス。**呼んだ側が後始末をすること**
    （`shutil.rmtree(root, ignore_errors=True)`）。
    """
    root = tempfile.mkdtemp()
    os.makedirs(os.path.join(root, "data", "ref", "shounin"))
    with open(os.path.join(root, "data", "ref", "torimoto-card.json"),
              "w", encoding="utf-8") as f:
        json.dump({"cards": cards}, f, ensure_ascii=False)
    with open(os.path.join(root, "data", "ref", "aite-daicho.json"),
              "w", encoding="utf-8") as f:
        json.dump(daicho or {"aite": {}}, f, ensure_ascii=False)
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "はじめ")
    for cid, s in (shounin or {}).items():
        path = os.path.join(root, "data", "ref", "shounin", "%s.json" % cid)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False)
        git(root, "add", "-A")
        msg = "承認 %s" % cid
        env = None
        if cid in ai_shounin:
            msg += "\n\nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
        git(root, "commit", "-q", "-m", msg, env=env)
    return root


def daicho_of(cards, repo_name=REPO):
    """カードの「相手」「対象host」から、そのまま使える相手台帳を組み立てる。"""
    aite = {}
    for c in cards.values():
        name = c.get("相手") or ""
        if not name:
            continue
        aite.setdefault(name, {"host": [], "担当": repo_name})
        for h in c.get("対象host") or []:
            if h not in aite[name]["host"]:
                aite[name]["host"].append(h)
    # 予約台帳（repo横断）は tests/test_kado.py の「予約台帳」で試す。ここでは要らないと書く
    # （書かなければ、門は要る側に倒れて止まる）
    return {"yoyaku": {"hitsuyou": False}, "aite": aite}


class Kumitate:
    """1つの取得元id・1枚のカードだけの、いちばん小さい組み立て。

    `もと()` を叩くほとんどの検査は、カードが1枚あれば足りる。
    複数枚いるものは `nise_kado.repo()` を直に使うこと。
    """

    def __init__(self, cid="shiken", shounin=True, **card_kae):
        self.cid = cid
        self.card = card(**card_kae)
        cards = {cid: self.card}
        shounin_dict = {cid: shounin_of(cid, self.card)} if shounin else {}
        self.root = repo(cards, daicho_of(cards), shounin_dict)
        self.kinko = tempfile.mkdtemp()

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)
        shutil.rmtree(self.kinko, ignore_errors=True)

    def env(self, **kae):
        e = {"KINKO_DIR": self.kinko, "KINKO_PRIVATE": "1", "RUN_DATE": "2026-09-25"}
        e.update(kae)
        return e

    def kado(self, **kw):
        kw.setdefault("env", self.env())
        # **検査では待たない。** 本物の `MATSU`（5秒）で毎回待つと検査が重くなる。
        # 待つこと自体は common/kado.py 側の検査（tests/test_kado.py）が見る
        kw.setdefault("sleep", lambda _n: None)
        return kado.Kado(self.root, REPO, UA, **kw)

    def hozon_saki(self, cid=None):
        return os.path.join(self.kinko, "raw", cid or self.cid)


class ToosuMon:
    """**通す偽の門。** 門そのものの挙動を試していない検査（読み取り・報告・
    混雑処理など）の中でだけ差し込む（正本の共通指示書 5節）。

    `card_mon()` はいつも空（＝止めない）を返し、`sesshon()` はいつも通す。
    本番のコードには置かない。ここは tests/ の中だけの偽物。
    """

    def card_mon(self, cid, koui=None, hozon_saki=None):
        return []

    @contextlib.contextmanager
    def sesshon(self, cid, koui=None, hozon_saki=None):
        yield self

    def robots_kekka(self, url):
        return True, "許可（検査で通す偽の門）"
