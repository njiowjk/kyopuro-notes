# AtCoder Inbox にURLを登録する

macOS・Linux の Python 3.11 以降で動作します。以下はVaultのルートから実行する例です。

```sh
python3 tools/note.py add 'https://atcoder.jp/contests/example/submissions/900000001'
python3 tools/note.py add 'https://atcoder.jp/contests/example/tasks/another_task_a'
python3 tools/note.py list
python3 tools/note.py rebuild
```

例の代わりに自分の提出URLか問題URLを1つ貼ってください。登録後、ObsidianでVaultルートの `Inbox.md` を開くと一覧が見られます。提出URLの task ID は「未解決」と表示されます。登録と再生成はローカルで完結します。

`.local/inbox.jsonl` が原本です。一覧を消した場合や更新に失敗した場合は、エラーの原因を解消し、`rebuild` で戻せます。どちらもGitの除外対象です。詳しくは [Inbox仕様](../管理/Inbox仕様.md) を参照してください。

テストは `python3 -B -m unittest discover -s tools` で実行できます。
