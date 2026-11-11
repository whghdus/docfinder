"""자료 공유 메시지 → 구조화 필드 (PROJECT.md 4.2절)
python extract.py : data/test.csv 100건 → results/extraction.csv

순서: ① 정규식으로 URL·절대 날짜 → ② LLM으로 문맥 필드(프로젝트명, 유형, 위치 힌트, 핵심 조건, 상대 날짜) → ③ Pandas 정제
* 입력은 마스킹된 텍스트만. LLM 제공자는 .env (로컬 ollama면 PC 밖으로 안 나감)
"""
import json, re, sys, time
from datetime import date, timedelta
import pandas as pd
from parse_kakao import URL

FILE_TYPES = ["공고", "공지", "회의", "설문/투표", "기타"]
FIELDS = ["project_name", "file_type", "location_url", "location_hint", "due_date", "key_info"]
WEEKDAYS = "월화수목금토일"
# 절대 날짜: "10/1", "9월 11일" (URL을 지운 뒤에 찾음 → URL 속 숫자 오인 방지)
DATE_SLASH = re.compile(r"(?<![\d/])(\d{1,2})/(\d{1,2})(?![\d/])")
DATE_KOR = re.compile(r"(\d{1,2})월\s*(\d{1,2})일")
# 1차 실행에서 LLM이 마감 없는 메시지("넵 가능합니다")에도 보낸 날짜를 채움(26건 중 14건)
# → 본문에 마감 표현이 있을 때만 LLM 마감일을 인정
DUE_CUE = re.compile(r"까지|마감|기한|오늘|내일|모레|이번\s*주|다음\s*주|[월화수목금토일]요일")

PROMPT = """대학 동아리 운영진 단톡방 메시지에서 정보를 뽑아 JSON 하나로만 답하세요.
메시지 보낸 날짜: {day} ({weekday}요일)

필드:
- project_name: 무슨 일에 대한 메시지인지 짧은 이름 (예: "부원 모집", "운영진 회의")
- file_type: "공고", "공지", "회의", "설문/투표", "기타" 중 하나
- location_hint: URL 없이 자료 위치를 말로 설명한 경우 그 경로 (예: "운영진 노션 → 부원 관리 → 상벌점 페이지")
- due_date: "오늘까지", "이번 주 일요일까지" 같은 마감을 보낸 날짜 기준 YYYY-MM-DD로 바꾼 값
- key_info: 해야 할 일이나 조건을 한 문장으로

규칙: 메시지에 없는 정보는 지어내지 말고 null. 마감이 없으면 due_date는 null.
형식: {{"project_name": ..., "file_type": ..., "location_hint": ..., "due_date": ..., "key_info": ...}}

메시지:
{text}"""


def regex_fields(text, ts):
    """URL과 절대 날짜는 정규식이 LLM보다 정확하고 빠르므로 먼저 뽑음"""
    urls = URL.findall(text)
    rest = URL.sub(" ", text)
    m = DATE_KOR.search(rest) or DATE_SLASH.search(rest)
    due = None
    if m and 1 <= int(m[1]) <= 12 and 1 <= int(m[2]) <= 31:
        try:
            due = date(ts.year, int(m[1]), int(m[2])).isoformat()  # 연도는 메시지 날짜에서
        except ValueError:
            pass  # 2/30 같은 없는 날짜
    return {"location_url": urls[0] if urls else None, "due_date": due}


def llm_fields(text, ts):
    from llm import ask
    reply = ask(PROMPT.format(day=ts.date(), weekday=WEEKDAYS[ts.weekday()], text=text))
    try:
        return json.loads(reply[reply.find("{"): reply.rfind("}") + 1])  # 앞뒤 ```json 같은 군더더기 제거
    except json.JSONDecodeError:
        return {}  # 형식 오류는 전부 null 처리 (건수는 clean 뒤 통계로 확인)


def clean(df):
    """Pandas 정제: 빈 문자열/"null" → None, 유형은 5개 중 하나, 날짜는 형식·범위 검사"""
    for c in FIELDS:
        df[c] = df[c].map(lambda v: None if v is None or str(v).strip().lower() in ("", "null", "none", "nan")
                          else str(v).strip())
    df.loc[~df["file_type"].isin(FILE_TYPES), "file_type"] = None
    # LLM이 만든 마감일은 메시지 날짜 ~ 60일 뒤 범위만 인정 (작은 모델의 날짜 계산 실수 걸러냄)
    ts = pd.to_datetime(df["timestamp"]).dt.normalize()
    due = pd.to_datetime(df["due_date"], format="%Y-%m-%d", errors="coerce")
    bad = (df["due_src"] == "llm") & ~due.between(ts, ts + timedelta(days=60))
    df.loc[due.isna() | bad, "due_date"] = None
    df.loc[df["due_date"].isna(), "due_src"] = None
    return df


def extract(df):
    rows = []
    for i, r in enumerate(df.itertuples(), 1):
        ts = pd.Timestamp(r.timestamp)
        t0 = time.perf_counter()
        llm = llm_fields(r.text, ts)
        reg = regex_fields(r.text, ts)
        row = {"id": r.id, "timestamp": r.timestamp, **{c: llm.get(c) for c in FIELDS}}
        row["location_url"] = reg["location_url"]  # URL은 정규식 값만 씀
        llm_due = llm.get("due_date") if DUE_CUE.search(r.text) else None
        row["due_src"] = "regex" if reg["due_date"] else ("llm" if llm_due else None)
        row["due_date"] = reg["due_date"] or llm_due  # 절대 날짜 우선, 없으면 LLM 상대 날짜
        row["llm_ok"] = bool(llm)
        row["latency_s"] = round(time.perf_counter() - t0, 2)
        rows.append(row)
        print(f"\r{i}/{len(df)}", end="", file=sys.stderr)
    print(file=sys.stderr)
    return clean(pd.DataFrame(rows))


if __name__ == "__main__":
    test = pd.read_csv("data/test.csv", encoding="utf-8-sig")
    out = extract(test)
    out.to_csv("results/extraction.csv", index=False, encoding="utf-8-sig")
    print(f"{len(out)}건 → results/extraction.csv | JSON 오류 {(~out.llm_ok).sum()}건 | "
          f"URL {out.location_url.notna().sum()} | 마감일 {out.due_date.notna().sum()} "
          f"(정규식 {(out.due_src == 'regex').sum()}, LLM {(out.due_src == 'llm').sum()}) | "
          f"건당 평균 {out.latency_s.mean():.1f}초")
