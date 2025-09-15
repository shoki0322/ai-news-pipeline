import os
import re
from openai import OpenAI


def _fallback_bulletize(text: str, max_items: int = 4, max_len: int = 120) -> list[str]:
    sentences = [s.strip() for s in re.split(r"[。．!?！？]", text) if s.strip()]
    points: list[str] = []
    for s in sentences:
        if len(points) >= max_items:
            break
        s = re.sub(r"\s+", " ", s)
        points.append("・" + s[:max_len])
    if not points:
        points = ["・" + text[:max_len]]
    return points
def summarize(text: str, max_items: int = 4) -> list[str]:
    """
    英文記事本文を日本語で要約し、3〜5点の箇条書きリストとして返す。
    """
    if not text:
        return []

    # 1. GPTで要約生成
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        try:
            client = OpenAI(api_key=api_key)
            prompt = (
                f"以下の英文記事を日本語で要約してください。\n"
                f"- 箇条書きで最大{max_items}点\n"
                "- 1点は120字以内、句点なし\n"
                "- 新しい事実、数値、日付、公開情報を優先\n"
                "- 序文や一般論は含めない\n\n"
                f"本文:\n{text}"
            )
            # Use Responses API to avoid parameter mismatch
            resp = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": "You are a concise Japanese news summarizer."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )
            content = resp.choices[0].message.content.strip()
            lines = [l.strip("・-•* ") for l in content.splitlines() if l.strip()]
            bullets = ["・" + l[:120] for l in lines[:max_items]]
            
            # 万一英語が混じっていたら翻訳
            if any(re.search(r"[A-Za-z]", b) for b in bullets):
                from translate import translate_text_long
                bullets = ["・" + translate_text_long(b) for b in bullets]
            
            return bullets
        except Exception as e:
            print(f"OpenAI summarization error: {e}, fallback mode")

    # 2. Fallback: シンプル分割＋スコアリング
    try:
        from translate import translate_text_long
        ja_text = translate_text_long(text)
    except Exception:
        ja_text = text
    return _fallback_bulletize(ja_text, max_items=max_items)
