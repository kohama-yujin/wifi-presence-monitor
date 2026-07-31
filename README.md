# Wi‑Fi Presence Monitor（在室管理）

iPhone ショートカットなどから接続／切断通知を受け取り、在室状況を Web で表示するツールです。

- `POST /wifi_connected` で在室開始
- `POST /wifi_disconnected` で不在
- `/` で学年別の在室ボードをリアルタイム表示
- `/history` で過去日の在室履歴を表示（日付切替）
- 到着時にサーバでチャイム再生
- 在室記録は日付ごとに `data/presence/` へ保存
- Cloudflare Quick Tunnel などで学外公開も可能

## 必要な環境

- Windows
- Python 3.10+

## セットアップ

```powershell
cd path\to\wifi-presence-monitor
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

API キー（必須・共有パスワード）:

```powershell
copy api_key.example.json api_key.json
# api_key.json の api_key を長いランダム文字列に書き換える
```

到着チャイム用 WAV（任意）:

- `sounds/arrive.wav` を置く  
- 無い場合は Windows の `SystemAsterisk` を再生  

## 起動

```powershell
cd path\to\wifi-presence-monitor
.\venv\Scripts\Activate.ps1
python main.py
```

学外公開の例（Quick Tunnel）:

```powershell
.\cloudflared-windows-amd64.exe tunnel --url http://127.0.0.1:5000
```

| URL | 内容 |
| --- | --- |
| `http://<PCのIP>:5000/` | リアルタイム在室管理画面 |
| `http://<PCのIP>:5000/history` | 過去の在室履歴（日付切替。当日は対象外） |
| `http://<PCのIP>:5000/health` | 生存確認（`running`） |
| `http://<PCのIP>:5000/status` | 当日の状態 JSON |
| `http://<PCのIP>:5000/history/dates` | 過去日の一覧 JSON |
| `http://<PCのIP>:5000/history/<YYYY-MM-DD>` | 指定日の在室 JSON |
| `POST /wifi_connected` | 在室開始 |
| `POST /wifi_disconnected` | 不在 |
| `POST /test_post` | 受信確認用（在室登録なし） |

## API キー（共有パスワード）

すべての **POST** に API キーが必要です（GET の画面・`/status` などは不要）。

渡し方（どれか1つ）:

| 方法 | 例 |
| --- | --- |
| JSON 本文 | `"api_key": "あなたの秘密文字列"` |
| ヘッダ | `X-Api-Key: あなたの秘密文字列` |
| ヘッダ | `Authorization: Bearer あなたの秘密文字列` |

設定:

```powershell
copy api_key.example.json api_key.json
# api_key.json の値を長いランダム文字列に変更
```

未設定のまま POST すると `503`、キー不一致・未送信は `401` です。`api_key.json` は gitignore 対象です。

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
{"ok": true, "message": "受け付けました"}
```

```json
{"ok": false, "error": true, "message": "APIキーが無効です"}
```

```json
{"ok": false, "error": true, "message": "name と grade は必須です"}
```

```json
{"ok": false, "error": true, "message": "同時接続数の上限に達しています"}
```

## 切断通知 API

`POST /wifi_disconnected`  
`Content-Type: application/json`

```json
{
  "name": "山田太郎",
  "grade": "M2",
  "api_key": "あなたの秘密文字列"
}
```

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

## iPhone からの自動通知（ショートカット + オートメーション）

研究室 Wi‑Fi の接続／切断で POST する設定例です。  
サーバ URL は学内 IP または Quick Tunnel の HTTPS URL に置き換えてください。

### 1. 接続ショートカット

1. 「ショートカット」で新規作成  
2. 「待機」5秒 → 「URLの内容を取得」  
3. URL: `https://<公開URL>/wifi_connected`（または `http://<PCのIP>:5000/wifi_connected`）  
4. 方法: POST / 本文を要求: JSON  

| キー | テキスト |
| --- | --- |
| `name` | 自分の氏名 |
| `grade` | 学年（`Teacher` / `M2` / `M1` / `B4` など） |
| `api_key` | `api_key.json` と同じ共有キー |

5. 名前を付ける（例: 在室・接続）

### 2. 切断ショートカット

接続と同様に作り、URL だけ次にする:

`https://<公開URL>/wifi_disconnected`

本文の `name` / `grade` は接続と同じ。

### 3. オートメーション

| トリガー | 実行するショートカット |
| --- | --- |
| Wi‑Fi「対象ネットワーク」**参加済み** | 接続ショートカット |
| Wi‑Fi「対象ネットワーク」**切断** | 切断ショートカット |

- ネットワークは研究室 Wi‑Fi に限定する  
- 「すぐに実行」を選ぶ  
- ロック中はオートメーションが遅延・スキップされることがある  

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

## 在室履歴（`/history`）

`data/presence/` に保存された**過去日**の記録を表示します（当日は含めません）。

## 主な設定（`app/config.py`）

| 定数 | 意味 |
| --- | --- |
| `CHECK_INTERVAL_SECONDS` | 在室時間の画面反映・加算ループ間隔（秒） |
| `MAX_TARGETS` | 同時在室のソフト上限 |
| `ARRIVAL_SOUND_ENABLED` | 到着チャイムの ON/OFF |
| `ARRIVAL_SOUND_FILE` | チャイム WAV パス |

## データ保存

```text
data/presence/
  2026-07-30.json
  2026-07-31.json
  ...
```

## 注意事項

- 不在は **切断 POST が届いたとき** に確定します（届かないと在室のまま）  
- トンネル経由でも接続／切断 POST は動作します（ARP 不要）  
- ソフト上限は `MAX_TARGETS`（既定 20）  
- Flask 開発サーバ想定です  

## トラブルシュート

| 症状 | 確認すること |
| --- | --- |
| POST が届かない | サーバ起動・トンネル URL・ショートカットの URL |
| 切断しても在室のまま | 切断オートメーション・`/wifi_disconnected` の URL |
| 音が鳴らない | `ARRIVAL_SOUND_ENABLED`、PC の音量、`sounds/arrive.wav` |
