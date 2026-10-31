# FinAgent Lab

A 股行情与多阶段投研流程演示项目。前端使用 Vue 3 + Vite，后端使用 FastAPI + AKShare。

## 项目结构

```text
FinancialAgent/
├─ requirements.txt                 # 后端 Python 依赖
├─ backend/
│  ├─ main.py                       # FastAPI 应用与 HTTP 接口
│  ├─ routers/                       # 健康检查与行情 API 路由
│  ├─ services/market.py            # 行情数据获取、缓存与整理
└─ frontend/
   ├─ src/
   │  ├─ api/market.js              # 前端行情 API 客户端
   │  ├─ components/                # 页面组件
   │  ├─ features/
   │  │  ├─ analysis/               # 分析流程、状态和展示内容生成
   │  │  └─ market/                 # 行情图表计算逻辑
   │  ├─ router/                    # 页面路由
   │  ├─ styles/                    # 全局样式
   │  ├─ views/Home.vue             # 投研工作台
   │  ├─ App.vue                    # 应用外壳
   │  └─ main.js                    # 前端入口
   ├─ package.json
   └─ vite.config.js                # /api 代理到本地后端
```

## 本地启动

后端终端（先在项目根目录安装 Python 依赖，再进入 backend 启动服务）：

```powershell
python -m pip install -r requirements.txt
cd backend
cmd /c "set PYTHONIOENCODING=utf-8&& set PYTHONUTF8=1&& python -X utf8 -m uvicorn main:app --host 127.0.0.1 --port 8000 >> ..\.uvicorn.log 2>&1"
```

Uvicorn 日志会追加写入项目根目录的 `.uvicorn.log`。该文件已被 `.gitignore` 忽略，不会作为源码提交。

前端终端：

```powershell
cd frontend
npm install
npm run dev
```

Vite 默认运行在 `http://localhost:5173`，并将 `/api` 请求转发给 `127.0.0.1:8000`。

## 模型配置

在项目根目录 `.env` 里填写提供商的 API Key，页面「分析区间」右侧的下拉框只会出现在已配置的那几家；改完需要重启后端。

| 提供商 | 环境变量 | 默认模型 | 费用 |
| --- | --- | --- | --- |
| 智谱 GLM | `LLM_ZHIPU_API_KEY` | `glm-4-flash-250414` | 免费 |
| DeepSeek | `LLM_DEEPSEEK_API_KEY` | `deepseek-chat` | 付费 |
| 通义千问 | `LLM_QWEN_API_KEY` | `qwen-plus` | 付费 |

`LLM_DEFAULT_PROVIDER` 决定页面默认选中哪家，不填则按上表顺序取第一个已配置的。模型名可用 `LLM_<提供商>_MODEL` 覆盖。智谱的 Key 必须用「模型标准 API」类型，Coding Plan 套餐的 Key 调用会 401。

免费模型在高峰期限流比较常见，后端对 429/5xx 会按 3s、6s 自动退避重试，次数由 `LLM_MAX_ATTEMPTS`（默认 3）控制；重试后仍失败会在页面上提示换用其他提供商。

## 当前边界

- 行情搜索、快照和日 K 线由 FastAPI 后端通过 AKShare 获取；周/月 K 线取自雪球接口（东财行情接口在部分网络下不可达），腾讯接口作为兜底。
- 数据接入与行情分析师两个阶段已由后端真实执行，后者会调用所选大模型；辩论、交易提案、风控、PM 决策四个阶段尚未接入后端。
- 页面展示仅供学习和演示，不构成投资建议。

## 代码组织约定

- 按业务领域归类代码：行情相关逻辑放在 `features/market`，分析流程放在 `features/analysis`。
- Vue 响应式状态和纯计算逻辑使用模块与函数组织；只在需要封装独立状态和行为时引入类。
- 后端数据获取保持在 `services`，HTTP 路由和应用入口放在 `main.py`。

## 开发路线

真实多智能体工作流的分阶段实施计划见[Agent 工作流实施路线](./docs/AGENT_WORKFLOW_ROADMAP.md)。
