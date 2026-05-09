# テストコード - テストの書き方

## AAA（Arrange-Act-Assert）か Given When Then で書く

可能な限り以下の順番で、三つの明確なセクションに分ける。

Arrange、Act、またはAssertのどの部分で問題が発生しているかを特定しやすくなり、デバッグが楽。テストを修正する必要が出た場合に、どの部分を変更すべきなのかが明確で保守しやすい。

- **Arrange (準備)**: テストに必要なオブジェクトや値を準備
- **Act (実行)**: テスト対象のコードを実行
- **Assert (検証)**: 期待される結果が得られたかを検証

bad:

```php
public function testUserRegister()
{
    // 準備・実行・検証が混在している
    $response = $this->post('/register', [
        'name' => 'John Doe',
        'email' => 'johndoe@example.com',
        'password' => 'securepassword123',
        'password_confirmation' => 'securepassword123'
    ]);
    $this->assertDatabaseHas('users', ['email' => 'johndoe@example.com']);
    $response->assertRedirect('/home');
    $user = User::where('email', 'johndoe@example.com')->first();
    $this->assertNotNull($user);
}
```

good:

```php
public function testUserRegister()
{
    // Arrange: 新しいユーザーのデータを準備
    $userData = [
        'name' => 'John Doe',
        'email' => 'johndoe@example.com',
        'password' => 'securepassword123',
        'password_confirmation' => 'securepassword123'
    ];

    // Act: ユーザー登録ルートにPOSTリクエストを送信を実行
    $response = $this->post('/register', $userData);

    // Assert: ユーザーがデータベースに登録されていることを検証
    $this->assertDatabaseHas('users', [
        'email' => 'johndoe@example.com'
    ]);
}
```

## if・forを使用しない（ロジックを含めない）

テストコードにロジックを含めないようにする。

bad:

```php
public function testResponseByUserType()
{
    $users = User::factory()->count(5)->create();

    foreach ($users as $user) {
        if ($user->type === 'admin') {
            $response = $this->actingAs($user)->get('/admin/dashboard');

            $response->assertStatus(200);
            $response->assertSee('Admin Dashboard');
        } elseif ($user->type === 'user') {
            $response = $this->actingAs($user)->get('/dashboard');

            $response->assertStatus(200);
            $response->assertSee('User Dashboard');
        } else {
            $response = $this->actingAs($user)->get('/');

            $response->assertStatus(302);
        }
    }
}
```

good:

```php
public function testAdminDashboardResponse()
{
    $admin = User::factory()->create(['type' => 'admin']);

    $response = $this->actingAs($admin)->get('/admin/dashboard');

    $response->assertStatus(200);
    $response->assertSee('Admin Dashboard');
}

public function testUserDashboardResponse()
{
    $user = User::factory()->create(['type' => 'user']);

    $response = $this->actingAs($user)->get('/dashboard');

    $response->assertStatus(200);
    $response->assertSee('User Dashboard');
}

public function testGuestResponse()
{
    $guest = User::factory()->create(['type' => 'guest']);

    $response = $this->actingAs($guest)->get('/');

    $response->assertStatus(302);
}
```

## 1つのテストメソッドで1つのアサーション

統合テストは複数アサーションが並ぶことも多いが、ユニットテストなどではテストメソッドが複雑になりすぎないように、1つの仕様をちゃんと検証しているか意識する。

ok（1つの操作に対する検証が複数並ぶ場合）:

```php
public function testStoreUser()
{
    $response = $this->post('/users', ['email' => 'test@example.com']);

    $response->assertStatus(200);
    $this->assertDatabaseHas('users', [
        'email' => 'test@example.com'
    ]);
}
```

bad（複数仕様を検証している）:

```php
class CartTest extends TestCase
{
    public function testAddCart()
    {
        // カートに追加できる
        $response = $this->postJson('/api/cart/item/add', ['product' => 'test']);
        $response->assertStatus(200);
        // 在庫がない場合
        $response = $this->postJson('/api/cart/item/add', ['product' => 'testNoStock']);
        $response->assertStatus(400);
        // 存在しない商品の場合
        $response = $this->postJson('/api/cart/item/add', ['product' => 'testNoProduct']);
        $response->assertStatus(422);
    }
}
```

good:

```php
// カートに追加できる
public function testAddItemToCartSuccessfully()
{
    $response = $this->postJson('/api/cart/item/add', ['product' => 'test']);
    $response->assertStatus(200);
}

// 在庫がない場合追加できない
public function testAddItemToCartFailsWhenNoStock()
{
    $response = $this->postJson('/api/cart/item/add', ['product' => 'testNoStock']);
    $response->assertStatus(400);
}

// 存在しない商品の場合追加できない
public function testAddItemToCartFailsForNotExist()
{
    $response = $this->postJson('/api/cart/item/add', ['product' => 'testNoProduct']);
    $response->assertStatus(422);
}
```

## 日時によって実行結果が変わらないようにする

`Carbon::setTestNow()`などで固定する。時間を固定しないでテストを行うと、ある時点で成功し、ある時点で失敗する可能性がある。

bad:

```php
public function testIsBirthdayToday()
{
    $user = User::factory()->create(['birth_date' => '2000-09-06']);

    // 9/6に実行すれば成功するが、それ以外の日は失敗する
    $this->assertTrue($user->isBirthday());
}
```

good:

```php
public function testIsBirthdayToday()
{
    $user = User::factory()->create(['birth_date' => '2000-09-06']);
    // 2024年9月6日に固定 これがないと 9/6以外の日は落ちる
    Date::setTestNow(Carbon::create(2024, 9, 6));

    $this->assertTrue($user->isBirthday());
}
```

## 可能な限りモックを利用して外部の依存を避ける

外部APIやサービスへの依存はモックに置き換える。

参考: https://readouble.com/laravel/11.x/ja/mocking.html

bad:

```php
public function testGetWeather()
{
    // 実際の外部APIを呼び出している
    $service = new WeatherService();
    $weather = $service->getCurrentWeather('Tokyo');

    $this->assertEquals('sunny', $weather['condition']);
}
```

good:

```php
public function testGetWeather()
{
    // 外部APIをモック化
    Http::fake([
        'api.weather.com/*' => Http::response([
            'condition' => 'sunny',
            'temperature' => 25,
        ], 200),
    ]);

    $service = new WeatherService();
    $weather = $service->getCurrentWeather('Tokyo');

    $this->assertEquals('sunny', $weather['condition']);
}
```

## なるべくassertTrueは使わない

`assertTrue`はどう失敗したかがわかりにくい。assertのメソッドが色々あるので、出来ればそちらを使う。booleanを返すメソッドの検証はok。

bad:

```php
$this->assertTrue($class instanceof TestModel);

// エラーログ
// Failed asserting that false is true.
```

good:

```php
$this->assertInstanceOf(TestModel::class, $class);

// エラーログ
// Failed asserting that an object is an instance of class App\Model\TestModel.
```
