"""分析任务使用的行情、基本面和新闻数据流。

按主要服务的分析师分子目录：
- market_analyst/           行情与 K 线 → 行情分析师（同时是所有分析共享的基础上下文）
- fundamental_analyst/      财报与估值 → 基本面分析师（尚未接入）
- news_sentiment_analyst/   新闻与公告 → 新闻情绪分析师（尚未接入）

子目录只表示主要消费方；三条数据流仍由 analysis_context_builder 统一编排，
产出同一份共享上下文。
"""
