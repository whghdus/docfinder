"""노션 내보내기 → data/notion/schedule.csv(이름, 시작, 종료), links.csv(page_id, title)
사용법: python prep_notion.py <노션 내보내기 폴더>
"""
import re, sys
from pathlib import Path
import pandas as pd

KDATE = re.compile(r"(\d{4})년 (\d{1,2})월 (\d{1,2})일")


def to_iso(s):
    y, m, d = KDATE.search(s).groups()
    return f"{y}-{int(m):02d}-{int(d):02d}"


def main(folder):
    folder = Path(folder)
    # 일정: "2026년 8월 17일 → 2026년 8월 28일" 또는 하루짜리 "2026년 8월 29일"
    src = next(folder.glob("*_all.csv"))  # _all.csv에만 날짜 컬럼이 있음
    df = pd.read_csv(src, encoding="utf-8-sig").dropna(subset=["날짜"])
    parts = df["날짜"].str.split("→")
    schedule = pd.DataFrame({
        "name": df["이름"].str.strip(),
        "start": parts.str[0].map(to_iso),
        "end": parts.str[-1].map(to_iso),  # 하루짜리면 시작 = 종료
    })
    schedule.to_csv("data/notion/schedule.csv", index=False)

    # 링크: 첫 페이지 .md의 [이름](URL)에서 URL 속 32자리 ID 추출
    # "(?![0-9a-f])": 16진수 덩어리의 끝 32자리 ("일정%20" + ID처럼 앞에 숫자가 붙는 경우 대비)
    md = next(folder.glob("*.md")).read_text(encoding="utf-8")
    links = [(pid, title.strip()) for title, pid in re.findall(r"\[([^\]]+)\]\([^)]*?([0-9a-f]{32})(?![0-9a-f])[^)]*\)", md)]
    pd.DataFrame(links, columns=["page_id", "title"]).drop_duplicates("page_id").to_csv("data/notion/links.csv", index=False)

    print(f"schedule.csv: {len(schedule)}건 (원본 {len(df)}행)")
    print(f"links.csv: {len(links)}건")


if __name__ == "__main__":
    main(sys.argv[1])
