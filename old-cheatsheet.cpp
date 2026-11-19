#include <bits/stdc++.h>
using namespace std;

#ifdef LOCAL
#include "algo/debug.h"
#else
#define debug(...) ((void)0)
#endif

using ll = long long;

constexpr ll INF = 1LL << 60;


// ============================================================
// C++ STL 競プロチートシート
// Pythonでよく使う操作との対応をコメントに記載
// ※ lower_bound / upper_bound / binary_search は基本的にソート済み範囲で使う
// ============================================================

void vector_and_string_examples() {
    // ---------- vector ----------
    vector<int> a = {3, 1, 4};

    a.push_back(2);       // Python: a.append(2)
    a.emplace_back(5);    // 末尾で直接生成
    int first = a.front();
    int last = a.back();

    a.pop_back();         // 末尾を削除。戻り値はない
    int n = static_cast<int>(a.size());
    bool empty = a.empty();

    for (int x : a) {
        cout << x << ' ';             // 値を読む
    }
    cout << '\n';

    for (int& x : a) {
        x *= 2;                        // 要素を書き換える
    }

    // N個を入力
    vector<int> b(5);
    for (int& x : b) cin >> x;

    // ---------- string ----------
    string s = "abcdef";

    char c = s[2];                     // 'c'
    string sub = s.substr(1, 3);       // "bcd"、開始位置と長さ
    s.push_back('g');
    s.pop_back();

    // 文字列内検索。見つからなければ string::npos
    size_t pos = s.find("cd");
    if (pos != string::npos) {
        cout << pos << '\n';
    }

    (void)first;
    (void)last;
    (void)n;
    (void)empty;
    (void)c;
    (void)sub;
}

void sort_and_search_examples() {
    vector<int> a = {5, 2, 8, 2, 1, 3};

    // ---------- sort / reverse ----------
    sort(a.begin(), a.end());                    // 昇順
    sort(a.begin(), a.end(), greater<>());       // 降順
    reverse(a.begin(), a.end());

    // 二分探索用に昇順へ戻す
    sort(a.begin(), a.end());

    // ---------- count / find ----------
    int twos = static_cast<int>(count(a.begin(), a.end(), 2));

    auto it = find(a.begin(), a.end(), 8);
    if (it != a.end()) {
        int index = static_cast<int>(it - a.begin());
        cout << index << '\n';
    }

    // ---------- Python bisect 対応 ----------
    int x = 2;

    // bisect_left(a, x)
    int left = static_cast<int>(
        lower_bound(a.begin(), a.end(), x) - a.begin()
    );

    // bisect_right(a, x)
    int right = static_cast<int>(
        upper_bound(a.begin(), a.end(), x) - a.begin()
    );

    int less_than_x = left;                       // x未満の個数
    int less_equal_x = right;                    // x以下の個数
    int greater_equal_x = static_cast<int>(a.size()) - left;   // x以上
    int greater_than_x = static_cast<int>(a.size()) - right;   // xより大きい
    int equal_x = right - left;                  // xの個数

    bool exists = binary_search(a.begin(), a.end(), x);

    // Python: insort_left(a, x)
    // 挿入位置探索はO(logN)だが、vectorへの挿入自体はO(N)
    a.insert(lower_bound(a.begin(), a.end(), x), x);

    // ---------- min / max ----------
    int mn = *min_element(a.begin(), a.end());
    int mx = *max_element(a.begin(), a.end());

    auto [mn_it, mx_it] = minmax_element(a.begin(), a.end());
    int mn_index = static_cast<int>(mn_it - a.begin());
    int mx_index = static_cast<int>(mx_it - a.begin());

    // ---------- 重複削除 ----------
    sort(a.begin(), a.end());
    a.erase(unique(a.begin(), a.end()), a.end());

    (void)twos;
    (void)less_than_x;
    (void)less_equal_x;
    (void)greater_equal_x;
    (void)greater_than_x;
    (void)equal_x;
    (void)exists;
    (void)mn;
    (void)mx;
    (void)mn_index;
    (void)mx_index;
}

void queue_stack_deque_heap_examples() {
    // ---------- queue: FIFO ----------
    queue<int> que;
    que.push(10);
    que.push(20);

    int q_front = que.front();
    que.pop();                         // pop()は値を返さない

    // ---------- stack: LIFO ----------
    stack<int> stk;
    stk.push(10);
    stk.push(20);

    int s_top = stk.top();
    stk.pop();

    // ---------- deque: 両端キュー ----------
    deque<int> dq;
    dq.push_back(10);
    dq.push_front(20);
    dq.pop_back();
    dq.pop_front();

    // ---------- priority_queue: max-heap ----------
    priority_queue<int> max_pq;
    max_pq.push(3);
    max_pq.push(10);
    max_pq.push(5);

    int maximum = max_pq.top();        // 10
    max_pq.pop();

    // ---------- min-heap ----------
    priority_queue<int, vector<int>, greater<>> min_pq;
    min_pq.push(3);
    min_pq.push(10);
    min_pq.push(5);

    int minimum = min_pq.top();        // 3
    min_pq.pop();

    // ---------- ダイクストラでよく使う形 ----------
    priority_queue<pair<ll, int>, vector<pair<ll, int>>, greater<>> pq; // {距離, 頂点}

    pq.push({10, 2});
    pq.push({3, 5});

    auto [dist, vertex] = pq.top();
    pq.pop();

    (void)q_front;
    (void)s_top;
    (void)maximum;
    (void)minimum;
    (void)dist;
    (void)vertex;
}

void set_and_map_examples() {
    // ---------- set ----------
    set<int> st;

    st.insert(3);
    st.insert(1);
    st.insert(3);                      // 重複は追加されない

    bool has_three = st.contains(3);   // C++20以降
    auto st_it = st.find(1);
    if (st_it != st.end()) {
        st.erase(st_it);
    }

    // set内でx以上の最小要素
    auto lb = st.lower_bound(2);
    if (lb != st.end()) {
        cout << *lb << '\n';
    }

    // ---------- multiset ----------
    multiset<int> mst = {1, 1, 2, 3};
    int ones = static_cast<int>(mst.count(1));

    // 1個だけ削除
    auto one_it = mst.find(1);
    if (one_it != mst.end()) {
        mst.erase(one_it);
    }

    // mst.erase(1); とすると値1を全部削除

    // ---------- map ----------
    map<string, int> mp;

    mp["apple"]++;
    mp["banana"] = 5;

    // mp[key] は存在しないkeyも0で作ってしまう
    if (mp.contains("apple")) {
        cout << mp["apple"] << '\n';
    }

    auto mp_it = mp.find("banana");
    if (mp_it != mp.end()) {
        cout << mp_it->first << ' ' << mp_it->second << '\n';
    }

    for (const auto& [key, value] : mp) {
        cout << key << ' ' << value << '\n';
    }

    // ---------- unordered_map ----------
    // 平均O(1)。順序は保証されない
    unordered_map<int, int> freq;
    freq[10]++;
    freq[20] += 3;

    (void)has_three;
    (void)ones;
}

void pair_and_tuple_examples() {
    // ---------- pair ----------
    pair<int, string> p = {3, "abc"};
    auto [number, text] = p;           // 構造化束縛

    vector<pair<int, ll>> edges;
    edges.push_back({2, 100});
    edges.emplace_back(3, 200);

    for (const auto& [to, cost] : edges) {
        cout << to << ' ' << cost << '\n';
    }

    // pairは first → second の順に辞書順比較される
    sort(edges.begin(), edges.end());

    // ---------- tuple ----------
    tuple<int, string, ll> t = {1, "xyz", 100};
    auto [a, b, c] = t;

    int first = get<0>(t);
    string second = get<1>(t);

    (void)number;
    (void)text;
    (void)a;
    (void)b;
    (void)c;
    (void)first;
    (void)second;
}

void numeric_and_algorithm_examples() {
    vector<int> a = {1, 2, 3, 4, 5};

    // Python: sum(a)
    ll total = accumulate(a.begin(), a.end(), 0LL);

    // 0, 1, 2, ..., n-1 を作る
    vector<int> p(5);
    iota(p.begin(), p.end(), 0);

    int g = gcd(12, 18);               // 6
    int l = lcm(12, 18);               // 36

    bool any_even = any_of(a.begin(), a.end(), [](int x) {
        return x % 2 == 0;
    });

    bool all_positive = all_of(a.begin(), a.end(), [](int x) {
        return x > 0;
    });

    bool none_negative = none_of(a.begin(), a.end(), [](int x) {
        return x < 0;
    });

    // 全順列。最初に昇順にしておく
    sort(p.begin(), p.end());
    do {
        // 現在の順列pを使う
    } while (next_permutation(p.begin(), p.end()));

    (void)total;
    (void)g;
    (void)l;
    (void)any_even;
    (void)all_positive;
    (void)none_negative;
}

void prefix_sum_examples() {
    vector<ll> a = {3, 1, 4, 1, 5};
    int n = static_cast<int>(a.size());

    // prefix[i] = a[0] + ... + a[i-1]
    vector<ll> prefix(n + 1);

    for (int i = 0; i < n; ++i) {
        prefix[i + 1] = prefix[i] + a[i];
    }

    // 半開区間 [l, r) の和
    int l = 1;
    int r = 4;
    ll range_sum = prefix[r] - prefix[l];

    (void)range_sum;
}

void character_count_examples() {
    string s = "competitiveprogramming";

    // 小文字26種類の頻度
    array<int, 26> cnt{};

    for (char c : s) {
        ++cnt[c - 'a'];
    }

    debug(cnt);
}

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    set_and_map_examples();

    // このファイルは参照用。
    // 必要な部分を問題コードへコピーして使う。
    //
    // lower_bound / upper_bound:
    //   Python bisect_left  -> lower_bound
    //   Python bisect_right -> upper_bound
    //
    // queue:
    //   front()で取得してからpop()
    //
    // stack / priority_queue:
    //   top()で取得してからpop()

    return 0;
}
