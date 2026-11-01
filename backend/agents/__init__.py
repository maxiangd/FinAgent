"""智能体层：分析上下文、模型工具、角色节点与共享状态。

按执行顺序：
- dataflows/               按任务区间取数，生成带来源、时间和限制说明的 EvidenceItem（分析前）
- analysis_context_builder 编排三条数据流，产出分析师使用的上下文
- tools/                   暴露给模型主动调用的受限工具，只读当前任务区间
- roles/                   五个阶段的角色节点：analysts / researchers / trader / risk_mgmt / managers
- workflow/                LangGraph 工作流（节点接线与条件边）
- research_context         把分析师结论整理成下游角色的输入
- agent_state              LangGraph 节点间共享的状态
- llm_provider_client      OpenAI 兼容的多提供商模型调用与重试
"""
