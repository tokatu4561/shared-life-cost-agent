# テストコード - 設定・運用

## SQLiteを使う（案件ごとで要相談）

インメモリのSQLiteを使った方がテストも高速なので良い、開発中の実行コストが下がる。実際の環境で利用してるデータベースへの接続も込みでテストしたい場合もあるので要相談。

phpunit.xmlの以下に行を追加する:

```xml
<env name="DB_CONNECTION" value="sqlite"/>
<env name="DB_DATABASE" value=":memory:"/>
```

## テスト内容のコメントをdocsで、日本語で書く（案件ごとで要相談）

ドキュメントとしても読みやすいので、日本語で書いた方が良い。

コメントに書いてることを `#[TestDox]` で書くと、実行時に表示できる。

参考: https://docs.phpunit.de/en/10.5/attributes.html#testdox

bad:

```php
public function testShopListResponse(): void
{
    $this->get('/api/shops')->assertStatus(200);
}
```

good:

```php
#[TestDox('店舗のリストの取得')]
public function testShopListResponse(): void
{
    $this->get('/api/shops')->assertStatus(200);
}
```
