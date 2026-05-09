# コントローラー規約

## 1つのbladeを複数のコントローラーから共用して使わない

bladeがどのコントローラーから参照されているのか分かりづらく、bladeを変更した場合、影響範囲が大きくなる。

代わりにコンポーネントや`@include`を利用して、ビューを共通化する。

bad:

```php
// UserController.php
public function index()
{
    $users = User::all();
    return view('shared.user-list', compact('users'));
}

// AdminController.php
public function users()
{
    $users = User::all();
    return view('shared.user-list', compact('users')); // 同じbladeを共用している
}
```

good:

```php
// UserController.php
public function index()
{
    $users = User::all();
    return view('user.index', compact('users'));
}

// AdminController.php
public function users()
{
    $users = User::all();
    return view('admin.users', compact('users'));
}
```

共通部分はコンポーネントや`@include`で共通化する。

```blade
{{-- resources/views/user/index.blade.php --}}
@include('components.user-table', ['users' => $users])

{{-- resources/views/admin/users.blade.php --}}
@include('components.user-table', ['users' => $users])
```
