# ローカル Inbox

未整理のAtCoder提出URL・問題URLはVaultルートの `.local/inbox.jsonl` に保存する。ルートの `Inbox.md` はObsidianで見る未処理一覧とし、JSONLから再生成できる表示用ファイルとする。両方ともGit管理から除外する。

## 保存形式

`.local/inbox.jsonl` はUTF-8で、1行に1件のJSONオブジェクトを持つ。未処理のURLの原本はこのファイルとする。

| 項目 | 内容 |
|---|---|
| `kind` | `submission` または `problem` |
| `url` | 正規化済みのAtCoder URL |
| `registered_at` | 登録日時。タイムゾーンを含むISO 8601形式 |

以下の `<...>` は置換用の例示。

```jsonl
{"kind":"submission","url":"https://atcoder.jp/contests/<contest-id>/submissions/<submission-id>","registered_at":"2026-11-19T12:00:00+09:00"}
{"kind":"problem","url":"https://atcoder.jp/contests/<contest-id>/tasks/<task-id>","registered_at":"2026-11-19T12:05:00+09:00"}
```

## 登録と整理

1. 登録は貼り付けを受け付け、`atcoder.jp` のHTTPS URLであることを確認する。ユーザー情報や非標準ポートを含むURLは対象外とする。パスは上記のいずれかとし、提出IDは数字とする。パスから `kind` を決め、末尾のスラッシュ、クエリ、フラグメントを除いたURLで重複を判定する。登録処理はローカルの保存と一覧更新までとし、AtCoderへのアクセスや生成AIによる解析は行わない。
2. 別操作で整理するときに提出URLから task ID を解決する。問題URLと複数の提出URLが同じタスクを指す場合は、1件の問題ノートにまとめる。公開してよい情報を判断したうえで、[分類ルール](分類ルール.md) に従って問題ノートと双方向リンクを更新する。
3. 問題ノートへの反映と必要な双方のリンクを確認した項目を未処理一覧から外す。取得できない項目、対応を判断できない項目、承認待ちで反映していない項目はキューに残す。

このPhaseでは保存場所とデータ形式を定義する。登録ツール、一覧ファイル、登録データ、解析処理は次のPhase以降に用意する。
