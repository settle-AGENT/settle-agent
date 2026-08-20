import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 백엔드(Spring Boot)는 :8080, 프론트 dev는 :5173.
// 운영에서는 Caddy가 /api/* 를 전부 Spring으로 보낸다. dev도 같은 경로를 쓴다.
// AI(:8000)에 직접 붙지 않는다 — 인증과 session_id 고정을 Spring이 담당한다.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
    },
  },
  build: { outDir: "dist" },
});
