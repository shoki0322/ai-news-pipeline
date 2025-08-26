import os
import re
from openai import OpenAI
from deep_translator import GoogleTranslator


def _postprocess_japanese_headline(text: str) -> str:
    """
    日本語訳のタイトル末尾の「します」「しました」「です」「ます」「でしょう」などを
    不自然でない範囲で簡潔な見出し調へ整える。
    例: 「〜を発表しました」→「〜を発表」, 「〜が開始します」→「〜開始」
    過度な変形は避け、基本は終止形・名詞止めを優先。
    """
    if not text:
        return text
    t = text.strip()
    # サイト接尾辞（| や - 区切り）を除去
    t = re.sub(r"\s*[|｜\-—–]\s*[^|｜\-—–]+$", "", t)
    # 末尾の丁寧語より先に「でき」系を辞書形へ
    t = re.sub(r"できますか$", "できる", t)
    t = re.sub(r"できます$", "できる", t)
    t = re.sub(r"できました$", "できた", t)
    # 末尾の丁寧語を簡易に削る
    t = re.sub(r"(を)?発表しました$", "を発表", t)
    t = re.sub(r"(を)?発表します$", "を発表", t)
    t = re.sub(r"開始しました$", "開始", t)
    t = re.sub(r"開始します$", "開始", t)
    t = re.sub(r"提供を開始しました$", "提供開始", t)
    t = re.sub(r"提供します$", "提供", t)
    t = re.sub(r"公開しました$", "公開", t)
    t = re.sub(r"公開します$", "公開", t)
    t = re.sub(r"発表しました$", "発表", t)
    t = re.sub(r"発表します$", "発表", t)
    t = re.sub(r"リリースしました$", "リリース", t)
    t = re.sub(r"リリースします$", "リリース", t)
    t = re.sub(r"実現します$", "実現", t)
    # 疑問形を断定系に寄せる
    t = re.sub(r"か[?？]$", "", t)
    t = re.sub(r"[?？]$", "", t)
    # 汎用的な丁寧語語尾を弱めに刈り取る（語感が崩れない範囲）
    t = re.sub(r"(でした|でした。)$", "", t)
    t = re.sub(r"(ます|ます。)$", "", t)
    t = re.sub(r"(です|です。)$", "", t)
    # 不完全な「…ことができ」で終わっていれば補完
    t = re.sub(r"ことができ$", "ことができる", t)
    # 語尾は句点を残さず見出し調に（余計な約物も除去）
    t = t.rstrip("。．. !！")
    return t


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
                return _postprocess_japanese_headline(translated.strip())
        except Exception as e:
            print(f"OpenAI translation error: {e}, falling back to Google Translate")
    
    # Fallback to Google Translate
    try:
        return _postprocess_japanese_headline(GoogleTranslator(source="auto", target="ja").translate(text))
    except Exception as e:
        print(f"Translation error: {e}")
        return text


def translate_text_long(text: str, chunk_size: int = 3500) -> str:
    if not text:
        return text
    # 粗くチャンク分割（単純に文字数基準）
    chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
    results: list[str] = []
    for ch in chunks:
        try:
            results.append(translate_text(ch))
        except Exception:
            results.append(ch)
    return "".join(results)


def translate_headline(title_en: str) -> str:
    if not title_en:
        return title_en
    t = title_en.strip()
    # 英語のサイト接尾辞（|, -, —）を左側に寄せて除去
    parts = re.split(r"\s*[|\-—–]\s+", t)
    if parts:
        # 最長の左側セグメントを優先しつつ、短すぎる場合は元を維持
        candidate = parts[0].strip()
        if len(candidate) >= 8:
            t = candidate
    # 翻訳→日本語見出し調
    ja = translate_text(t)
    return _postprocess_japanese_headline(ja)