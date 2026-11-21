
重複を許すソート済み集合。要素の追加・削除をしながら、最小値・最大値を高速に取得できる。

## 基本操作

```cpp
multiset<int> st = {1, 1, 2, 3};

st.insert(4);            // 追加
auto it = st.find(2);    // 要素を検索
int cnt = st.count(1);   // 出現個数
```

## 削除

1個だけ削除。
```cpp
auto it = st.find(1);
if (it != st.end()) {
    st.erase(it);
}
```

同じ値をすべて削除。
```cpp
st.erase(1);
```

## 最小値・最大値

```cpp
int mn = *st.begin();   // 最小値
int mx = *st.rbegin();  // 最大値
```

空集合では参照できない。

## 二分探索

```cpp
auto it1 = st.lower_bound(x); // x以上の最小要素
auto it2 = st.upper_bound(x); // xより大きい最小要素
```

該当する要素がなければ `st.end()` を返す。

## 計算量

`N = st.size()`、`C = 値xの出現個数` とする。

| 操作 | 計算量 |
|---|---|
| `insert(x)` | O(log N) |
| `find(x)` | O(log N) |
| `count(x)` | O(log N + C) |
| `erase(it)` | 償却 O(1) |
| `erase(x)` | O(log N + C) |
| `*begin()` / `*rbegin()` | O(1) |
| `lower_bound(x)` / `upper_bound(x)` | O(log N) |
| `size()` / `empty()` | O(1) |

### 注意点

- `erase(x)` は同じ値をすべて削除する。
- `find(x)` → `erase(it)` による1個削除は全体で O(log N)。
- `count(x)` は重複が多いと O(log N) では済まない。
- `begin()` / `rbegin()` の参照前には空でないことを確認する。
- 要素を追加・削除しながら最大値・最小値を管理する場合に便利。