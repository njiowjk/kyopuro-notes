# ローカル Inbox

AtCoderの提出URL・問題URLはVaultルートの `.local/inbox.jsonl` に保存する。ルートの `Inbox.md` はObsidianで見る未処理一覧とし、JSONLから再生成できる表示用ファイルとする。両方ともGit管理から除外する。登録・一覧表示・再生成のコマンドは [CLIの使い方](../tools/README.md) を参照する。

## 保存形式

`.local/inbox.jsonl` はUTF-8で、正規化済みURLごとに1行のJSONオブジェクトを持つ。

| 項目 | 内容 |
|---|---|
| `schema_version` | 整数の `1` |
| `kind` | `submission` または `problem` |
| `url` | 正規化済みのAtCoder URL。整理後も原本に保持する |
| `contest_id` | URLのコンテストID |
| `submission_id` | 提出IDの文字列。問題URLでは `null` |
| `task_id` | 問題URLから取得したtask ID。提出URLの登録時は `null` |
| `registered_at` | タイムゾーン付きISO 8601形式の登録日時。新規登録ではUTC |
| `status` | 登録時は `pending`（未整理）。後続の整理で `organized`（整理済み）にできる |

架空のURLを使った保存例。

```jsonl
{"schema_version":1,"kind":"submission","url":"https://atcoder.jp/contests/example/submissions/900000001","contest_id":"example","submission_id":"900000001","task_id":null,"registered_at":"2026-11-19T03:00:00+00:00","status":"pending"}
{"schema_version":1,"kind":"problem","url":"https://atcoder.jp/contests/example/tasks/another_task_a","contest_id":"example","submission_id":null,"task_id":"another_task_a","registered_at":"2026-11-19T03:05:00+00:00","status":"pending"}
```

## 登録と整理

1. `atcoder.jp` のHTTPS URLから、`/contests/{contest}/submissions/{submission_id}` または `/contests/{contest}/tasks/{task_id}` を受け付ける。提出IDは数字とし、ユーザー情報や非標準ポートを含むURLは拒否する。末尾のスラッシュ、クエリ、フラグメントを除いたURLで重複を判定し、元の登録日時を保つ。別々の提出URLは個別に保持する。登録はローカルの保存と一覧更新までとする。
2. 後続の整理処理で、提出URLから実際の task ID を解決する。同じタスクを指すURLは1件の問題ノートにまとめる。公開してよい情報を判断したうえで、[分類ルール](分類ルール.md) に従って問題ノートと双方向リンクを更新する。
3. 問題ノートへの反映と両方向のリンクを確認した項目は、原本で `status` を `organized` にする。未処理一覧には `pending` の項目を表示する。取得できない項目や承認待ちの項目は `pending` のままにする。

Phase 1の `kind`・`url`・`registered_at` の3項目だけを持つ行も読み取れる。新規URLを追加するときに、そのような既存行もバージョン1に揃える。未対応のバージョンや不正な行を検出した場合は、行番号を表示して更新を中止する。

登録と再生成は同時に書き込まないよう調整し、原本と一覧はそれぞれ完成した一時ファイルから置き換える。原本を保存したあとに一覧の更新が失敗した場合、登録済みのURLは原本に残る。`rebuild` または同じURLの再登録で一覧を復旧できる。
