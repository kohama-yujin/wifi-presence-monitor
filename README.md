# Wi‑Fi Presence Monitor（在室管理）

iPhone ショートカットの Wi‑Fi 接続／切断通知を受け取り、在室状況を Web で表示するツールです。

**仕組み（概要）**

1. 研究室 Wi‑Fi に接続 → iPhone が **学内 IP** へ `POST /wifi_connected`（在室）
2. レスポンスの `public_url`（Cloudflare Quick Tunnel）を iPhone に保存
3. 研究室 Wi‑Fi から切断 → iPhone が **保存した公開 URL** へ `POST /wifi_disconnected`（不在）

切断後は学内 IP に届かないため、切断通知だけ公開トンネル経由にします。

| 画面・機能 | 内容 |
| --- | --- |
| `/` | 学年別のリアルタイム在室ボード |
| `/history` | 過去日の在室履歴（日付切替。当日は対象外） |
| 到着チャイム | サーバ PC で WAV（なければ Windows の既定音） |
| 永続化 | 日付ごと `data/presence/*.json` |

---

## 必要な環境

- Windows
- Python 3.10+
- （公開する場合）cloudflared（Quick Tunnel）

---

## セットアップ

```powershell
cd path\to\wifi-presence-monitor
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

仮想環境名は `venv` でも `wifi_env` でも可（`start.ps1` は両方を探します）。

API キー（必須）:

```powershell
copy api_key.example.json api_key.json
# api_key.json の api_key を長いランダム文字列に書き換える
```

到着チャイム用 WAV（任意）:

- `sounds/arrive.wav` を置く
- 無い場合は Windows の `SystemAsterisk` を再生

cloudflared（公開する場合）の置き場所（優先順）:

1. 環境変数 `CLOUDFLARED_EXE`
2. `tools\cloudflared-windows-amd64.exe`
3. `%USERPROFILE%\Downloads\cloudflared-windows-amd64.exe`

---

## 起動と停止

起動:

```powershell
.\scripts\start.ps1
```

停止:

```powershell
.\scripts\stop.ps1
```

`start.ps1` は Quick Tunnel の URL を `data/tunnel_url.txt` に BOM なしで書き込み、在室ボードのヘッダーと API の `public_url` に反映します。Quick Tunnel の URL は**起動のたびに変わります**。

手動か分離起動の例:

```powershell
.\tools\cloudflared-windows-amd64.exe tunnel --url http://127.0.0.1:5000
# 表示された URL を data\tunnel_url.txt に1行で書けば画面・API にも出ます
```

### 主な URL

| URL | 内容 |
| --- | --- |
| `http://<PCのIP>:5000/` | リアルタイム在室ボード |
| `http://<PCのIP>:5000/history` | 過去の在室履歴 |
| `GET /health` | 生存確認（本文 `running`） |
| `GET /status` | 当日の状態 JSON（`public_url` 含む） |
| `GET /history/dates` | 過去日の一覧 |
| `GET /history/<YYYY-MM-DD>` | 指定日の在室 JSON |
| `POST /wifi_connected` | 在室開始（レスポンスに `public_url`） |
| `POST /wifi_disconnected` | 不在 |
| `POST /test_post` | 受信確認用（在室登録なし） |

`<PCのIP>` はサーバ PC の学内 LAN アドレスです（例: `192.168.1.10`）。

---

## API キー

すべての **POST** に API キーが必要です（GET の画面・`/status` などは不要）。

| 方法 | 例 |
| --- | --- |
| JSON 本文 | `"api_key": "あなたの秘密文字列"` |
| ヘッダ | `X-Api-Key: あなたの秘密文字列` |
| ヘッダ | `Authorization: Bearer あなたの秘密文字列` |

- 未設定のまま POST → `503`
- キー不一致・未送信 → `401`
- `api_key.json` は gitignore 対象です

---

## 接続通知 API

`POST /wifi_connected`  
`Content-Type: application/json`

```json
{
  "name": "山田太郎",
  "grade": "M2",
  "api_key": "あなたの秘密文字列"
}
```

| フィールド | 必須 | 説明 |
| --- | --- | --- |
| `name` | はい | 氏名 |
| `grade` | はい | `Teacher` / `M2` / `M1` / `B4` など。それ以外は `other` |
| `api_key` | はい※ | 共有キー（ヘッダでも可） |

当日レコードは **氏名 + 学年** で識別します。

### レスポンス例

```json
{"ok": true, "message": "受け付けました", "public_url": "https://xxxx.trycloudflare.com"}
```

`public_url` は `data/tunnel_url.txt` の値です（未起動・未設定時は `null`）。ショートカットではこの値をファイルに保存し、切断時のベース URL に使います。

```json
{"ok": false, "error": true, "message": "APIキーが無効です"}
```

```json
{"ok": false, "error": true, "message": "name と grade は必須です"}
```

```json
{"ok": false, "error": true, "message": "同時接続数の上限に達しています", "public_url": null}
```

---

## 切断通知 API

`POST /wifi_disconnected`  
`Content-Type: application/json`

本文は接続と同じ（`name` / `grade` / `api_key`）。

### レスポンス例

```json
{"ok": true, "message": "不在にしました"}
```

```json
{"ok": true, "ignored": true, "message": "当日の在室記録が見つかりません"}
```

```json
{"ok": true, "ignored": true, "message": "すでに不在です"}
```

---

## iPhone ショートカットの作り方

推奨構成は次のとおりです。

| タイミング | 宛先 | 理由 |
| --- | --- | --- |
| Wi‑Fi **接続時** | `http://<PCのIP>:5000/wifi_connected` | 学内 LAN 上で確実に届く。レスポンスの `public_url` を保存 |
| Wi‑Fi **切断時** | `https://<保存した公開URL>/wifi_disconnected` | 切断後は学内 IP に届かないため |

あらかじめ用意するもの:

- サーバ PC の学内 IP（例: `192.168.1.10`）
- `api_key.json` と同じ `api_key`
- 自分の `name` / `grade`
- `.\scripts\start.ps1` でサーバとトンネルが起動していること

ローカルは HTTP のため、「URLの内容を取得」で **安全でない読み込みを許可** をオンにしてください。

### 1. 接続ショートカット（名前例: 在室・接続）

1. 「ショートカット」アプリ → 新規ショートカット
2. **待機** → `5` 秒（Wi‑Fi 安定待ち）
3. **URL** → `http://<PCのIP>:5000/wifi_connected`
4. **URLの内容を取得**
   - 方法: **POST**
   - ヘッダ: 不要（キーは本文で送る）
   - **本文を要求**: JSON
   - キーと値:

| キー | テキスト |
| --- | --- |
| `name` | 自分の氏名 |
| `grade` | `Teacher` / `M2` / `M1` / `B4` など |
| `api_key` | `api_key.json` と同じ文字列 |

5. （「URLの内容を取得」の結果は辞書になる）**辞書の値を取得** → キー `public_url`
6. **もし** `public_url` が空でない なら:
   - **ファイルを保存**
   - 内容: `public_url` のテキスト
   - ファイル名例: `presence_public_url.txt`
   - 場所: iCloud Drive の「Shortcuts」フォルダなど（切断側と同じ場所）
   - **上書き** をオン
7. （任意）`public_url` が空なら **通知**「公開URLが取得できませんでした」

接続のたびにトンネル URL が更新されるので、切断用 URL も常に最新になります。  
（`GET /status` は不要です。接続レスポンスの `public_url` で足ります。）

### 2. 切断ショートカット（名前例: 在室・切断）

1. 新規ショートカット
2. **ファイルを取得** → 接続側で保存した `presence_public_url.txt`（同じ場所）
3. ファイルの内容をテキストとして使う（必要なら「テキスト」アクションで渡す）
4. **URL** →  
   `[ファイルのテキスト]/wifi_disconnected`  
   例: `https://xxxx.trycloudflare.com/wifi_disconnected`
5. **URLの内容を取得**
   - 方法: **POST**
   - **本文を要求**: JSON
   - `name` / `grade` / `api_key` は接続ショートカットと同じ

### 3. オートメーション

「ショートカット」アプリ → **オートメーション** → 個人用オートメーションを作成。

| トリガー | 実行するショートカット |
| --- | --- |
| Wi‑Fi → 対象ネットワークが **参加済み** | 在室・接続 |
| Wi‑Fi → 対象ネットワークから **切断** | 在室・切断 |

設定のポイント:

- ネットワークは研究室 SSID に限定する
- **すぐに実行**（確認ダイアログを出さない）
- ロック中は遅延・スキップされることがある
- 作成後は、研究室 Wi‑Fi で手動実行してボード上の在室／不在が変わるか確認する

### 4. 動作確認の手順例

1. PC で `.\scripts\start.ps1` → ボードに公開 URL が出ることを確認
2. iPhone を研究室 Wi‑Fi に接続した状態で「在室・接続」を手動実行
3. `http://<PCのIP>:5000/` で自分が在室になること、`presence_public_url.txt` が保存されることを確認
4. 「在室・切断」を手動実行 → 不在になること
5. 問題なければオートメーションを有効化

---

## 在室ボード（`/`）

表示順: **Teacher（灰）→ M2（薄青）→ M1（黄土）→ B4（薄緑）→ other（薄赤）**

| 列 | 内容 |
| --- | --- |
| 状態 | 在室 / 不在 |
| 氏名 | `name` |
| 到着 | 当日最初の接続時刻 |
| 帰宅 | 切断通知の時刻（再接続で `-` に戻る） |
| 総在室 | 当日の在室時間（接続中に加算、切断時に確定） |

- 不在になっても当日の行は残る
- 日付が変わると当日ボードはリセット（過去ファイルは残る）
- ヘッダーの「公開URL」は `data/tunnel_url.txt` 由来（`GET /status` の `public_url` と同じ）

## 在室履歴（`/history`）

`data/presence/` に保存された**過去日**の記録を表示します（当日は含めません）。

---

## タスクスケジューラ（PC 起動時の自動開始）

`start.ps1` は完了後に終了し、Flask / cloudflared は裏で常駐します。

### 事前準備

1. `venv` または `wifi_env` を作成し `pip install -r requirements.txt` 済み
2. `api_key.json` を設定済み
3. cloudflared を `tools\` などに配置
4. 手動で一度確認:

```powershell
cd path\to\wifi-presence-monitor
.\scripts\start.ps1
# http://127.0.0.1:5000/ に公開URLが出ることを確認
.\scripts\stop.ps1
```

### かんたん登録（推奨）

```powershell
cd path\to\wifi-presence-monitor
.\scripts\register-task.ps1
```

- タスク名: `WiFi Presence Monitor`
- トリガー: ログオン時 + 60 秒遅延（ネットワーク待ち）
- 削除: `.\scripts\register-task.ps1 -Unregister`

登録後の手動実行:

```powershell
Start-ScheduledTask -TaskName "WiFi Presence Monitor"
```

### GUI で作る場合

1. 「タスク スケジューラ」→「タスクの作成」（基本タスクではない）
2. **全般**
   - 名前: `WiFi Presence Monitor`
   - 「ユーザーがログオンしているときのみ実行」
   - 「最上位の特権で実行する」は通常オフ
3. **トリガー**
   - 「ログオン時」＋ **1 分程度の遅延**（ネット未接続だとトンネル取得に失敗しやすい）
4. **操作**
   - プログラム: `powershell.exe`
   - 引数:  
     `-NoProfile -ExecutionPolicy Bypass -File "C:\Users\<あなた>\MyTools\wifi-presence-monitor\scripts\start.ps1"`
5. **設定**
   - 「タスクを停止するまでの時間」を**オフ**（または十分長く）
   - 「要求時に実行中のタスクを停止する」はそのままで可（`start.ps1` 自体は数分で終わる）

### 確認・失敗時

| 確認 | 場所 |
| --- | --- |
| タスクの最終実行結果 | タスクスケジューラの履歴 / 前回の実行結果 |
| 起動スクリプト全体 | `data\start.log` |
| 起動失敗メッセージ | `data\start.err.log` |
| Flask | `data\app.err.log` |
| cloudflared | `data\cloudflared.err.log` |

停止: `.\scripts\stop.ps1`

固定の公開 URL が必要なら Cloudflare の名前付きトンネルを検討してください（このリポジトリの `start.ps1` は Quick Tunnel 向けです）。

---

## 主な設定（`app/config.py`）

| 定数 | 意味 |
| --- | --- |
| `CHECK_INTERVAL_SECONDS` | 在室時間の画面反映・加算ループ間隔（秒） |
| `MAX_TARGETS` | 同時在室のソフト上限（既定 20） |
| `ARRIVAL_SOUND_ENABLED` | 到着チャイムの ON/OFF |
| `ARRIVAL_SOUND_FILE` | チャイム WAV パス |
| `TUNNEL_URL_FILE` | 公開 URL ファイル（既定 `data/tunnel_url.txt`） |

---

## データ保存

```text
data/
  presence/
    2026-07-30.json
    2026-07-31.json
  tunnel_url.txt          # Quick Tunnel の公開 URL（gitignore）
  runtime/                # app / cloudflared の PID
  start.log / start.err.log  # start.ps1（タスクスケジューラ向け）
  app.*.log / cloudflared.*.log
```

---

## 注意事項

- 不在は **切断 POST が届いたとき** に確定します（届かないと在室のまま）
- 切断通知は公開 URL 経由を想定しています（接続は学内 IP 推奨）
- Quick Tunnel の URL は起動ごとに変わるため、接続ショートカットで毎回 `public_url` を保存してください
- Flask 開発サーバ想定です

---

## トラブルシュート

| 症状 | 確認すること |
| --- | --- |
| 接続 POST が届かない | サーバ起動・学内 IP・ポート 5000・同一 Wi‑Fi・ショートカットの URL / JSON |
| 切断 POST が届かない | `presence_public_url.txt` の有無・内容・`/wifi_disconnected` の結合・トンネル稼働 |
| `public_url` が `null` | `.\scripts\start.ps1` 実行・`data\tunnel_url.txt`・cloudflared ログ |
| ボードに公開URLが出ない | 同上。ファイル先頭の BOM 問題は現行コードで吸収済み |
| 切断しても在室のまま | 切断オートメーション・保存 URL・API キー |
| 401 / 503 | `api_key.json` の有無とショートカットの `api_key` 一致 |
| 音が鳴らない | `ARRIVAL_SOUND_ENABLED`、PC の音量、`sounds/arrive.wav` |
| タスクスケジューラで起動しない | `data\start.err.log` を見る。多い原因: `venv`/`wifi_env` 未作成、cloudflared 未配置、ログオン直後でネット未接続（遅延を付ける）、引数のパス誤り |
