# モデル規約

## 1対1のリレーションは、Modelの$withでイーガーローディングする

bad:

```php
class User extends Model
{
    public function group()
    {
        return $this->belongsTo(Group::class);
    }
}

// コントローラーで毎回withを指定する必要があり、忘れるとN+1問題になる
$users = User::with('group')->get();
```

good:

```php
class User extends Model
{
    protected $with = [
        'group',
    ];

    public function group()
    {
        return $this->belongsTo(Group::class);
    }
}

// 常に自動的にイーガーローディングされる
$users = User::all();
```

## orWhere()はwhere()でクロージャーを使って利用する

`orWhere()`を単独で使うと意図しないクエリになる場合がある。`where()`のクロージャー内で使用する。

bad:

```php
// WHERE role = 'admin' AND active = 1 OR role = 'editor' となり、意図しない結果になる
$users = User::query()
    ->where('role', 'admin')
    ->where('active', 1)
    ->orWhere('role', 'editor')
    ->get();
```

good:

```php
// WHERE (role = 'admin' OR role = 'editor') AND active = 1 と意図通りになる
$users = User::query()
    ->where(function ($query) {
        $query->where('role', 'admin')
              ->orWhere('role', 'editor');
    })
    ->where('active', 1)
    ->get();
```

## getXXXAttributeは使わない

IDEで補完が効かないため、アクセサ（`getXXXAttribute`）は使わず、通常のメソッドとして定義する。

not good:

```php
public function getFullNameAttribute()
{
    return "{$this->first_name} {$this->last_name}";
}
```

good:

```php
public function getFullName()
{
    return "{$this->first_name} {$this->last_name}";
}
```

## モデルでget()を使うときはN+1問題に注意

モデルでget()を使うときは、そのメソッドの使われ方によってN+1問題にならないように注意する。

bad:

```php
class Category extends Model
{
    public static function getParentCategory($category_id)
    {
        return self::query()->where('id', $category_id)->get();
    }
}
```

```php
// in controller
$parent_categories = [];
foreach($categories as $category) {
    $parent_categories[] = Category::getParentCategory($category->id); // N+1問題
}
```

good:

```php
class CategoryService
{
    public function getParentCategories($category_ids)
    {
        return Category::query()->whereIn('id', $category_ids)->get();
    }
}
```

```php
// in controller
$parent_categories = (new CategoryService())->getParentCategories([$category->id]);
```
