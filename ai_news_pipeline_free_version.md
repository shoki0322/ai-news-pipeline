# AI ニュース自動収集・翻訳・要約・保存・通知パイプライン（完全無料版）

## ① 環境構築

1. **GitHub リポジトリ作成**
   - 例：`ai-news-pipeline`
2. **必要パッケージインストール**
   ```bash
   pip install feedparser requests deep-translator transformers torch slack_sdk notion-client python-dotenv
   環境変数ファイル .env 作成
   ```

ini
コピーする
編集する
SLACK_BOT_TOKEN=xoxb-xxxx
NOTION_TOKEN=secret_xxxx
NOTION_DATABASE_ID=xxxx
.gitignore に .env を追加してコミットしない

② 情報源リスト作成
RSS 対応サイト → rss_sources.json

json
コピーする
編集する
[
"https://venturebeat.com/category/ai/feed/",
"https://www.marktechpost.com/feed/",
"https://openai.com/blog/rss"
]
③ 記事取得（RSS）
fetch_articles.py

python
コピーする
編集する
import feedparser, hashlib, json
from datetime import datetime

def fetch_rss_articles(urls):
articles = []
for url in urls:
feed = feedparser.parse(url)
for entry in feed.entries:
articles.append({
"title": entry.title,
"link": entry.link,
"published": entry.get("published", datetime.utcnow().isoformat())
})
return articles

def deduplicate(articles):
seen, unique = set(), []
for a in articles:
h = hashlib.md5(a["link"].encode()).hexdigest()
if h not in seen:
seen.add(h)
unique.append(a)
return unique
④ 翻訳（deep-translator）
translate.py

python
コピーする
編集する
from deep_translator import GoogleTranslator

def translate_text(text):
try:
return GoogleTranslator(source='auto', target='ja').translate(text)
except Exception as e:
print(f"Translation error: {e}")
return text
⑤ 要約（Hugging Face 無料モデル）
summarize.py

python
コピーする
編集する
from transformers import pipeline

summarizer = pipeline("summarization", model="facebook/bart-large-cnn")

def summarize(text):
try:
result = summarizer(text, max_length=60, min_length=20, do_sample=False)
return result[0]['summary_text']
except Exception as e:
print(f"Summarization error: {e}")
return text[:120]
⑥ Notion 保存
save_notion.py

python
コピーする
編集する
from notion_client import Client
import os

notion = Client(auth=os.getenv("NOTION_TOKEN"))

def save_to_notion(title, url, summary, date):
notion.pages.create(
parent={"database_id": os.getenv("NOTION_DATABASE_ID")},
properties={
"Title": {"title": [{"text": {"content": title}}]},
"URL": {"url": url},
"Summary": {"rich_text": [{"text": {"content": summary}}]},
"Date": {"date": {"start": date}}
}
)
⑦ Slack 通知
notify_slack.py

python
コピーする
編集する
from slack_sdk import WebClient
import os

client = WebClient(token=os.getenv("SLACK_BOT_TOKEN"))

def send_to_slack(channel, title, url, summary):
message = f"_{title}_\n{summary}\n<{url}|記事リンク>"
client.chat_postMessage(channel=channel, text=message)
⑧ メインスクリプト
main.py

python
コピーする
編集する
import os, json
from fetch_articles import fetch_rss_articles, deduplicate
from translate import translate_text
from summarize import summarize
from save_notion import save_to_notion
from notify_slack import send_to_slack
from dotenv import load_dotenv

load_dotenv()

with open("rss_sources.json") as f:
rss_sources = json.load(f)

articles = deduplicate(fetch_rss_articles(rss_sources))

for a in articles:
ja_title = translate_text(a["title"])
summary = summarize(translate_text(a["title"]))
save_to_notion(ja_title, a["link"], summary, a["published"])
send_to_slack("#ai-速報", ja_title, a["link"], summary)
⑨ GitHub Actions 自動化
.github/workflows/news.yml

yaml
コピーする
編集する
name: AI News Pipeline

on:
schedule: - cron: "_/30 _ \* \* \*" # 30 分ごと
workflow_dispatch:

jobs:
run:
runs-on: ubuntu-latest
steps: - uses: actions/checkout@v3 - uses: actions/setup-python@v4
with:
python-version: 3.11 - run: pip install -r requirements.txt - run: python main.py
env:
SLACK_BOT_TOKEN: ${{ secrets.SLACK_BOT_TOKEN }}
NOTION_TOKEN: ${{ secrets.NOTION_TOKEN }}
NOTION_DATABASE_ID: ${{ secrets.NOTION_DATABASE_ID }}
