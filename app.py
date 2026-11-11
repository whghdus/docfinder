"""검색 API (PROJECT.md 5절)
python app.py load   : results/extraction.csv + data/test.csv → docfinder.db (SQLite 한 파일)
uvicorn app:app      : GET /search?q=, POST /correction (→ data/corrections.jsonl, 저장만)

검색: 한국어는 조사가 붙어("제안서는") 공백 토큰이 잘 안 맞음 → 문자 2-gram 겹침 비율로 점수
"""
import json, re, sqlite3, sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
import pandas as pd
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from parse_kakao import bigrams

DB = "docfinder.db"
NOTION_ID = re.compile(r"([0-9a-f]{32})(?:[?#]|$)")


def load_titles():
    p = Path("data/notion/links.csv")
    return dict(pd.read_csv(p).values) if p.exists() else {}


def link_label(url, titles):
    """노션 URL의 32자리 ID → 페이지 이름. 매칭이 없으면 도메인만"""
    if not url:
        return None
    m = NOTION_ID.search(url.split("?")[0].rstrip("/") + "?")
    return titles.get(m[1]) if m and m[1] in titles else urlparse(url).netloc


def build_db():
    ext = pd.read_csv("results/extraction.csv", encoding="utf-8-sig")
    test = pd.read_csv("data/test.csv", encoding="utf-8-sig")[["id", "text", "is_relevant"]]
    df = ext.merge(test, on="id")
    # 지금은 사용자가 단 정답 라벨로 자료 공유 메시지만 남김. 3일차에 분류기 결과로 교체
    df = df[df["is_relevant"] == 1]
    titles = load_titles()
    df["link_label"] = df["location_url"].map(lambda u: link_label(u if isinstance(u, str) else None, titles))
    cols = ["id", "timestamp", "text", "project_name", "file_type", "location_url", "link_label",
            "location_hint", "due_date", "key_info"]
    with sqlite3.connect(DB) as con:
        df[cols].to_sql("docs", con, if_exists="replace", index=False)
    print(f"{len(df)}건 → {DB} (링크 {df.location_url.notna().sum()}개 중 노션 이름 매칭 "
          f"{df.link_label.isin(titles.values()).sum()}개)")


def search(q, k=10):
    with sqlite3.connect(DB) as con:
        con.row_factory = sqlite3.Row
        docs = [dict(r) for r in con.execute("SELECT * FROM docs")]
    qg = bigrams(q)
    if not qg:
        return []
    for d in docs:
        # 원문 + 추출 필드 + 노션 페이지 이름을 합쳐서 2-gram 집합을 만듦
        hay = " ".join(str(d[c]) for c in ["text", "project_name", "key_info", "location_hint", "link_label"] if d[c])
        d["score"] = round(len(qg & bigrams(hay)) / len(qg), 3)  # 질문 2-gram 중 문서에 있는 비율
    docs = [d for d in docs if d["score"] > 0]
    docs.sort(key=lambda d: (d["score"], d["timestamp"]), reverse=True)  # 점수가 같으면 최신 메시지 먼저
    return docs[:k]


app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])


@app.get("/search")
def api_search(q: str, k: int = 10):
    return [{**d, "snippet": d.pop("text")[:120]} for d in search(q, k)]


class Correction(BaseModel):
    id: int
    field: str
    value: str | None
    note: str | None = None


@app.post("/correction")
def api_correction(c: Correction):
    # 저장만 함 (재학습은 범위 밖)
    with open("data/corrections.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({**c.model_dump(), "at": datetime.now().isoformat(timespec="seconds")},
                           ensure_ascii=False) + "\n")
    return {"ok": True}


if Path("web/dist").exists():  # 빌드 후에는 한 서버에서 화면까지 서빙
    app.mount("/", StaticFiles(directory="web/dist", html=True), name="web")

if __name__ == "__main__" and sys.argv[1:] == ["load"]:
    build_db()
