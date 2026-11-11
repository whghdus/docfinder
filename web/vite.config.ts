import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// 개발 중에는 /search, /correction 요청을 FastAPI(8000)로 넘김 → CORS 걱정 없음
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy: { "/search": "http://localhost:8000", "/correction": "http://localhost:8000" } },
});
