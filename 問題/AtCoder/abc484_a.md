---
task_id: "abc484_a"
problem_url: "https://atcoder.jp/contests/abc484/tasks/abc484_a"
submission_urls: []
representative_submission_url: null
status: organized
---

# A - Chocolate Bar Count

## 問題概要

30 行 30 列の板チョコから、下端の行を 1 行ずつ B 回取り除き、その後に右端の列を 1 列ずつ R 回取り除く。1 マスが 1 片に対応し、残ったチョコレートの個数を求める。B、R はどちらも 1 以上 29 以下の整数。

## 解法の概要

行を取り除く操作は行数だけを減らし、列を取り除く操作は列数だけを減らす。操作後も長方形なので、残る行数 `30 - B` と列数 `30 - R` の積が答えになる。時間計算量・追加メモリはともに O(1)。

主分類は [グリッド](../../分野/グリッド/グリッド.md)。

## 使用した解法ノート

<!-- BEGIN AUTO: related-solutions -->

<!-- END AUTO: related-solutions -->

## 問題固有の実装ポイント

- 入力順は `B R` で、下から取り除く行数、右から取り除く列数の順。
- 残る行数と列数はそれぞれ 1 以上 29 以下。答えは 1 以上 841 以下なので、`int` で扱える。

## 自作コード

Inbox で問題 A に照合された C++ のローカルスナップショット（取得元 `atc-rs-local`）を参照した。保存済みの実装は `int` の `b` と `r` を読み込み、`(30 - b) * (30 - r)` を改行付きで出力する。提出との対応やジャッジ結果は未確認。

## 公式解法・参考資料

- 板チョコの初期サイズ、取り除く順序、入力の範囲を確認した。[AtCoder 公式問題文](https://atcoder.jp/contests/abc484/tasks/abc484_a)
- 操作後の行数と列数の積で残りの個数を求める考え方を確認した。[AtCoder 公式解説](https://atcoder.jp/contests/abc484/editorial/29003)
