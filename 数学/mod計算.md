# mod計算

答えを MOD で割った余りで管理する問題。

よく使うMOD:

```cpp
const ll MOD = 998244353;
// const ll MOD = 1000000007;
```

## 足し算

```cpp
a = (a + b) % MOD;
```

## 引き算

C++の `%` は負になることがあるので補正する。

```cpp
a = (a - b + MOD) % MOD;
```

差が MOD より大きくなる可能性がある一般形。

```cpp
a = ((a - b) % MOD + MOD) % MOD;
```

## 掛け算

```cpp
a = a * b % MOD;
```

`int` 同士だと掛け算前にoverflowすることがあるので `ll` を使う。

## 累乗

`pow()` ではなく二分累乗。

```cpp
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
```

計算量 O(log N)。

## 逆元

MOD が素数で、a が MOD の倍数でないとき

```cpp
ll inv = mod_pow(a, MOD - 2);
```

フェルマーの小定理を使っている。

割り算

```cpp
ll res = x * mod_pow(y, MOD - 2) % MOD;
```

普通の `x / y` は使えない。

## 正規化

```cpp
x %= MOD;
if (x < 0) x += MOD;
```

## 関連
- [[数学/組合せnCr]]
- [[STL/algorithm-numeric]]
