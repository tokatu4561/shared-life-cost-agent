# バッチ処理規約

## バッチ処理はステートレスを意識して作成する

バッチ処理はステートレスに設計し、複数サーバーで実行しても問題ないようにする。

参考: https://laravel.com/docs/9.x/scheduling#running-tasks-on-one-server

bad:

```php
class SyncOrdersCommand extends Command
{
    protected $lastSyncedId = 0; // インスタンス変数に状態を持つ

    public function handle()
    {
        $orders = Order::where('id', '>', $this->lastSyncedId)->get();
        foreach ($orders as $order) {
            $this->processOrder($order);
            $this->lastSyncedId = $order->id; // メモリ上の状態に依存
        }
    }
}
```

good:

```php
class SyncOrdersCommand extends Command
{
    public function handle()
    {
        // DBから状態を取得し、複数サーバーで実行しても安全
        $orders = Order::where('synced', false)->get();
        foreach ($orders as $order) {
            $this->processOrder($order);
            $order->update(['synced' => true]);
        }
    }
}
```
