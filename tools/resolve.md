# atc-rsのローカルソースを照合する

`resolve` は登録済みの問題について `atc source <contest> --task-id <task_id> --workspace <root> --json` を実行し、問題識別子・URLとソースを照合します。Workspaceとatc-rsのファイルは読み取り専用で扱います。

## Workspaceを設定する

Vaultルートに `.local/config.toml` を手動で作成し、マシンで使用するWorkspaceを指定してください。このファイルはGitの除外対象です。

```toml
[atc]
workspace = "~/atcoder-submittion"
```

`~` はホームディレクトリに展開されます。展開後のパスが実在するディレクトリの絶対パスになるように指定してください。Windowsでは `workspace = "C:/Users/your-name/atcoder-submittion"` のように指定できます。

`--workspace` を指定した回はその値が優先されます。`--workspace` と `atc.workspace` の両方が未設定の場合はエラーになります。

```sh
python3 tools/note.py resolve
python3 tools/note.py resolve --workspace ~/another-workspace
```

両言語のファイルがある問題は取得待ちになります。`--language cpp` または `--language python` で、今回の取得に使う言語を指定してください。取得結果は照合時点のローカルコードです。提出やACの状態はこの記録から判断できません。

## 取得結果を更新する

同じ内容を再取得すると、同じスナップショットを使います。コードや言語が変わった場合は、以前の取得記録を保持して取得待ちにします。Workspace側の変更を確認し、新しい版として採用する場合に `--accept-source-change` を付けて実行してください。以前のスナップショットは保存されます。

```sh
python3 tools/note.py resolve --workspace ~/atcoder-submittion --language cpp --accept-source-change
```

照合中にatc-rsやソースが見つからない場合、タイムアウトやJSON形式の不一致があった場合は、原因を表示して対象の問題を取得待ちにします。`--workspace` で指定したディレクトリが存在しない場合も同じ扱いです。問題IDやURLの矛盾、ソースの対応やスナップショットの整合性に矛盾がある場合は保留になります。取得待ち・保留があった回は終了コード1を返し、その回に照合できた他の結果は保存します。

保存後に一覧の更新が失敗した場合は `rebuild` で復旧できます。[データ形式と以前のInboxの扱い](../管理/Inbox仕様.md)
