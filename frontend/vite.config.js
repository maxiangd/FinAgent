import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    host: true,
    port: 5173,
    // 将前端 API 请求转发到本地 FastAPI 服务
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        // 完整分析链路可能持续 1-5 分钟，避免代理提前断开
        timeout: 600_000,
        proxyTimeout: 600_000,
      },
    },
  },
})
