import os
import re
from openai import OpenAI


def _split_sentences(text: str) -> list[str]:
    if not text:
        return []
    # Split by Japanese and English sentence punctuation
    parts = re.split(r"(?<=[。．！？!\?])\s+|(?<=[.!?])\s+", text.strip())
    # Fallback to chunking if no obvious punctuation
    if len(parts) <= 1:
        chunk_size = 80
        return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
    return [p.strip() for p in parts if p.strip()]


def _simple_summarize(text: str, max_chars: int = 300, min_chars: int = 160, max_sentences: int = 4) -> str:
    if not text:
        return text
    sentences = _split_sentences(text)
    if not sentences:
        return text[:max_chars] + ("…" if len(text) > max_chars else "")

    result = []
    length = 0
    for s in sentences:
        if len(result) >= max_sentences:
            break
        result.append(s)
        length += len(s)
        if length >= min_chars:
            break

    summary = "".join(result)
    if len(summary) > max_chars:
        summary = summary[:max_chars].rstrip() + "…"
    return summary


def summarize(text: str, max_chars: int = 400, min_chars: int = 300, max_sentences: int = 5) -> str:
    if not text:
        return text
    
    # Try OpenAI API first
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        try:
            client = OpenAI(api_key=api_key)
            prompt = f"以下のテキストを{min_chars}〜{max_chars}文字の日本語で要約してください。必ず{min_chars}文字以上書いてください。技術的な詳細、重要な数値、主要な特徴、背景情報、今後の展望など、できるだけ多くの情報を含めてください。\n\nテキスト:\n{text}"
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a professional summarizer. Create concise Japanese summaries that capture the key points."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=500
            )
            summary = response.choices[0].message.content
            if summary:
                summary = summary.strip()
                # Ensure it's within the character limit
                if len(summary) > max_chars:
                    summary = summary[:max_chars].rstrip() + "…"
                return summary
        except Exception as e:
            print(f"OpenAI summarization error: {e}, falling back to simple summarization")
    
    # Fallback to simple summarization
    return _simple_summarize(text, max_chars, min_chars, max_sentences)