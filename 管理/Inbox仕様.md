# ローカル Inbox

問題URLの登録原本はVaultの `.local/inbox.jsonl`、照合したローカルソースは `.local/sources/` に保存する。Vaultルートの `Inbox.md` は原本から再生成できる状態一覧とする。いずれもGit管理から除外する。[CLIの使い方](../tools/README.md)

## JSONLの記録

UTF-8で、正規化済み問題URLにつき1行とする。末尾のスラッシュ、クエリ、フラグメントを除いたURLで重複を判定し、最初の登録日時を保持する。

| 項目 | 内容 |
|---|---|
| `schema_version` | 整数の `1` |
| `kind` | 新規登録は `problem` |
| `url` | 正規化済みのAtCoder問題URL |
| `contest_id`、`task_id` | 問題URLの各識別子 |
| `submission_id` | 問題URLでは `null` |
| `registered_at` | タイムゾーン付きISO 8601形式 |
| `status` | 以下の整理状態 |
| `local_source` | 取得時の `origin: atc-rs-local`、`index`、`language`、`sha256` |
| `resolution_error` | 取得待ちや保留の理由を示す固定コード |

| 状態 | 意味 |
|---|---|
| `pending` | まだ取得できていない、または改版の確認待ち |
| `resolved` | 問題メタデータとローカルソースの照合が完了 |
| `organized` | 問題ノートと解法ノートの整理が完了 |
| `blocked` | 問題識別子または保存データの整合性に矛盾があり要確認 |

同じtask IDに異なる問題URLがある場合は両方を保持し、照合を保留する。旧Inboxの提出URLは行・日時を保持し、一覧の別欄に表示する。旧方式で `resolved` になった問題も、ローカルソースの記録がなければ取得待ちとして扱う。変更対象外のJSONL行はそのまま保存される。

## 保存と再実行

ソースは `.local/sources/<sha256>.cpp` または `.local/sources/<sha256>.py` にUTF-8バイト列として保存する。JSONLにはatc-rsが返す絶対パスやソース本文を記録しない。元ファイルのパスやコードはMarkdownに転記しない。

同じSHA-256のファイルは、内容を確認して再利用する。新旧でソースが異なる場合は、確認を受けたあとで新しいスナップショットを採用し、前のファイルを保持する。ソースを安全に保存した後で原本を一時ファイル経由で置き換える。原本の保存だけ失敗した場合、再実行時に保存済みのソースを検証して復旧できる。[照合と再実行](../tools/resolve.md)
