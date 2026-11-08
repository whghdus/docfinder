"""LLM 호출 한 곳으로 모음. 제공자/모델/키는 .env에서만 읽음 (코드에 박지 않음)"""
import os
from dotenv import load_dotenv

load_dotenv()


def ask(prompt: str) -> str:
    provider, model, key = (os.environ[k] for k in ("LLM_PROVIDER", "LLM_MODEL", "LLM_API_KEY"))
    if provider == "anthropic":
        import anthropic
        r = anthropic.Anthropic(api_key=key).messages.create(
            model=model, max_tokens=2000, messages=[{"role": "user", "content": prompt}])
        return r.content[0].text
    if provider == "openai":
        from openai import OpenAI
        r = OpenAI(api_key=key).chat.completions.create(
            model=model, messages=[{"role": "user", "content": prompt}])
        return r.choices[0].message.content
    if provider == "gemini":
        from google import genai
        r = genai.Client(api_key=key).models.generate_content(model=model, contents=prompt)
        return r.text
    raise ValueError(f"지원하지 않는 LLM_PROVIDER: {provider}")
