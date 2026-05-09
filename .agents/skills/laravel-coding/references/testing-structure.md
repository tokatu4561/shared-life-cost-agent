# テストコード - 構造と命名規則

## 命名規則

テストコードでも共通の命名規則に従う。

## ディレクトリ構造、テストクラスの命名

- `/app` 配下の構造に合わせる
- データベース操作、ネットワーク呼び出し(外部API等)、フレームワークの機能などに依存するテストは `Feature` 配下に、それ以外のクラスや関数単体のテスト等は `Unit` ディレクトリに配置する
- テストファイルの命名はテストしたい対象のクラスの末尾に Test を加えたもの

```
app
├─ Services
│  ├─ RegisterService.php # データベースへの登録を処理内容に含むクラス
│  └─ FizzBuzzService.php # fizzbuzzを実装したクラス
└─ Controller
   └─ UserController.php # LaravelのController
tests
├─ Feature
│  ├─ Services # app配下の階層とあわせる
│  │  └─ StorageServiceTest.php # データベースを利用するためFeature
│  └─ Controller
│     └─ UserControllerTest.php # Laravelのルーティングと対応するコントローラーを含めたテストになるのでFeature
└─ Unit
   └─ Services # app配下の階層とあわせる
      └─ FizzBuzzServiceTest.php # Laravelの機能を利用しないのでUnit
```
