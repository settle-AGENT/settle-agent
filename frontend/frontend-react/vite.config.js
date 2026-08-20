import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 백엔드(Spring Boot)는 :8080, AI(FastAPI)는 :8000, 프론트 dev는 :5173.
// Spring 전용 엔드포인트(/api/v1/*)는 Spring으로, AI 엔드포인트는 AI로 직접 보낸다.
// 운영에서는 Caddy/Nginx가 경로별로 라우팅한다.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api/v1": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: { outDir: "dist" },
});
