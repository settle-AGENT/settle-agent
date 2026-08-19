import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 백엔드(Spring Boot)는 :8080, 프론트 dev는 :5173.
// /api 요청은 백엔드로 프록시한다.
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
