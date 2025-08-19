# GitHub Actions セットアップガイド

## 1. リポジトリの作成とプッシュ

```bash
# GitHubでリポジトリを作成後
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR_USERNAME/ai-news-pipeline.git
git push -u origin main
```

## 2. GitHub Secrets の設定

GitHub リポジトリの Settings → Secrets and variables → Actions から以下を追加：

### 必須の Secrets

1. **SLACK_BOT_TOKEN**

   - Slack App の Bot User OAuth Token
   - 形式: `xoxb-xxxxxxxxxxxxx-xxxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxx`
   - 取得方法: https://api.slack.com/apps → あなたの App → OAuth & Permissions

2. **NOTION_TOKEN**

   - Notion Integration Token
   - 形式: `secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
   - 取得方法: https://www.notion.so/my-integrations → New integration

3. **NOTION_DATABASE_ID**

   - Notion データベースの ID
   - 形式: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
   - 取得方法: データベースページの URL から抽出

4. **OPENAI_API_KEY**
   - OpenAI API Key
   - 形式: `sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`
   - 取得方法: https://platform.openai.com/api-keys

## 3. Actions の有効化

1. リポジトリの Actions タブをクリック
2. "I understand my workflows, go ahead and enable them" をクリック
3. `.github/workflows/news.yml` が自動的に認識される

## 4. 手動実行テスト

1. Actions タブ → AI News Pipeline
2. "Run workflow" ボタンをクリック
3. "Run workflow" を実行

## 5. 実行スケジュール

- **現在の設定**: 1 時間ごと（毎時 0 分）に自動実行
- **変更方法**: `.github/workflows/news.yml` の `cron` を編集

```yaml
# 例：
- cron: "0 */2 * * *" # 2時間ごと
- cron: "0 9,18 * * *" # 毎日9時と18時
- cron: "*/30 * * * *" # 30分ごと
```

## 6. Slack チャンネルの変更

`.github/workflows/news.yml` の 32 行目を編集：

```yaml
python main.py --slack-channel "#ai-news" # 本番チャンネル
```

## 7. 権限設定（last_processed.json の自動更新用）

Settings → Actions → General → Workflow permissions：

- "Read and write permissions" を選択
- "Allow GitHub Actions to create and approve pull requests" をチェック

## トラブルシューティング

### エラー: "Error: Process completed with exit code 1"

- Secrets が正しく設定されているか確認
- ログを確認して具体的なエラーメッセージを特定

### Slack に投稿されない

- Slack ボットがチャンネルに招待されているか確認
- SLACK_BOT_TOKEN が正しいか確認

### Notion に保存されない

- Notion Integration がデータベースに接続されているか確認
- NOTION_DATABASE_ID が正しいか確認

### OpenAI API エラー

- API 使用量制限を確認
- OPENAI_API_KEY が有効か確認
