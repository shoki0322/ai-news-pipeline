import os
from openai import OpenAI
from deep_translator import GoogleTranslator


def translate_headline(title_en: str, max_len: int = 60) -> str:
    """
    英語タイトルを日本語に翻訳し、自然な見出し調に整形して返す。
    GPTを優先し、失敗時はGoogle翻訳にフォールバック。
    """
    if not title_en:
        return ""

    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        try:
            client = OpenAI(api_key=api_key)
            prompt = (
                "以下の英文タイトルを日本語に翻訳してください。"
                "翻訳は直訳ではなく、新聞やニュースサイトの見出しのように簡潔で力強い表現にしてください。"
                f"{max_len}文字以内を目安に短くまとめてください。"
                "文末は「〜を発表」「〜開始」「〜公開」のように名詞止め・見出し調にしてください。\n\n"
                f"Title: {title_en}"
            )
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a professional Japanese news editor."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            )
            ja = response.choices[0].message.content.strip()
            # 長すぎる場合はカット
            if len(ja) > max_len:
                ja = ja[:max_len].rstrip("。．. !！?？、，")
            return ja
        except Exception as e:
            print(f"OpenAI translation error: {e}, falling back to Google Translate")

    # Fallback: Google Translate
    try:
        ja = GoogleTranslator(source="auto", target="ja").translate(title_en)
        if len(ja) > max_len:
            ja = ja[:max_len].rstrip("。．. !！?？、，")
        return ja
    except Exception as e:
        print(f"Google Translate error: {e}")
        return title_en


def translate_text_long(text: str, chunk_size: int = 3000) -> str:
    """長文を日本語へ安定して翻訳（Google翻訳ベース、分割結合）。"""
    if not text:
        return ""
    try:
        chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
        out_parts: list[str] = []
        for ch in chunks:
            out_parts.append(GoogleTranslator(source="auto", target="ja").translate(ch))
        ja = "".join(out_parts)
        # 余分な空白を正規化
        ja = " ".join(ja.split())
        return ja
    except Exception as e:
        print(f"Long translation error: {e}")
        return text


def translate_text(text: str) -> str:
    """汎用テキストを日本語へ翻訳（見出しではなく通常文）。
    OpenAIが利用可能なら優先し、失敗時はGoogle翻訳にフォールバックする。
    """
    if not text:
        return ""
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        try:
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a professional translator. Translate the following text to Japanese. Provide only the translation without any explanation."},
                    {"role": "user", "content": text},
                ],
                temperature=0.3,
            )
            translated = response.choices[0].message.content
            if translated:
                return translated.strip()
        except Exception as e:
            print(f"OpenAI translation error: {e}, falling back to Google Translate")
    try:
        return GoogleTranslator(source="auto", target="ja").translate(text)
    except Exception as e:
        print(f"Google Translate error: {e}")
        return text
