import { useState } from "react";

export default function SearchBar({ onSearch }: { onSearch: (q: string) => void }) {
  const [q, setQ] = useState("");
  return (
    <form
      className="flex gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (q.trim()) onSearch(q.trim());
      }}
    >
      <input
        className="flex-1 rounded border border-gray-300 px-3 py-2"
        placeholder="예: 상벌점 노션 링크"
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      <button className="rounded bg-blue-600 px-4 py-2 text-white hover:bg-blue-700">검색</button>
    </form>
  );
}
