# 組合せ nCr

`n` 個から `r` 個選ぶ組合せ数。

MOD が素数で、多数の nCr を求めるときは階乗と逆階乗を前計算する。

## 前計算

```cpp
const ll MOD = 998244353;

ll mod_pow(ll a, ll n) {
    a %= MOD;
    if (a < 0) a += MOD;
    ll res = 1;

    while (n > 0) {
        if (n & 1) {
            res = res * a % MOD;
        }

        a = a * a % MOD;
        n >>= 1;
    }

    return res;
}

vector<ll> fact(n + 1);
vector<ll> inv_fact(n + 1);

fact[0] = 1;

for (int i = 1; i <= n; i++) {
    fact[i] = fact[i - 1] * i % MOD;
}

inv_fact[n] = mod_pow(fact[n], MOD - 2);

for (int i = n; i >= 1; i--) {
    inv_fact[i - 1] = inv_fact[i] * i % MOD;
}
```

## nCr

```cpp
auto comb = [&](int n, int r) -> ll {
    if (r < 0 || r > n) return 0;

    return fact[n]
        * inv_fact[r] % MOD
        * inv_fact[n - r] % MOD;
};
```

前計算 O(N)、各 nCr O(1)。

## 1回だけ・Nが小さい場合

MOD不要なら

```cpp
ll res = 1;

for (int i = 1; i <= r; i++) {
    res = res * (n - i + 1) / i;
}
```

ただし値が大きいとoverflowする。

## 注意

上の逆元を使う方法は「MODが素数」の典型用。
また、単純な階乗法は通常 `n < MOD` の範囲で使う。

## 関連
- [[数学/mod計算]]
