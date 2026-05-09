# ビュー規約

## ビューコンポーザは使わない

特定のデータをビューへ結合する場合は`ミドルウェア`を使う。

bad:

```php
// app/Providers/ViewServiceProvider.php
public function boot()
{
    View::composer('layouts.app', function ($view) {
        $view->with('notifications', Auth::user()->notifications);
    });
}
```

good:

```php
// app/Http/Middleware/ShareNotifications.php
class ShareNotifications
{
    public function handle($request, Closure $next)
    {
        view()->share('notifications', Auth::user()?->notifications ?? collect());
        return $next($request);
    }
}
```

## bladeで複雑な条件文を書かない

bladeで複雑な条件文を書くのを避け、コントローラー、モデルやサービスなどで行う。

bad:

```blade
// blade
@if ($user->birth_date->diff(now())->format('%y') >= 20)
   // 20歳以上です
@endif
```

good:

```php
// model
public function is20Over()
{
    return $this->birth_date->diff(now())->format('%y') >= 20;
}
```

```blade
{{-- blade --}}
@if ($user->is20Over())
   // 20歳以上です
@endif
```

## bladeでモデルを呼び出さない

MVCパターンに従い、blade内でモデルを直接呼び出さない。

bad:

```blade
// blade
@php
    $users = User::all();
@endphp
```

good:

```php
// controller
$users = User::all();

return view('user.index', compact('users'));
```

## フォームの生成にはLaravel Collectiveを使う

[Laravel Collective HTML](https://github.com/LaravelCollective/html)を使用してフォームを生成する。

bad:

```blade
<form method="POST" action="/users">
    @csrf
    <input type="text" name="username" value="{{ old('username') }}">
    <select name="role">
        @foreach($roles as $role)
            <option value="{{ $role->id }}" {{ old('role') == $role->id ? 'selected' : '' }}>{{ $role->name }}</option>
        @endforeach
    </select>
</form>
```

good:

```blade
{!! Form::open(['url' => '/users']) !!}
    {!! Form::text('username') !!}
    {!! Form::select('role', $roles->pluck('name', 'id')) !!}
{!! Form::close() !!}
```
