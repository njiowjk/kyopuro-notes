---
task_id: abc465_c
problem_url: https://atcoder.jp/contests/abc465/tasks/abc465_c
submission_urls: []
representative_submission_url:
status: organized
---

# C - Reverse Permutation

## 問題概要

`N` と `o`・`x` からなる長さ `N` の文字列 `S` を読む。初期列 `1,2,...,N` に対し、`k=1..N` の順に `S_k` が `o` なら先頭 `k` 項を反転する。最終列を空白区切りで出力する。`2 <= N <= 5×10^5`。

## 解法の概要

操作 `k` の前に、先頭 `k-1` 項だけを deque で保持する。過去の操作の範囲外だった `k` は、現在の列の末尾にそのまま追加できる。`o` の場合は追加後に向きフラグを反転する。フラグが真なら deque を末尾から読むと現在の列になるので、論理上の末尾への追加は物理的な先頭への追加に切り替える。この対応は反転後も保たれる。時間 O(N)、追加メモリ O(N)。

主分類は [配列](../../分野/配列/配列.md)。

## 使用した解法ノート

<!-- BEGIN AUTO: related-solutions -->

- [列の反転と端への追加を deque と向きフラグで処理する](../../分野/配列/列の反転と端への追加を%20deque%20と向きフラグで処理する.md)

<!-- END AUTO: related-solutions -->

### 関連する既存ノート

- [STL / deque（両端への追加）](../../STL/queue-stack-deque-heap.md)

## 問題固有の実装ポイント

- 毎回 `k` を加えてから `S_k` に従って反転する。操作 `k=1` の反転は見かけ上変化がなくても、フラグの規則を適用できる。
- 最後のフラグに従って、先頭からまたは末尾から順に出力する。

## 自作コード

Inbox で照合した Python の実装を確認した。提出との対応とジャッジ結果は未確認。

空の `deque` と `rev=False` で開始する。`rev` に応じて `i+1` を `append` または `appendleft` し、`o` なら `rev` を反転する。出力時だけ必要に応じて `reversed` を使う。

公式3サンプルと、全て `x`、先頭または末尾だけ `o`、交互に反転する場合、短い列での接頭辞の直接反転を照合した。

## 公式解法・参考資料

- 入出力、制約、サンプルを確認した。[AtCoder 公式問題文](https://atcoder.jp/contests/abc465/tasks/abc465_c)
- 反転回数の偶奇で挿入する端を選び、最後に向きをそろえる方法を参照した。[AtCoder 公式解説](https://atcoder.jp/contests/abc465/editorial/22559)
