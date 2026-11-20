# 列の反転と端への追加を deque と向きフラグで処理する

## やりたいこと

列全体の反転と、論理上の先頭・末尾への追加を繰り返す。例では `1..N` を順に末尾へ追加し、入力の `o` の位置で追加直後の列全体を反転する。

## 基本的な考え方

deque と向きを示す `reversed` を持つ。向きが通常なら deque を先頭から、逆なら末尾から読んだ順が現在の列。全体の反転は向きのフラグ1つで表す。

## 実装（C++）

`abc465_c` の形式で `N` と `o`・`x` の文字列を読む。照合済みの実装と同じ向きの管理を使い、出力時は C++ の deque に対する添字で読み出し方向を切り替える。

```cpp
#include <deque>
#include <iostream>
#include <string>
using namespace std;

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n;
    string operations;
    cin >> n >> operations;

    deque<int> values;
    bool reversed = false;
    for (int i = 0; i < n; ++i) {
        if (reversed) values.push_front(i + 1);
        else values.push_back(i + 1);
        if (operations[i] == 'o') reversed = !reversed;
    }

    for (int i = 0; i < n; ++i) {
        cout << values[reversed ? n - 1 - i : i]
             << (i + 1 == n ? '\n' : ' ');
    }
}
```

## 実装の要点

- 空の deque と通常の向きで始める。論理上の末尾への追加には、通常時の `push_back` と逆向きの `push_front` が対応する。論理上の先頭への追加では対応が逆になる。
- 例の操作 `k` より前に並べ替えたのは `1..k-1` の範囲だけなので、次の要素 `k` を論理上の末尾に加えてから反転すれば、先頭 `k` 項の操作になる。出力時にも向きを適用する。

## 計算量・注意点

1回の追加・反転は O(1)、`N` 要素の出力を含めて O(N) 時間、追加メモリ O(N)。例は `o` の判定より先に要素を追加する。任意長の部分区間を反転する場合は別のデータ構造が必要。

## 関連問題

<!-- BEGIN AUTO: related-problems -->

- [abc465_c](../../問題/AtCoder/abc465_c.md)

<!-- END AUTO: related-problems -->

## 関連する既存ノート

- [配列（主分野）](配列.md)
- [STL / deque（両端への追加）](../../STL/queue-stack-deque-heap.md)
