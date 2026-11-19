---
task_id: abc342_c
problem_url: https://atcoder.jp/contests/abc342/tasks/abc342_c
submission_urls: []
representative_submission_url:
status: organized
---

# C - Many Replacement

## 問題概要

`N`、英小文字列 `S`、`Q`、続けて `Q` 組の英小文字 `c d` を読む。操作ごとに現時点の `c` をすべて `d` に換え、最後の文字列を出力する。`1 <= N,Q <= 2×10^5`。

## 解法の概要

変換表の各要素を元の文字で添字付けし、そこに現在の文字を保存する。初期値は元の文字自身。各操作は変換表の値で `c` になっている箇所をすべて `d` にすればよい。元の文字が同じ位置はどの操作でも同じように変わるため、表には各元文字の最新の結果が保たれる。最後に `S` の各文字へ表を1度適用する。文字種数を `Σ=26` として時間 O(N+ΣQ)、変換表は O(Σ)。Python では出力文字列を別に作るので追加で O(N)。

主分類は [文字列](../../分野/文字列/文字列.md)。

## 使用した解法ノート

<!-- BEGIN AUTO: related-solutions -->

- [文字種ごとの対応表で一括置換を合成する](../../分野/文字列/文字種ごとの対応表で一括置換を合成する.md)

<!-- END AUTO: related-solutions -->

### 関連する既存ノート

- [STL / string（文字列と文字を走査）](../../STL/string.md)
- [STL / vector・array（小さな固定長の全走査）](../../STL/vector-array.md)
## 問題固有の実装ポイント

- たとえば `a→b` の後で `b→c` が来れば、元の `a` も元の `b` も `c` になる。更新するのは変換表のうち現在値が `b` の全箇所。
- `c==d` や現在の文字列に `c` が存在しない場合も同じ処理でよい。元の文字列に登場しない文字の表も用意しておける。

## 自作コード

Inbox で照合したローカルソースを解析した。提出との対応とジャッジ結果は未確認。

Python の `dic` を英小文字の列で初期化し、各操作を `dic.replace` で処理する。全操作後に `str.maketrans` で元の英小文字と `dic` を対応づけ、`translate` で `S` に適用する。

全3サンプルと、短い文字列に置換を直接適用する実装との照合を行い、置換の連鎖・合流、同じ文字への置換を確認した。

## 公式解法・参考資料

- 入出力・制約・サンプルを確認した。[AtCoder 公式問題文](https://atcoder.jp/contests/abc342/tasks/abc342_c)
- 元の文字種ごとに置換結果を管理する考え方を確認した。[AtCoder 公式解説](https://atcoder.jp/contests/abc342/editorial/9450)
