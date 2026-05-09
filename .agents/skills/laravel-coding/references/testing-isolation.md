# テストコード - テスト間の独立性

## テスト間で影響し合わないようにする

各テストは他のテストに依存しないように書く。

### 生成したデータはクリーンアップする

bad:

```php
class FileTest extends TestCase
{
    private $filePath = 'testfile.txt';

    public function testWriteToFile()
    {
        Storage::disk('local')->put($this->filePath, "Hello, world!");

        $this->assertTrue(Storage::disk('local')->exists($this->filePath));
    }

    public function testReadFromFile()
    {
        $content = Storage::disk('local')->get($this->filePath);

        $this->assertEquals("Hello, world!", $content);
    }
}
```

good:

```php
class FileTest extends TestCase
{
    private $filePath = 'testfile.txt';

    // 各テストの最後に実行される
    protected function tearDown(): void
    {
        // テスト後にファイルをクリーンアップ
        Storage::disk('local')->delete($this->filePath);
        parent::tearDown();
    }

    public function testWriteToFile()
    {
        Storage::disk('local')->put($this->filePath, "Hello, world!");

        $this->assertTrue(Storage::disk('local')->exists($this->filePath));
    }

    public function testReadFromFile()
    {
        // 各テストで必要なデータは生成する　別のテストメソッドで生成したファイルを参照しない
        Storage::disk('local')->put($this->filePath, "Hello, world!");
        $content = Storage::disk('local')->get($this->filePath);

        $this->assertEquals("Hello, world!", $content);
    }
}
```

### RefreshDatabaseを使う

bad:

```php
class ProductTest extends TestCase
{
    public function testCreateProduct()
    {
        $product = Product::create(['id' => '1', 'name' => 'Example', 'price' => 100]);

        $this->assertDatabaseHas('products', ['name' => 'Example', 'price' => 100]);
    }

    public function testDeleteProduct()
    {
        //❌ testCreateProduct で登録したデータを利用している
        $product = Product::find(1);

        $product->delete();

        $this->assertDatabaseMissing('products', ['name' => 'Example']);
    }
}
```

good:

テストメソッドAで更新されたDBのデータがテストメソッドB実行時に反映されないようにできる。

```php
class ProductTest extends TestCase
{
    use RefreshDatabase;

    public function testCreateProduct()
    {
        $product = Product::factory()->create(['price' => 100]);

        $this->assertDatabaseHas('products', ['price' => 100]);
    }

    public function testDeleteProduct()
    {
        $product = Product::factory()->create();

        $product->delete();

        $this->assertDatabaseMissing('products', ['id' => $product->id]);
    }
}
```

## ランダムなSeederのデータを利用しない

ランダムに投入されているseederのデータに依存しない。依存しているランダムなデータの内容が変更・削除された場合に失敗する可能性がある。

bad:

```php
public function testUserLogin()
{
    // シーダーで投入されているユーザーデータを使う
    $user = User::find(1);

    $response = $this->actingAs($user)->get('/home');

    $response->assertStatus(200);
}
```

good:

```php
public function testUserLogin()
{
    // ファクトリーを使ってテスト用テストデータを作成する
    $user = User::factory()->create([
        'email' => 'test@example.com'
    ]);

    $response = $this->actingAs($user)->get('/home');

    $response->assertStatus(200);
}
```
