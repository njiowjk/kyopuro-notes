# 最も近い要素の探索（set + 二分探索）

## 問題の特徴

- 数直線上に複数の要素が存在する。
    
- 現在位置から最も近い要素を探す。
    
- 選んだ要素は削除される。
    
- 距離が等しい場合は座標の小さい方を選ぶ。
    

## 解法の方針

### 1. 全探索を避ける

毎回すべての要素との距離を比較すると、計算量は $O(N^2)$ になる。

しかし、最も近い要素は、現在位置の左右にある最も近い要素のどちらかである。

そのため、左右の2要素だけを比較すればよい。

### 2. setで要素を管理する

`set` は要素を昇順に管理でき、探索・削除を $O(\log N)$ で行える。

- `upper_bound(x)`：`x` より大きい最初の要素
    
- `prev(r)`：`r` の1つ前の要素
    
- `erase()`：選んだ要素を削除する
    

これにより、現在位置の左右にある候補を効率よく取得できる。

### 3. 境界条件を考える

以下の3パターンに分ける。

1. `r == st.begin()`：左側に候補がないため、右側を選ぶ。
    
2. `r == st.end()`：右側に候補がないため、左側を選ぶ。
    
3. それ以外：左右の距離を比較する。
    

距離が等しいときは左側を選ぶため、比較には `>=` を使う。

## ソースコード

```
#include <bits/stdc++.h>
using namespace std;

using ll = long long;
#define rep(i, n) for (int i = 0; i < (int)(n); i++)

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);

    int n;
    cin >> n;

    set<ll> st;
    ll x = 0;
    ll ans = 0;

    rep(i, n) {
        int k;
        cin >> k;
        st.insert(k);
    }

    rep(i, n) {
        auto r = st.upper_bound(x);

        if (r == st.begin()) {
            ans += abs(x - *r);
            x = *r;
            st.erase(*r);
        } else if (r == st.end()) {
            auto l = prev(r);
            ans += abs(x - *l);
            x = *l;
            st.erase(*l);
        } else {
            auto l = prev(r);

            if (*r - x >= x - *l) {
                ans += abs(x - *l);
                x = *l;
                st.erase(*l);
            } else {
                ans += abs(*r - x);
                x = *r;
                st.erase(*r);
            }
        }
    }

    cout << ans << endl;

    return 0;
}
```

## 計算量

各操作の計算量は以下の通り。

- `upper_bound`：$O(\log N)$
    
- `prev`：$O(1)$
    
- `erase`：$O(\log N)$
    

これらを $N$ 回繰り返すため、

**時間計算量：$O(N\log N)$**

**空間計算量：$O(N)$**

## 今回学んだこと

- 最も近い要素を探す場合、ソートされた集合の左右の要素だけを比較すればよい。
    
- 要素の追加・削除がある場合は `set` を検討する。
    
- `upper_bound` と `prev` を組み合わせることで左右の候補を取得できる。
    
- `begin()` と `end()` の境界条件に注意する。
    
- 移動距離を計算してから現在位置を更新する。
    

## 類題での考え方

**「最も近い値・座標を探す」問題が出たら、まず二分探索を検討する。**

- 追加・削除がない → `vector` + `lower_bound`
    
- 追加・削除がある → `set` + `lower_bound` / `upper_bound`
    

全探索が必要なのかを考え、ソートされたデータの隣接要素だけで答えを求められないか検討する。

## 関連タグ

#競プロ #二分探索 #set #lower_bound #upper_bound #貪欲法