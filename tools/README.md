# AtCoderの問題をInboxに登録する

Python 3.11以降を使います。ローカルソースの照合には、`atc source` を備えたatc-rsがPATH上に必要です。

```sh
python3 tools/note.py add 'https://atcoder.jp/contests/abc484/tasks/abc484_a'
python3 tools/note.py resolve
python3 tools/note.py list
```

`add` にはAtCoderの問題URLを指定します。登録時はPython内でURLを検証し、問題と登録日時を記録します。解決後は `list` またはVaultルートの `Inbox.md` で取得状態を確認できます。一覧の再生成は `python3 tools/note.py rebuild` です。

引数なしで `resolve` を使うには、Vaultルートの `.local/config.toml` にWorkspaceを設定します。実行ごとに `--workspace` で指定することもできます。[Workspaceの設定方法](resolve.md#workspaceを設定する)

原本、スナップショット、生成した一覧はGitの除外対象です。[照合と再実行](resolve.md)・[Inbox仕様](../管理/Inbox仕様.md)

テストは `python3 -B -m unittest discover -s tools` で実行できます。
