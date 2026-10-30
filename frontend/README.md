# FinAgent Lab 前端

Vue 3 + Vite 投研工作台，负责行情展示和六阶段分析流程的演示界面。

## 启动

```powershell
npm install
npm run dev
```

默认地址：`http://localhost:5199`。开发服务器将 `/api` 请求代理到 `http://127.0.0.1:8000`，因此需要同时启动 `backend/` 下的 FastAPI 服务才能加载真实行情。

## 目录

- `src/api/`：后端 API 客户端
- `src/components/`：页面组件
- `src/features/analysis/`：分析阶段定义、模拟内容生成和流程状态
- `src/features/market/`：K 线技术指标计算
- `src/router/`：页面路由
- `src/views/`：页面视图

分析流水线目前是前端模拟流程；行情数据通过后端 AKShare 接口获取。详见项目根目录的 `README.md`。
