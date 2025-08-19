import os
from openai import OpenAI
from deep_translator import GoogleTranslator


def translate_text(text: str) -> str:
    if not text:
        return text
    
    # Try OpenAI API first
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        try:
            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a professional translator. Translate the following text to Japanese. Provide only the translation without any explanation."},
                    {"role": "user", "content": text}
                ],
                temperature=0.3,
                max_tokens=1000
            )
            translated = response.choices[0].message.content
            if translated:
                return translated.strip()
        except Exception as e:
            print(f"OpenAI translation error: {e}, falling back to Google Translate")
    
    # Fallback to Google Translate
    try:
        return GoogleTranslator(source="auto", target="ja").translate(text)
    except Exception as e:
        print(f"Translation error: {e}")
        return text