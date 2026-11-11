// GET /search 응답 한 건 (app.py의 docs 테이블 + score, snippet과 일치)
export type FileType = "공고" | "공지" | "회의" | "설문/투표" | "기타";

export interface SearchResult {
  id: number;
  timestamp: string;
  project_name: string | null;
  file_type: FileType | null;
  location_url: string | null;
  link_label: string | null; // 노션 페이지 이름, 매칭 없으면 도메인
  location_hint: string | null;
  due_date: string | null; // YYYY-MM-DD
  key_info: string | null;
  snippet: string; // 원문 앞 120자
  score: number;
}

// POST /correction 요청
export interface Correction {
  id: number;
  field: keyof Pick<SearchResult, "project_name" | "file_type" | "location_url" | "due_date" | "key_info">;
  value: string | null;
  note?: string;
}
