import { useState } from "react";
import CorrectionForm from "./CorrectionForm";
import type { SearchResult } from "../types";

export default function ResultCard({ result: r }: { result: SearchResult }) {
  const [editing, setEditing] = useState(false);
  return (
    <div className="rounded border border-gray-200 bg-white p-4">
      <div className="flex items-center gap-2">
        {r.file_type && <span className="rounded bg-gray-100 px-2 py-0.5 text-xs">{r.file_type}</span>}
        <h2 className="font-semibold">{r.project_name ?? "(프로젝트명 없음)"}</h2>
        <span className="ml-auto text-xs text-gray-400">{r.timestamp}</span>
      </div>
      <div className="mt-2 space-y-1 text-sm">
        {r.location_url && (
          <p>
            링크:{" "}
            <a className="text-blue-600 underline" href={r.location_url} target="_blank" rel="noreferrer">
              {r.link_label ?? r.location_url}
            </a>
          </p>
        )}
        {r.location_hint && <p>위치: {r.location_hint}</p>}
        {r.due_date && <p className="text-red-600">마감: {r.due_date}</p>}
        {r.key_info && <p>{r.key_info}</p>}
        <p className="whitespace-pre-line text-gray-500">{r.snippet}</p>
      </div>
      <button className="mt-2 text-xs text-gray-500 underline" onClick={() => setEditing(!editing)}>
        {editing ? "닫기" : "수정"}
      </button>
      {editing && <CorrectionForm result={r} onDone={() => setEditing(false)} />}
    </div>
  );
}
