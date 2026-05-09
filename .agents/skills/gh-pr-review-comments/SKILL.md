---
name: gh-pr-review-comments
description: GitHub Pull Request のコードレビューを行い、差分の該当行へ短く実務的な inline コメントを投稿する。PR URLや番号でレビュー依頼、ブランチ切替、コメント修正、OpenAPIなどの仕様差分確認を求められたときに使う。
---

# PR Review Comment Flow

## 実行方針
- 事実と推測を分ける。
- 指摘は「問題 -> 影響 -> 改善案」の順で1から3文に収める。
- 優先度タグはユーザーが求めない限り付けない。
- コメントは diff の該当行に付ける。diff 外のファイルは file comment を使う。

## 手順
1. PR 情報を取得する。
```bash
gh pr view <pr> --json number,url,headRefName,baseRefName,headRefOid,files
```

2. PR ブランチへ切り替える。
```bash
git checkout -t origin/<headRefName>
```

3. 差分を確認する。
```bash
git diff origin/<baseRefName>...HEAD -- <path>
```
- 挙動回帰、後方互換、仕様整合を優先確認する。
- テスト削除やカバレッジ低下を確認する。

4. コメント本文を短く作る。
- 先頭ラベルや冗長な前置きを避ける。
- 例: `compare_period` 引数が削除されているため、既存クライアントが渡すと失敗する可能性があります。互換期間を設けるか、明示的エラーへの変換を検討してください。

5. inline comment を投稿する。
```bash
gh api repos/<owner>/<repo>/pulls/<pr>/comments -X POST \
  -f body='<comment>' \
  -f commit_id='<headRefOid>' \
  -f path='<file>' \
  -F line=<line> \
  -f side='RIGHT'
```

6. diff 外のファイルへコメントする。
```bash
gh api repos/<owner>/<repo>/pulls/<pr>/comments -X POST \
  -f body='<comment>' \
  -f commit_id='<headRefOid>' \
  -f path='<file>' \
  -f subject_type='file'
```

7. 既存コメントを修正する。
```bash
gh api repos/<owner>/<repo>/pulls/comments/<comment_id> -X PATCH -f body='<new_body>'
```

8. 結果を報告する。
- 投稿したコメント URL を列挙する。
- 未投稿の懸念があれば短く補足する。

## チェックリスト
- 公開パラメータの互換性を壊していないか。
- 新規レスポンス項目が仕様書に反映されているか。
- 仕様変更に合わせてテストが更新されているか。
- コメント文体が短く直接的か。
