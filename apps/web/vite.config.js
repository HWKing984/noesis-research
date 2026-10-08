import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// 技术栈与 NOESIS 前端保持一致（Vite 5 + React 18 + Tailwind 4），这样原组件移植
// 时不需要跨栈改写。端口刻意避开 NOESIS 的 5178，避免同时跑两个前端时冲突。
//
// `/api` 走**同源代理**到业务 API：这样浏览器看到的是同源请求，后端不必开 CORS。
// 部署时前端与 API 由同一个网关对外，语义一致。
const API_TARGET = process.env.RESEARCH_API_TARGET || 'http://127.0.0.1:8100';
const proxy = {
  '/api': {
    target: API_TARGET,
    changeOrigin: false,
  },
};

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { port: 5180, strictPort: true, proxy },
  preview: { port: 4173, strictPort: true, proxy },
});
