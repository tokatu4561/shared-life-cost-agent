# その他の規約

## Enumを使う

マジックナンバーを直接比較せず、Enumを使用する。

bad:

```php
if ($user->status == 1) {

}
```

good:

```php
if ($user->status == UserStatus::ACTIVE) {

}
```

## ネストされた三項演算子は使わない

可読性が著しく低下するため、ネストされた三項演算子は使用しない。

bad:

```php
$label = $user->isAdmin() ? 'Admin' : ($user->isEditor() ? 'Editor' : ($user->isViewer() ? 'Viewer' : 'Guest'));
```

good:

```php
$label = match (true) {
    $user->isAdmin()  => 'Admin',
    $user->isEditor() => 'Editor',
    $user->isViewer() => 'Viewer',
    default           => 'Guest',
};
```

## 日付はDateファサードを利用する

`Carbon\CarbonImmutable`を直接使用せず、`Illuminate\Support\Facades\Date`ファサードを使用する。

laravelのDateファサードはCarbonImmutableで、デフォルトで`'monthOverflow' => false, 'yearOverflow' => false`となっている。

bad:

```php
Carbon\CarbonImmutable::now();
```

better:

```php
Illuminate\Support\Facades\Date::now();
```
