"""
python gen_data.py template : 마스킹 로그 → test 후보 100건 → data/label_template.csv (라벨은 사용자가 직접)
python gen_data.py train    : 시드(data/seeds.csv, Claude 초안 + 사용자 검수) → LLM 변형 300건 → data/train.csv
  * test 메시지는 생성기에 절대 넣지 않음. 생성 결과가 test 후보와 비슷하면 버림(누수 방지)
"""
import io, json, random, re, sys
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


PROMPT = """대학 IT 동아리 운영진 카카오톡 단톡방 메시지를 만듭니다.
아래 예시들과 같은 말투, 같은 길이로 새 메시지 {k}개를 쓰세요.
{rule}
- 동아리 운영진이 실제로 보내는 평범한 업무 연락처럼 쓰세요.
- 이모지, 유행어, 과장된 표현, 느낌표 남발은 쓰지 마세요.
- 실존 인물 이름, 이메일, 전화번호는 쓰지 마세요.
- JSON 문자열 배열로만 답하세요. 예: ["메시지1", "메시지2"]

예시:
{examples}"""
RNG = random.Random(42)  # 시드 고정 → 재실행해도 같은 가짜 URL
EMOJI = re.compile(r"[\U0001F000-\U0001FAFF☀-➿]")
# 라벨별 규칙: 1차 생성에서 음성에도 URL이 들어가 라벨 노이즈가 생겨 분리함
RULES = {
    1: "- 반드시 자료의 링크 또는 위치(노션 페이지 경로, 드라이브 폴더 등)를 알려주는 메시지\n"
       "- 링크는 https://www.notion.so/ 뒤에 임의의 32자리 16진수를 붙인 가짜 URL",
    0: "- 자료 공유가 아닌 메시지 (잡담, 대답, 일정 조율, 질문)\n- 링크, URL, 자료 위치는 절대 넣지 마세요",
}


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

    rows, n_leak, n_bad, n_url, n_emoji, i = [], 0, 0, 0, 0, 0
    while len(rows) < n_target:
        s = seeds.iloc[i % len(seeds)]
        label = int(s["is_relevant"])
        # 말투 기준점: 이번 시드 + 같은 라벨 시드 3개를 예시로 줌 (예시 1개면 모델이 자기 말투로 씀)
        others = seeds[(seeds.is_relevant == label) & (seeds.text != s["text"])].sample(3, random_state=i)
        examples = "\n".join(f"- {t}" for t in [s["text"], *others["text"]])
        reply = ask(PROMPT.format(k=k, rule=RULES[label], examples=examples))
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
            if label == 0 and "http" in t:  # 음성인데 링크가 들어간 문장은 라벨이 틀린 것 → 버림
                n_url += 1
                continue
            if EMOJI.search(t):  # 시드에 없는 이모지 → AI 말투로 보고 버림
                n_emoji += 1
                continue
            # 모델이 쓴 "abcdef1234..." 같은 가짜 ID는 패턴이 뻔해서 분류기가 그걸 단서로 배울 수 있음 → 랜덤 ID로 교체
            t = re.sub(r"https?://www\.notion\.so/\S+", lambda m: f"https://www.notion.so/{RNG.getrandbits(128):032x}", t)
            rows.append({"text": t, "is_relevant": label, "source": "llm_generated", "seed_id": (i - 1) % len(seeds)})

    gen = dedup(rows)[:n_target]  # 생성물끼리 거의 같은 문장 제거
    hand = [{"text": t, "is_relevant": int(l), "source": "seed", "seed_id": j}
            for j, (t, l) in enumerate(zip(seeds["text"], seeds["is_relevant"]))]
    train = pd.DataFrame(hand + gen)
    train.insert(0, "id", range(len(train)))
    train.to_csv("data/train.csv", index=False)

    seed_leak = sum(any(similarity(t, x) >= 0.6 for x in test_texts) for t in seeds["text"])
    print(f"LLM 호출 {i}회 (JSON 형식 오류로 건너뜀 {n_bad}회), 생성 {len(rows) + n_leak + n_url + n_emoji}건 중 test 유사로 버림 {n_leak}건, 음성인데 URL 있어 버림 {n_url}건, 이모지로 버림 {n_emoji}건, 중복 제거 후 {len(gen)}건 사용")
    print(f"시드 {len(hand)}건 중 test 유사 {seed_leak}건 (0이어야 함)")
    print(f"train.csv: {len(train)}건 (양성 {train['is_relevant'].sum()}, 음성 {(train['is_relevant'] == 0).sum()})")


FIX_COLS = ["location_url", "due_date"]


def make_fix_sheets():
    """test 양성 중 정답 칸(URL, 마감일)과 검색 질문을 사용자가 채우기 쉽게 시트로 뽑음
    * 추출 결과(LLM 예측)는 넣지 않음 → 정답이 모델 답을 베끼면 정확도가 부풀려짐"""
    from extract import DUE_CUE
    from parse_kakao import URL
    test = pd.read_csv("data/test.csv", encoding="utf-8-sig")
    pos = test[test["is_relevant"] == 1].copy()
    ts = pd.to_datetime(pos["timestamp"])
    pos["weekday"] = ts.dt.dayofweek.map(lambda d: "월화수목금토일"[d])
    pos["url_in_text"] = pos["text"].map(lambda t: " ".join(URL.findall(t)))  # 참고용, 원문 그대로
    pos["due_cue"] = pos["text"].map(lambda t: "있음" if DUE_CUE.search(t) else "")
    pos[["id", "timestamp", "weekday", "due_cue", "url_in_text", "location_url", "due_date", "text"]].to_csv(
        "data/label_fix.csv", index=False, encoding="utf-8-sig")
    pos["head"] = pos["text"].str.replace("\n", " ").str[:80]
    pos[["id", "timestamp", "project_name", "file_type", "head"]].to_csv(
        "data/queries_ref.csv", index=False, encoding="utf-8-sig")
    if not Path("data/queries.csv").exists():
        pd.DataFrame(columns=["query", "answer_ids"]).to_csv("data/queries.csv", index=False, encoding="utf-8-sig")
    print(f"data/label_fix.csv {len(pos)}건 (마감 표현 {(pos.due_cue != '').sum()}, URL {(pos.url_in_text != '').sum()}), "
          "data/queries_ref.csv, data/queries.csv")


def apply_fix_and_check():
    """label_fix.csv의 URL·마감일을 test.csv에 반영하고, queries.csv 형식을 검사"""
    test = pd.read_csv("data/test.csv", encoding="utf-8-sig")
    fix = pd.read_csv("data/label_fix.csv", encoding="utf-8-sig").set_index("id")
    # review 칸에 "제외"가 남은 행은 test에서 뺌 (지원자 평가 등 민감 정보, 3.2절)
    drop = fix.index[fix.get("review", pd.Series(dtype=str)).fillna("").str.contains("제외")]
    test = test[~test["id"].isin(drop)]
    if len(drop):
        print(f"test에서 제외: id {list(drop)}")
    fix = fix[FIX_COLS]
    bad = fix["due_date"].dropna()
    bad = bad[pd.to_datetime(bad, format="%Y-%m-%d", errors="coerce").isna()]
    assert bad.empty, f"마감일은 YYYY-MM-DD 형식이어야 함: id {list(bad.index)}"
    for c in FIX_COLS:
        test[c] = test["id"].map(fix[c]).where(test["is_relevant"] == 1, test[c])
    test.to_csv("data/test.csv", index=False, encoding="utf-8-sig")
    print(f"test.csv 반영: URL {test.location_url.notna().sum()}건, 마감일 {test.due_date.notna().sum()}건")

    q = pd.read_csv("data/queries.csv", encoding="utf-8-sig")
    pos_ids = set(test.loc[test["is_relevant"] == 1, "id"])
    for r in q.itertuples():
        ids = [int(x) for x in str(r.answer_ids).split(";") if x.strip()]
        wrong = [i for i in ids if i not in pos_ids]
        assert ids and not wrong, f"'{r.query}': 정답 id가 없거나 양성 메시지가 아님 {wrong}"
    print(f"queries.csv {len(q)}개 정상 (목표 15개)")


if __name__ == "__main__":
    {"template": make_template, "train": make_train,
     "fix-sheets": make_fix_sheets, "apply-fix": apply_fix_and_check}[sys.argv[1]]()
