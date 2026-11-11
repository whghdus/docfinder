import { useState } from "react";
import SearchBar from "./components/SearchBar";
import ResultCard from "./components/ResultCard";
import type { SearchResult } from "./types";

export default function App() {
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searched, setSearched] = useState(""); // 마지막으로 검색한 질문
  const [error, setError] = useState("");

  async function search(q: string) {
    setError("");
    try {
      const res = await fetch(`/search?q=${encodeURIComponent(q)}`);
      if (!res.ok) throw new Error(`서버 오류 ${res.status}`);
      setResults(await res.json());
      setSearched(q);
    } catch (e) {
      setError(e instanceof Error ? e.message : "검색 실패");
    }
  }

  return (
    <main className="mx-auto max-w-2xl px-4 py-8">
      <h1 className="mb-4 text-2xl font-bold">동아리 자료찾기</h1>
      <SearchBar onSearch={search} />
      {error && <p className="mt-4 text-red-600">{error}</p>}
      {searched && !error && (
        <p className="mt-4 text-sm text-gray-500">"{searched}" 결과 {results.length}건</p>
      )}
      <div className="mt-2 space-y-3">
        {results.map((r) => (
          <ResultCard key={r.id} result={r} />
        ))}
      </div>
    </main>
  );
}
