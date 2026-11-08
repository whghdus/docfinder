"""LLM 호출 한 곳으로 모음. 제공자/모델/키는 .env에서만 읽음 (코드에 박지 않음)"""
import json, os, urllib.request
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv()


@lru_cache
def gemini_client(key):
    """클라이언트를 한 번만 만들어 재사용. 매번 새로 만들면 요청 중에 객체가 정리되면서 연결이 닫힘"""
    from google import genai
    return genai.Client(api_key=key)


def ask(prompt: str) -> str:
    provider, model = os.environ["LLM_PROVIDER"], os.environ["LLM_MODEL"]
    key = os.getenv("LLM_API_KEY")  # ollama는 키 불필요
    if provider == "ollama":
        # 로컬 Ollama 서버에 HTTP 요청. 데이터가 PC 밖으로 나가지 않음
        body = {"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False}
        req = urllib.request.Request("http://localhost:11434/api/chat", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        return json.load(urllib.request.urlopen(req, timeout=600))["message"]["content"]
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
        r = gemini_client(key).models.generate_content(model=model, contents=prompt)
        return r.text
    raise ValueError(f"지원하지 않는 LLM_PROVIDER: {provider}")
