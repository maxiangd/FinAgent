# FinAgent Lab

A 股行情与多阶段投研流程演示项目。前端使用 Vue 3 + Vite，后端使用 FastAPI + AKShare。

## 项目结构

```text
FinancialAgent/
├─ requirements.txt                 # 后端 Python 依赖
├─ backend/
│  ├─ main.py                       # FastAPI 入口（uvicorn main:app）
│  ├─ config/settings.py            # 统一读取 .env 与环境变量
│  ├─ app/                          # Web/API 层
│  │  ├─ routers/                   # analysis_router / market_router / health_router
│  │  ├─ schemas/                   # 请求与响应模型（analysis_schemas.py）
│  │  └─ presenters/                # 把 Agent 状态整理成接口响应
│  ├─ agents/                       # 智能体层
│  │  ├─ agent_state.py             # LangGraph 共享状态 AgentState
│  │  ├─ analysis_context_builder.py# 按周期和日期组装分析上下文
│  │  ├─ research_context.py        # 分析结论 + 证据目录，供下游角色使用
│  │  ├─ llm_provider_client.py     # 多提供商大模型客户端
│  │  ├─ workflow/                  # LangGraph 工作流（接入 → 分析师 → 辩论 → 提案 → 风控 → PM）
│  │  ├─ analysts/                  # 分析师节点 + 共用的工具调用运行时
│  │  ├─ researchers/               # 多空双研究员（发言计数 + 角色轮转）
│  │  ├─ trader/                    # 交易提案
│  │  ├─ risk_mgmt/                 # 进攻 / 中性 / 保守三类风控评审
│  │  ├─ managers/                  # PM 最终决策
│  │  ├─ tools/                     # 模型可调用的受限工具，按分析师分子目录
│  │  │  ├─ market_analyst/         # 行情：K 线统计与明细
│  │  │  ├─ fundamental_analyst/    # 基本面：估值指标或定期财报
│  │  │  └─ news_sentiment_analyst/ # 新闻：覆盖情况与具体条目
│  │  └─ dataflows/                 # 数据流适配层，按主要服务的分析师分子目录
│  │     ├─ market_analyst/         # 行情与 K 线
│  │     ├─ fundamental_analyst/    # 财报与估值
│  │     └─ news_sentiment_analyst/ # 新闻与公告
│  └─ services/                     # 外部数据源（AKShare / 雪球 / 腾讯 / 巨潮）
│     ├─ market/                    # 行情类：图表展示与智能体分析共用
│     │  ├─ kline_data_service.py   # 日/周/月 K 线
│     │  ├─ market_snapshot_service.py # 行情快照（价格/市值/财务/行业）
│     │  └─ stock_name_service.py   # 代码表与搜索
│     ├─ analysis/                  # 分析类：供智能体构建证据
│     │  ├─ fundamental_data_service.py # 财务指标与历史基本面
│     │  └─ news_data_service.py    # 新闻与公司公告
│     └─ common/
│        └─ cache_manager.py        # 进程内缓存、重试与字段整理
└─ frontend/
   ├─ src/
   │  ├─ api/                       # http / market / analysis 三个客户端
   │  ├─ components/                # 页面组件
   │  ├─ features/
   │  │  ├─ analysis/               # 分析流程与阶段定义
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

## 缓存

`.env` 的 `CACHE_BACKEND` 决定缓存后端，改完重启生效：

| 取值 | 说明 |
| --- | --- |
| `memory`（默认） | 进程内缓存，单进程开发够用，不需要外部服务 |
| `redis` | 跨进程、重启后仍保留；多 worker 部署时使用。连接串写在 `REDIS_URL`，格式 `redis://:密码@127.0.0.1:6379/0` |

Redis 连不上时会自动回退到进程内缓存，并在日志里打一条 WARNING；日志中的连接串会隐藏密码。

K 线按 `(股票代码, 周期)` 缓存一份完整序列（根数由 `KLINE_*_LIMIT` 决定），图表加载与后续分析共用同一次取数，指定日期区间的请求直接从这份序列本地切片并补齐预热；请求更早的历史区间时才会重新回源。

## 当前边界

- 行情搜索、快照和日 K 线由 FastAPI 后端通过 AKShare 获取；周/月 K 线取自雪球接口（东财行情接口在部分网络下不可达），腾讯接口作为兜底。
- 六阶段链路已由 LangGraph 工作流真实执行（`POST /api/analysis/run`）：数据接入 → 三个分析师 → 多空辩论（3 轮）→ 交易提案 → 三类风控 → PM 决策，全部调用所选大模型；页面点「开始分析」会跑完整链路（约 1-2 分钟）并展示各阶段结果。交易提案仅作研究结果，不接入真实下单。
- 页面展示仅供学习和演示，不构成投资建议。

## 代码组织约定

- 按业务领域归类代码：行情相关逻辑放在 `features/market`，分析流程放在 `features/analysis`。
- Vue 响应式状态和纯计算逻辑使用模块与函数组织；只在需要封装独立状态和行为时引入类。
- 后端分层：`app/` 放 HTTP 路由、请求模型和响应组装，`agents/` 放智能体与数据流，`services/` 放外部数据源访问，配置统一从 `config/settings.py` 读取。

## 开发路线

真实多智能体工作流的分阶段实施计划见[Agent 工作流实施路线](./docs/AGENT_WORKFLOW_ROADMAP.md)。
