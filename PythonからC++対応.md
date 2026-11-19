# PythonからC++対応

Pythonで覚えた操作をC++で探すためのメモ。

| Python | C++ |
|---|---|
| `a.append(x)` | `a.push_back(x)` |
| `sum(a)` | `accumulate(a.begin(), a.end(), 0LL)` |
| `bisect_left(a, x)` | `lower_bound(a.begin(), a.end(), x)` |
| `bisect_right(a, x)` | `upper_bound(a.begin(), a.end(), x)` |
| `x in set` | `st.contains(x)` |
| `heapq` | `priority_queue<T, vector<T>, greater<>>` |
| `enumerate(a)` | 添字for / range-for |
| `itertools.permutations` | `next_permutation` |

## bisect
詳しくは [[STL/sort-search#lower_bound / upper_bound]]。

## heapq
Pythonの `heapq` は最小ヒープ。C++では次。

```cpp
priority_queue<int, vector<int>, greater<>> pq;
```

詳しくは [[STL/queue-stack-deque-heap]]。
