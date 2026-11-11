import { useState } from "react";
import type { Correction, SearchResult } from "../types";

const FIELDS: { key: Correction["field"]; label: string }[] = [
  { key: "project_name", label: "프로젝트명" },
  { key: "file_type", label: "유형" },
  { key: "location_url", label: "링크" },
  { key: "due_date", label: "마감일" },
  { key: "key_info", label: "핵심 내용" },
];

// 추출이 틀렸을 때 고칠 값을 서버에 보냄 (서버는 corrections.jsonl에 저장만)
export default function CorrectionForm({ result, onDone }: { result: SearchResult; onDone: () => void }) {
  const [field, setField] = useState<Correction["field"]>("project_name");
  const [value, setValue] = useState(result.project_name ?? "");
  const [status, setStatus] = useState("");

  async function submit() {
    const body: Correction = { id: result.id, field, value: value.trim() || null };
    const res = await fetch("/correction", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (res.ok) onDone();
    else setStatus(`저장 실패 (${res.status})`);
  }

  return (
    <div className="mt-2 flex flex-wrap gap-2 text-sm">
      <select
        className="rounded border border-gray-300 px-2 py-1"
        value={field}
        onChange={(e) => {
          const f = e.target.value as Correction["field"];
          setField(f);
          setValue(result[f] ?? "");
        }}
      >
        {FIELDS.map((f) => (
          <option key={f.key} value={f.key}>
            {f.label}
          </option>
        ))}
      </select>
      <input
        className="flex-1 rounded border border-gray-300 px-2 py-1"
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
      <button className="rounded bg-gray-800 px-3 py-1 text-white" onClick={submit}>
        저장
      </button>
      {status && <span className="text-red-600">{status}</span>}
    </div>
  );
}
