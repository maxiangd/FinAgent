"""智能体层：分析上下文、模型工具、分析师节点与共享状态。

按执行顺序：
- dataflows/               按任务区间取数，生成带来源、时间和限制说明的 EvidenceItem（分析前）
- analysis_context_builder 编排三条数据流，产出分析师使用的上下文
- tools/                   暴露给模型主动调用的受限工具，只读当前任务区间
- analysts/                各分析角色的节点实现（行情 / 基本面 / 新闻情绪 …）
- agent_state              LangGraph 节点间共享的状态
- llm_provider_client      OpenAI 兼容的多提供商模型调用与重试
"""
