"""카톡 대화 .txt → 파싱 → 버릴 줄 제거 → 중복 제거 → 민감 구간 제외 → 마스킹 → data/masked/kakao.csv
사용법: python parse_kakao.py <카톡원본.txt>
"""
import csv, json, re, sys
from datetime import datetime
from pathlib import Path
import pandas as pd

DATE_LINE = re.compile(r"^-+ (\d{4})년 (\d{1,2})월 (\d{1,2})일 .+ -+$")
MSG_LINE = re.compile(r"^\[(.+?)\] \[(오전|오후) (\d{1,2}):(\d{2})\] (.*)$")
SYSTEM_LINE = re.compile(r"님[이을].*(초대했습니다|나갔습니다|들어왔습니다)\.?$")
DROP_TEXT = re.compile(r"^(이모티콘|사진|사진 \d+장|동영상|메시지가 삭제되었습니다\.|파일: .*)$")
URL = re.compile(r"(https?://[^\s가-힣]+)")  # URL 뒤에 한글이 붙어도 한글에서 끊음


def to_24h(ampm, h, m):
    h = int(h) % 12 + (12 if ampm == "오후" else 0)  # 오전 12시 → 0시, 오후 12시 → 12시
    return f"{h:02d}:{m}"


def parse(lines):
    msgs, day = [], None
    for line in lines:
        line = line.rstrip("\n")
        if d := DATE_LINE.match(line):
            day = f"{int(d[1]):04d}-{int(d[2]):02d}-{int(d[3]):02d}"
        elif day is None or SYSTEM_LINE.search(line):
            continue  # 파일 헤더(첫 날짜선 이전), 초대/퇴장 안내
        elif m := MSG_LINE.match(line):
            msgs.append({"timestamp": f"{day} {to_24h(m[2], m[3], m[4])}", "sender": m[1], "text": m[5]})
        elif msgs:
            msgs[-1]["text"] += "\n" + line  # 여러 줄 메시지: 이전 메시지에 이어붙임
    return msgs


def bigrams(s):
    s = re.sub(r"\s+", "", s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


def similarity(a, b):
    """문자 2-gram 자카드 유사도 (0~1)"""
    A, B = bigrams(a), bigrams(b)
    return len(A & B) / len(A | B) if A | B else 0.0


def dedup(msgs, min_len=50, threshold=0.9):
    """긴 메시지끼리 거의 같으면 처음 것만 남김 (반복 모집 공고 등)"""
    kept, long_seen = [], []
    for m in msgs:
        if len(m["text"]) >= min_len:
            if any(similarity(m["text"], s) >= threshold for s in long_seen):
                continue
            long_seen.append(m["text"])
        kept.append(m)
    return kept


def load_ranges(path):
    if not Path(path).exists():
        return []
    df = pd.read_csv(path, comment="#")
    return list(zip(df["start"], df["end"]))


def is_sensitive(m, ranges, cfg):
    if any(s <= m["timestamp"] <= e for s, e in ranges):  # "YYYY-MM-DD HH:MM" 문자열은 사전순 = 시간순
        return True
    t = m["text"]
    if re.search(r"(깃허브|깃헙|github).{0,10}(아이디|id)", t, re.I):
        return True
    hit = any(k in t for k in cfg["exclude_keywords"])
    return hit and not any(k in t for k in cfg["keep_keywords"])  # 공개 모집 공고는 남김


def mask_plain(t, names):
    for name in sorted(names, key=len, reverse=True):  # 긴 이름부터 치환 ("김철수" 먼저, "철수" 나중)
        t = t.replace(name, names[name])
    t = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "[이메일]", t)
    t = re.sub(r"@(?!멤버)\S+", "@멤버", t)  # 매핑에 없는 @멘션
    t = re.sub(r"01[016789]-?\d{3,4}-?\d{4}", "[전화번호]", t)
    t = re.sub(r"\d[\d-]{8,}\d", lambda m: "[계좌]" if sum(c.isdigit() for c in m[0]) >= 10 else m[0], t)
    t = re.sub(r"(?<!\d)\d{8}(?!\d)", "[학번]", t)
    return t


def mask(t, names):
    # URL 안의 숫자(노션 ID 등)는 학번/계좌로 오인하지 않도록 URL 밖만 마스킹
    return "".join(p if URL.fullmatch(p) else mask_plain(p, names) for p in URL.split(t))


def main(src):
    msgs = parse(open(src, encoding="utf-8-sig"))
    n_parsed = len(msgs)
    senders = [m["sender"] for m in msgs]  # 제외될 메시지의 발신자도 본문에서 마스킹해야 하므로 미리 저장
    msgs = [m for m in msgs if not DROP_TEXT.match(m["text"].strip())]
    n_dropped = n_parsed - len(msgs)
    n_before = len(msgs)
    msgs = dedup(msgs)
    n_dup = n_before - len(msgs)

    cfg = json.load(open("data/filter_config.json", encoding="utf-8"))
    ranges = load_ranges("data/exclude_ranges.csv")
    n_before = len(msgs)
    msgs = [m for m in msgs if not is_sensitive(m, ranges, cfg)]
    n_excluded = n_before - len(msgs)

    # 발신자 → 멤버N (등장 순서대로), names.txt의 이름도 같은 표에 추가
    names = {}
    extra = Path("data/names.txt")
    extra_names = [l.strip() for l in extra.read_text(encoding="utf-8").splitlines()
                   if l.strip() and not l.startswith("#")] if extra.exists() else []
    for n in senders + extra_names:
        names.setdefault(n, f"멤버{len(names) + 1}")
    for i, m in enumerate(msgs):
        m["id"] = i
        m["sender"] = names[m["sender"]]
        m["text"] = mask(m["text"], names)

    Path("data/masked").mkdir(parents=True, exist_ok=True)
    pd.DataFrame(msgs)[["id", "timestamp", "sender", "text"]].to_csv("data/masked/kakao.csv", index=False)
    Path("data/raw").mkdir(parents=True, exist_ok=True)
    with open("data/raw/member_map.csv", "w", encoding="utf-8", newline="") as f:  # 매핑표는 raw에만
        csv.writer(f).writerows([["name", "alias"], *names.items()])

    print(f"파싱된 메시지: {n_parsed}")
    print(f"버린 메시지(사진/이모티콘 등): {n_dropped}")
    print(f"중복 제거: {n_dup}")
    print(f"민감 구간/키워드 제외: {n_excluded}")
    print(f"최종 메시지: {len(msgs)} → data/masked/kakao.csv")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("사용법: python parse_kakao.py <카톡원본.txt>")
    main(sys.argv[1])
