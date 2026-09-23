# 競売統計 設計・移行の履歴

> **これは設計・移行の履歴。** 現在の仕様・決まりの根拠は [DESIGN.md](DESIGN.md)。
> **このファイルを、現在の仕様の根拠として使わない。**
> ここにある文は、DESIGN.md にあった当時の文をそのまま移したもの。
> 古い言い方・やめた案・当時の引用・当時の状態を、今の形に直していない。

## 3章「棚の定義」から

### 3.4 すでにある棚と空いている場所

- アットホーム「官公庁物件情報」: 公売と国・公有財産売払を扱う。官公庁から依頼を受けた分で、公開しているのは一部
- 財務省「国有財産の売却情報サイト」: 全国の財務局の一般競争入札物件と先着順物件を検索できる（アットホームの空き家バンク基盤）
- KSI官公庁オークション: 公売と公有財産売却が別カテゴリ
- 近畿財務局「地方公共団体（管内）の公有地売却情報」と国交省「公的不動産（PRE）売却・貸付け情報」: 自治体ページへのリンク集。**収集先の種を蒔く索引に使う**
- 空いている場所: 結果（落札価格）のアーカイブ、4段の同じ物差し、大阪兵庫の市町まで全部、円/㎡

## 「公開側」から

### 当てたもの・まだのもの（2026-09-19）

**⓪（アカウント Settings → Pages → Verified domains）は済んだ。**
WHOIS は代理公開。

| | 当てたか | |
| --- | --- | --- |
| `site_id` = `keibai-toukei` | ✅ 09-18 | `records` が0件のうちに |
| `id` の接頭辞 = `keibai` | ✅ 09-18 | 同上 |
| UA = `kujiraya archive bot (keibai-toukei; …)` | ✅ 09-19 | ⓪が済んだので据え置きを解いた |
| 金庫を `keibai-toukei-raw` に rename | ✅ 09-19 | ①（人） |
| 公開用 `keibai-toukei` を履歴ゼロで作る | ✅ 09-19 | ②（人） |
| 公開用の木を入れる（手順3） | ✅ 09-19 | 42ファイル・1コミット |
| 名前による自己停止（`*-raw` なら止まる） | ✅ 09-19 | 下の「見張り」 |
| deploy key（④） | ✅ 09-19 | 運営者が作る。入ったら公開用を1回通す |
| Pages に `keibai-toukei.com`（⑤） | ✅ 09-19 | ④のあと |
| `site_url` | ✅ 09-19 | ⑤のあと。下記 |
| 金庫から `.github/workflows/` と印を消す | ✅ 09-19 | **公開用が1回通ってから**（下の「見張り」） |

**`site_url` だけは、⓪のあとすぐには入れなかった。**

⓪は「**ほかの人にドメインを取られない**」ことを保証するだけで、
「**そこに何かがある**」ことは保証しない。2026-09-19 時点で
`keibai-toukei.com` は DNS が引けない（`curl` で確認）。

正本 3.4「**404 を入れない。** まだ公開していないページのURLは入れない。
確認できない名乗りは、名乗らないより不審に見える」。

**Pages が配信を始めたのを確かめてから入れた**（確かめた中身は `common/site.json` の `_meta`）。UA を先に当てられたのは、
そちらが URL ではなく**名前**だから。同じ「⓪のあと」でも、
名前と URL では確かめられる時期が違う。

### 向きが変わった（2026-09-17）

前は「private の keibai-data で Actions が走り、公開側へ push する」と書いてあった。
**正本 9節は逆で、走るのは公開用の Actions。** 公開用は public なので Actions が無料で、
`GITHUB_TOKEN` で自分に push できる。収集用は置き場に徹する。

変わるのは3つ。

| | 前 | いま |
| --- | --- | --- |
| Actions が走る場所 | keibai-data（private） | 公開用（public） |
| 鍵 | ic-log 宛ての fine-grained PAT（`IC_LOG_TOKEN`） | **deploy key**（`RAW_DEPLOY_KEY`） |
| 向き | 金庫 →（push）→ 公開 | 公開 →（checkout）→ 金庫を隣に出す |

PAT をやめるのは、**期限が来ると黙って止まる**から。deploy key は1本のリポジトリにしか
効かないので、漏れたときの範囲も狭い。

### 移植元は、まだ走っていなかった（2026-09-17 時点）

大型店日報の同じ仕組みは、2026-09-17 時点では**まだ main に入っていなかった**
（未マージの枝 `chk/claude/vault-prep` にあった）。一度も本番で走っていなかったので、
そのまま写す前に、向こうが1回走るのを待つか、こちらを先行させるかを決める必要があった。

### 公開用を作るまでは1本だった

鍵が無いあいだ1本の形（`git add data` の丸ごと）で動いてよいのは、
**生データを既に追跡している移行前のリポジトリだけ**（正本 9節）。収集用はそれに当たった。
だから公開用を作るまでは、毎朝の workflow をそのまま使った。公開用を作った日から上の形に移った。

### 前身の置き場（2026-09-17 に確かめた。**きれいだった**）

正本 9節「前身の置き場を見る」。作り直しの手順は「いま書いているリポジトリ」が
対象で、**その前に使っていた置き場**は対象外になる。
姉妹サイト（大型店日報）が、前身の public なリポジトリに
**伏せる前の出力 3,525枚**が履歴から読める状態で残っていたのを見つけた。

**このサイトは、どこからも分かれてきていない。** 確かめたのは5つ。

| 見たこと | 結果 |
| --- | --- |
| 親の無いコミット（ルート）の数 | **1つだけ**。よそから履歴を持ち込んでいない |
| 最初のコミットの中身 | 12ファイル。`DESIGN.md` `README.md` `recon.py` `sources.json` `tests/` と `.gitkeep` だけ。**データは1件も無い** |
| `ic-log`（`publish.sh` の宛先だった既存のリポジトリ） | 全履歴 165 コミットに `keibai/` のパスが**一度も無い**。いまは private・fork 0 |
| ほかの public なリポジトリ | `ogataten-nippo` `gaitou-settou` `maisoku` のいずれにも競売・公売のものは無い |
| `data/public/index.json` の全履歴 | **どの版も `records: 0`**。升は 0 → 40 → 92 と増えたが、伏せ字は全部入っている |

`index.json` の `site` が `"ic-log"` になっていたのは、
`make_index.py` の既定値がそう書いてあっただけだった。

    SITE = os.environ.get("SITE", "ic-log")
    BASE_URL = os.environ.get("SITE_URL", "https://virgob77.github.io/ic-log/keibai/")

**送る先として書いてあっただけで、一度も送っていない**（`publish.sh` は存在しない）。
2026-09-17 に `keibai-data` / 競売統計 に直した。

伏せる前の値が入っているのは `data/raw/` `inbox/` `data/rows/` の3つで、
**どれもこのリポジトリの中だけ**にある。ここは private のまま。

fork は 0。コピーは存在しない。

## 5章「情報源」から

### 5.3 国有財産（近畿財務局）

| id | url | 何が載るか | kind |
| --- | --- | --- | --- |
| kokuyu-kinki-yotei | `https://lfb.mof.go.jp/kinki/kanzai/pagekinkihp029000143.html` | 一般競争入札予定物件（売却）。「次回入札で入札予定の物件」と「今後入札を予定している物件」 | kokuyu-list |
| kokuyu-kinki-kekka | `https://lfb.mof.go.jp/kinki/kanzai/np-bid-result_00001.html` | 一般競争入札（売却）の開札結果及び契約状況。受付終了の翌営業日から開札までは応札の有無も出る | kokuyu-result |
| kokuyu-kinki-senchaku | URL未確認（「すぐに購入できる物件」＝先着順の売却物件） | 先着順の物件と売却価格 | kokuyu-list |
| kokuyu-kinki-top | `https://lfb.mof.go.jp/kinki/kanzai/pageknkhp00200005.html`（旧ドメイン `kinki.mof.go.jp` からの移行先。要確認） | 国有財産の売却情報の入口 | index |

- 近畿財務局の期間入札は回数が少ない（年1〜2回の見込み）。先着順は随時。
- 物件調書PDFはリンクだけ残す（大きいものが多い）。2MB以下なら取る。
- 参照だけ（取らない）: 財務省「国有財産の売却情報サイト」`https://kokuyuzaisan.akiya-athome.jp/`（アットホーム基盤。規約が別）、
  財務省「国有財産の売却情報」`https://www.mof.go.jp/policy/national_property/summary/sellout/index.htm`（国有財産情報公開システムへの入口。要確認）

### 5.4 公有財産（自治体）

まず府県・政令市。市町は 5.5 の索引から偵察して、一覧のある所から足す。

| id | url | 何が載るか | kind |
| --- | --- | --- | --- |
| koyu-osaka-pref | `https://www.pref.osaka.lg.jp/o050050/kanzai/baikyakutou/index.html` | 府有地等の入札・先着順による売却。今後の入札予定、先着順物件、一般競争入札の結果、サウンディング。一般競争入札はKSIで実施（案内と結果は府ページに残る） | koyu-list / koyu-result |
| koyu-hyogo-pref | `https://web.pref.hyogo.lg.jp/kk30/pa10_000000015.html` | 県有地の売却。一般競争入札（郵送型）のお知らせPDF（6〜8MB。取らない、リンクだけ）、先着順物件 | koyu-list |
| koyu-hyogo-pref-kekka | `https://web.pref.hyogo.lg.jp/kk30/pa10_000000039.html` | 一般競争入札による県有地売払い結果 | koyu-result |
| koyu-hyogo-pref-cat | `https://web.pref.hyogo.lg.jp/pref/cate3_618.html` | 県有財産売却のカテゴリ（インターネット一般競争入札の案内など） | index |
| koyu-osaka-city | URL未確認（大阪市「市有不動産売り払い」。大阪府ページからリンクあり） | 市有不動産の売払 | koyu-list / koyu-result |
| koyu-kobe-city | `https://www.city.kobe.lg.jp/a59688/shise/kobai/sell/index.html` | 市有地売却・貸付関係の新着（複数の局にまたがる） | index |
| koyu-kobe-city-nyusatsu | `https://www.city.kobe.lg.jp/a59688/shise/kobai/sell/nyusatsu00.html` | 入札による売却（回ごとのページと開札月） | koyu-list |
| koyu-kobe-city-r7 | `https://www.city.kobe.lg.jp/a59688/r7ippan.html` | 令和7年度一般競争入札による神戸市有地売却（物件・期限の例） | koyu-list |
| koyu-sakai-city | URL未確認 | 堺市の市有地売却 | `enabled: false` |

- 貸付・定期借地・サウンディング（意見募集）は取らない。売却だけ。
- 自治体の「結果」は契約課の入札結果ページなど別の場所にあることが多い。偵察で探し、見つからなければ note に書く。

### 5.5 索引（種まき用。取り込まず、人が見て sources.json に足す）

- 近畿財務局「地方公共団体（管内）の公有地売却情報」: `https://lfb.mof.go.jp/kinki/np-localgovernment-link_00001.html`
- 国交省「公的不動産（PRE）売却・貸付け情報」: `https://www.mlit.go.jp/totikensangyo/totikensangyo_tk5_000166.html`
- 兵庫県の県有地ページ（市町有地の売却情報へのリンクがある）

## 11章「段階と完了条件」から

### Phase 0 偵察（1〜2日）

- 非公開リポを作る（人。当時の名前は `keibai-data`）。`sources.json`（5章、4段すべて）と `recon.py`。Actions で1回手動実行
- 完了: `data/recon-report.md` に全収集先の robots／応答／判定（表・PDF・わからない）が出ている。
  3点セットを1本も取っていない。自動化できる kind と inbox に回す kind が決まっている。13章の未確認が埋まっている

### Phase 1 取り込み（2〜3日）

- `parse.py`（bit-past, bit-schedule, bit-result, bit-list, kobai-nta, kokuyu-list, kokuyu-result）。fixtures は inbox に手で置いた実物
- 完了: 競売3年分の rows が入り、件数が「対象件数」と一致。競売・公売の rows に町丁目以下が無いことをテストが保証。
  国有財産の rows に住所・面積・最低売却価格が入る。key の重複なし

### Phase 2 集計（1日）

- `aggregate.py` と秘匿ルール、`winner_name` の個人名禁止。unittest で定義（7章）を固定
- 完了: `data/agg/monthly.json`（社内）と `data/public/index.json`（公開）が出て、競売の n<3 の価格が null
