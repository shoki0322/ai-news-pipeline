import os
import re
from openai import OpenAI


def _split_sentences(text: str) -> list[str]:
    if not text:
        return []
    t = text.strip()
    # Japanese: split even without spaces by matching sentence-ending punctuation
    jp_sentences = re.findall(r"[^。．！？!?]*[。．！？!?]", t)
    remainder = t[len("".join(jp_sentences)) :]
    if remainder:
        # Capture any tail without terminal punctuation
        jp_sentences.append(remainder)
    sentences = [s.strip() for s in jp_sentences if s and s.strip()]
    if not sentences:
        # Fallback chunking
        chunk_size = 80
        return [t[i:i+chunk_size] for i in range(0, len(t), chunk_size)]
    return sentences


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
    # Strictly enforce the upper bound without ellipsis; try to end at safe boundary (sentence/phrase)
    if len(summary) > max_chars:
        # Try dropping the last sentence if that keeps within bounds and above min_chars
        while len(summary) > max_chars and len(result) > 1:
            result.pop()
            summary = "".join(result)
            if len(summary) >= min_chars:
                break
        if len(summary) > max_chars:
            # Hard trim but avoid adding ellipsis; cut at safe boundary if possible
            trimmed = summary[:max_chars].rstrip()
            # Prefer sentence enders, then Japanese comma, then whitespace, then fallback
            ender_pos = max(trimmed.rfind(c) for c in "。．！？!?")
            comma_pos = trimmed.rfind("、")
            space_pos = trimmed.rfind(" ")
            cut_pos = max(ender_pos, comma_pos, space_pos)
            if cut_pos is not None and cut_pos >= 0:
                # Include the punctuation for sentence enders
                if trimmed[cut_pos:cut_pos+1] in "。．！？!?":
                    summary = trimmed[: cut_pos + 1]
                else:
                    summary = trimmed[: cut_pos].rstrip()
            else:
                summary = trimmed
    # If it's still shorter than min_chars and we can extend from original text, extend safely
    if len(summary) < min_chars and len(text) > len(summary):
        extra = text[len(summary): max(len(summary), min(len(text), min_chars))]
        combined = (summary + extra)
        if len(combined) > max_chars:
            combined = combined[:max_chars].rstrip()
            # Try to cut at safe boundary if possible
            candidates = [
                max(combined.rfind(c) for c in "。．！？!?"),
                combined.rfind("、"),
                combined.rfind(" "),
            ]
            cut_pos = max([p for p in candidates if p is not None])
            if cut_pos is not None and cut_pos >= max(min_chars * 2 // 3, 40):
                if combined[cut_pos:cut_pos+1] in "。．！？!?":
                    combined = combined[: cut_pos + 1]
                else:
                    combined = combined[: cut_pos].rstrip()
        summary = combined
    # Ensure the summary ends cleanly at a sentence boundary; normalize trailing punctuation
    summary = summary.strip()
    # If there is any sentence ender, prefer cutting there
    last_ender = max(summary.rfind(c) for c in "。．！？!?")
    if last_ender >= 0 and last_ender < len(summary) - 1:
        summary = summary[: last_ender + 1]
    # Remove trailing connectors/particles before adding period
    summary = re.sub(r"[、，,・\-]+$", "", summary).rstrip()
    summary = re.sub(r"(の|が|に|で|と|や|か|は|も|を|へ|より|から|まで|など)$", "", summary).rstrip()
    # Collapse trailing punctuation to a single Japanese period
    summary = re.sub(r"[。．.!?！？]+$", "。", summary)
    if not re.search(r"[。．]$", summary):
        summary = summary.rstrip() + "。"
    return summary


def summarize(text: str, max_chars: int = 500, min_chars: int = 450, max_sentences: int = 5) -> str:
    if not text:
        return text
    
    # Try OpenAI API first
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        try:
            client = OpenAI(api_key=api_key)
            prompt = (
                "あなたは有能なニュース記者です。以下の英文記事本文を日本語で“翻訳”ではなく“要約”してください。"
                f" 出力は{min_chars}〜{max_chars}文字に収め、{max_chars}文字を超えないでください。"
                " 箇条書きは使わず自然文で、冗長表現を避け、主語の重複を減らし、名詞密度を高めてください。"
                " 誰が・何を・なぜ・何が新しいか・影響/ユースケース・数値(ベンチマーク/価格/日付)があれば含めます。"
                " 断定調の見出し文体を目指し、必要な場合のみ一文追加で背景を補足してください。\n\n"
                f"本文:\n{text}"
            )
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a professional summarizer. Create concise Japanese summaries that capture the key points."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=700
            )
            summary = response.choices[0].message.content
            if summary:
                summary = summary.strip()
                # Ensure it's within the character limit strictly
                if len(summary) > max_chars:
                    summary = summary[:max_chars].rstrip()
                    if not summary.endswith("…"):
                        summary += "…"
                if len(summary) < min_chars:
                    # Pad using original text if the model produced too short output
                    extra = text[: max(0, min_chars - len(summary))]
                    summary = (summary + extra)[:max_chars]
                    if not summary.endswith("…") and len(summary) == max_chars:
                        summary = summary.rstrip() + "…"
                return summary
        except Exception as e:
            print(f"OpenAI summarization error: {e}, falling back to simple summarization")
    
    # Fallback: 日本語に機械翻訳してから簡易要約（長文も分割対応）
    try:
        from translate import translate_text_long, translate_text  # avoid top-level import cycles
        try:
            ja_text = translate_text_long(text)
            return _simple_summarize(ja_text, max_chars, min_chars, max_sentences)
        except Exception:
            # 翻訳に失敗した場合、まず英語で短く要約し、その短文だけ再翻訳
            en_short = _simple_summarize(text, max_chars, min_chars, max_sentences)
            ja_short = translate_text(en_short)
            return ja_short
    except Exception:
        # 最終フォールバック（英語のままの可能性あり）
        return _simple_summarize(text, max_chars, min_chars, max_sentences)