"""
python gen_data.py template : 마스킹 로그 → test 후보 100건 → data/label_template.csv (라벨은 사용자가 직접)
python gen_data.py train    : 시드(data/seeds.csv, Claude 초안 + 사용자 검수) → LLM 변형 300건 → data/train.csv
  * test 메시지는 생성기에 절대 넣지 않음. 생성 결과가 test 후보와 비슷하면 버림(누수 방지)
"""
import io, json, re, sys
from pathlib import Path
import pandas as pd
from parse_kakao import dedup, similarity

KEYWORDS = ["http", "노션", "링크", "공지", "마감", "까지", "설문", "투표", "회의", "제출", "폼", "공고", "올려"]
LABEL_COLS = ["id", "text", "timestamp", "is_relevant", "project_name", "file_type", "location_url", "due_date"]


def make_template(n_total=100, max_pos=45, seed=42):
    df = pd.read_csv("data/masked/kakao.csv")
    is_cand = df["text"].apply(lambda t: any(k in t for k in KEYWORDS))
    pos = df[is_cand]
    pos = pos.sample(min(len(pos), max_pos), random_state=seed)
    # 음성 후보: "ㅋㅋ" 같은 너무 짧은 메시지는 점수만 부풀리므로 10자 이상만
    rest = df[~is_cand & (df["text"].str.len() >= 10)]
    neg = rest.sample(min(len(rest), n_total - len(pos)), random_state=seed)
    out = pd.concat([pos, neg]).sample(frac=1, random_state=seed)  # 섞어서 라벨링 편향 줄이기
    out = out.reindex(columns=LABEL_COLS)  # 라벨 칸은 빈 칸
    out.to_csv("data/label_template.csv", index=False, encoding="utf-8-sig")  # 엑셀에서 한글 깨짐 방지
    print(f"키워드 후보 {is_cand.sum()}건 중 {len(pos)}건 + 기타 {len(neg)}건 = {len(out)}건 → data/label_template.csv")


def load_seeds():
    text = Path("data/seeds.csv").read_text(encoding="utf-8-sig")  # utf-8-sig: 엑셀용 BOM 제거
    lines = [l for l in text.splitlines() if not l.startswith("#")]
    return pd.read_csv(io.StringIO("\n".join(lines)))


PROMPT = """다음은 대학 IT 동아리 운영진 카카오톡 단톡방 메시지입니다.
같은 성격(자료 공유/위치 안내 여부)을 유지하면서 프로젝트명, 날짜, 링크, 말투를 바꾼 새 메시지 {k}개를 만드세요.
- 실존 인물 이름, 이메일, 전화번호는 쓰지 마세요.
- 링크가 필요하면 https://www.notion.so/ 뒤에 임의의 32자리 16진수를 붙인 가짜 URL을 쓰세요.
- JSON 문자열 배열로만 답하세요. 예: ["메시지1", "메시지2"]

메시지: {text}"""


def make_train(n_target=300, k=5):
    from llm import ask
    seeds = load_seeds()
    # 양성/음성이 번갈아 나오게 정렬 → 300건에서 끊겨도 라벨 비율이 한쪽으로 쏠리지 않음
    seeds = seeds.assign(r=seeds.groupby("is_relevant").cumcount()).sort_values(["r", "is_relevant"]).reset_index(drop=True)
    if len(seeds) < 30:
        sys.exit(f"시드가 {len(seeds)}건입니다. data/seeds.csv에 30건 이상 필요합니다.")
    test_path = next((p for p in [Path("data/test.csv"), Path("data/label_template.csv")] if p.exists()), None)
    if test_path is None:
        sys.exit("data/test.csv가 없어 누수 검사를 할 수 없습니다.")
    test_texts = pd.read_csv(test_path, encoding="utf-8-sig")["text"].astype(str).tolist()
    print(f"누수 검사 대상: {test_path} {len(test_texts)}건")

    rows, n_leak, n_bad, i = [], 0, 0, 0
    while len(rows) < n_target:
        s = seeds.iloc[i % len(seeds)]
        reply = ask(PROMPT.format(k=k, text=s["text"]))
        i += 1
        try:  # 소형 모델은 가끔 JSON 형식을 틀림 → 그 응답만 건너뜀
            texts = [t for t in json.loads(reply[reply.find("["): reply.rfind("]") + 1]) if isinstance(t, str)]
        except json.JSONDecodeError:
            n_bad += 1
            continue
        print(f"호출 {i}회, 누적 {len(rows)}건", flush=True)
        for t in texts:
            if any(similarity(t, x) >= 0.6 for x in test_texts):  # test와 비슷한 문장은 버림
                n_leak += 1
                continue
            rows.append({"text": t, "is_relevant": int(s["is_relevant"]), "source": "llm_generated", "seed_id": (i - 1) % len(seeds)})

    gen = dedup(rows)[:n_target]  # 생성물끼리 거의 같은 문장 제거
    hand = [{"text": t, "is_relevant": int(l), "source": "seed", "seed_id": j}
            for j, (t, l) in enumerate(zip(seeds["text"], seeds["is_relevant"]))]
    train = pd.DataFrame(hand + gen)
    train.insert(0, "id", range(len(train)))
    train.to_csv("data/train.csv", index=False)

    seed_leak = sum(any(similarity(t, x) >= 0.6 for x in test_texts) for t in seeds["text"])
    print(f"LLM 호출 {i}회 (JSON 형식 오류로 건너뜀 {n_bad}회), 생성 {len(rows) + n_leak}건 중 test 유사로 버림 {n_leak}건, 중복 제거 후 {len(gen)}건 사용")
    print(f"시드 {len(hand)}건 중 test 유사 {seed_leak}건 (0이어야 함)")
    print(f"train.csv: {len(train)}건 (양성 {train['is_relevant'].sum()}, 음성 {(train['is_relevant'] == 0).sum()})")


if __name__ == "__main__":
    {"template": make_template, "train": make_train}[sys.argv[1]]()
