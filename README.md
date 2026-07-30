# Wi‑Fi Presence Monitor（在室管理）

研究室 LAN 上の端末から接続通知を受け取り、ARP で在席を監視し、在室状況を Web で表示するツールです。

- iPhone ショートカットなどから `POST /wifi_connected`
- サーバが対象 IP へ ARP Request（Npcap + Scapy）
- `/client` で学年別の在室ボードを表示
- 到着時にサーバでチャイム再生
- 在室記録は日付ごとに `data/presence/` へ保存

## 必要な環境

- Windows（管理者権限で起動）
- Python 3.10+
- [Npcap](https://npcap.com/)（L2 ARP 送受信に必須）

## Npcap の導入

Scapy の ARP（`Ether` + `srp`）には Npcap が必要です。未導入だと次のエラーになります。

```text
RuntimeError: Sniffing and sending packets is not available at layer 2:
winpcap is not installed.
```

### 手順

1. [Npcap ダウンロード](https://npcap.com/#download) からインストーラを入手する  
2. **管理者として実行**する  
3. インストール時に次を有効にする  
   - **Install Npcap in WinPcap API-compatible Mode**（Scapy 用に必須）  
4. インストール後、**ターミナル / Cursor をいったん閉じて開き直す**  
5. 本アプリは **管理者権限の PowerShell** で起動する  

補足:

- WinPcap が残っている場合はアンインストールし、Npcap のみにする  
- 学校・共用 PC ではポリシーでインストールできないことがあります  

## セットアップ

```powershell
cd path\to\wifi-presence-monitor
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

除外 MAC リスト（任意）:

```powershell
copy excluded_macs.example.json excluded_macs.json
# excluded_macs.json を編集
```

到着チャイム用 WAV（任意）:

- `sounds/arrive.wav` を置く  
- 無い場合は Windows の `SystemAsterisk` を再生  

## 起動

**管理者権限**の PowerShell で:

```powershell
cd path\to\wifi-presence-monitor
.\venv\Scripts\Activate.ps1
python main.py
```

| URL | 内容 |
| --- | --- |
| `http://<PCのIP>:5000/` | 生存確認（`running`） |
| `http://<PCのIP>:5000/client` | 在室管理画面 |
| `http://<PCのIP>:5000/status` | 状態 JSON |

## 接続通知 API

`POST /wifi_connected`  
`Content-Type: application/json`

```json
{
  "name": "山田太郎",
  "grade": "M2"
}
```

| フィールド | 必須 | 説明 |
| --- | --- | --- |
| `name` | はい | 氏名 |
| `grade` | はい | `Teacher` / `M2` / `M1` / `B4` など。それ以外は `other` |

MAC は POST では受け取りません。接続元 IP に対する ARP で取得し、除外判定にも使います。

### レスポンス例

```json
{"ok": true, "message": "受け付けました"}
```

```json
{"ok": true, "ignored": true, "message": "C3-503のルーターに接続してください"}
```

```json
{"ok": true, "message": "確認中です"}
```

```json
{"ok": false, "error": true, "message": "name と grade は必須です"}
```

IP は `request.remote_addr`（通知元）を使います。サーバと**同じ LAN** である必要があります（別ルータ配下では ARP 監視できません）。

## 在室ボード（`/client`）

表示順: **Teacher（灰）→ M2（薄青）→ M1（黄土）→ B4（薄緑）→ other（薄赤）**

各行:

| 列 | 内容 |
| --- | --- |
| 状態 | 在室 / 不在 |
| 氏名 | `name` |
| 到着 | 当日最初の接続時刻 |
| 帰宅 | 不在になった時刻（デフォルト `-`、再到着で `-` に戻る） |
| 総在室 | 当日の在室時間（5分単位で加算。1時間以上は `〇時間〇分`） |

- 不在になっても当日の行は残る  
- 日付が変わると当日ボードはリセット（過去ファイルは残る）  
- 画面の更新間隔はサーバの `CHECK_INTERVAL_SECONDS` に追従  

## 主な設定（`app/config.py`）

| 定数 | 意味 |
| --- | --- |
| `CHECK_INTERVAL_SECONDS` | ARP 監視・画面更新の間隔（秒） |
| `PRESENCE_CREDIT_SECONDS` | 総在室時間の加算単位（秒） |
| `MISS_THRESHOLD_COUNT` | 連続ミスで不在とみなす回数 |
| `MAX_TARGETS` | 同時監視のソフト上限 |
| `ROUTER_NAME` | 除外 MAC 時の案内文に使う名前 |
| `ARRIVAL_SOUND_ENABLED` | 到着チャイムの ON/OFF |
| `ARRIVAL_SOUND_FILE` | チャイム WAV パス |

## 除外 MAC（`excluded_macs.json`）

研究室ルーター以外からの接続を無視したい端末の MAC を列挙します。

```json
[
  "aa:bb:cc:dd:ee:ff"
]
```

- 除外時は表に載せず、ルーター接続を案内するメッセージを返す  
- すでに正しい接続で当日登録済みの行は消さない  

## データ保存

```text
data/presence/
  2026-07-30.json
  2026-07-31.json
  ...
```

日付ごとに蓄積されます。アプリ再起動後も当日分を読み込みます。

## ディレクトリ構成

```text
wifi-presence-monitor/
  main.py                 # 起動入口
  requirements.txt
  excluded_macs.json      # ローカル設定（gitignore）
  app/
    config.py
    arp.py
    monitor.py
    sound.py
    routes/
      api.py
      client.py
  client/                 # /client の静的ファイル
  data/presence/          # 日付別の在室記録
  sounds/                 # arrive.wav（任意）
```

## 注意事項

- ARP 送信には **Npcap** と **管理者権限** が必要です  
- 対象は同一 L2/同一 LAN の端末のみです  
- 同時監視の目安は環境によりますが、ソフト上限は `MAX_TARGETS`（既定 20）です  
- Flask 開発サーバ想定です。本番常駐が必要なら別途サービス化してください  

## トラブルシュート

| 症状 | 確認すること |
| --- | --- |
| layer 2 / winpcap エラー | Npcap 導入・WinPcap 互換・端末再起動 |
| ARP が常に失敗 | 管理者で起動しているか、同一 LAN か |
| 除外なのに「受け付けました」 | 接続時 ARP で MAC が取れていない可能性。Npcap・管理者起動・同一 LAN を確認 |
| 音が鳴らない | `ARRIVAL_SOUND_ENABLED`、PC の音量、`sounds/arrive.wav` |
