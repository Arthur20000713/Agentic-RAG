from __future__ import annotations

import re

from pydantic import BaseModel

from backend.app.schemas.agent import IntentType


class RouteResult(BaseModel):
    intent: IntentType
    confidence: float
    reason: str = ""


class IntentRouter:
    disease_keywords = {
        "diarrhea",
        "fever",
        "temperature",
        "cough",
        "respiratory",
        "sick",
        "illness",
        "symptom",
        "health problem",
        "abnormal",
        "condition",
        "disease consultation",
        "腹泻",
        "拉稀",
        "发烧",
        "体温",
        "精神差",
        "不吃",
        "采食下降",
        "咳嗽",
        "呼吸困难",
        "发病",
    }
    measurement_keywords = {
        "body measurement",
        "body height",
        "body length",
        "chest girth",
        "chest depth",
        "chest width",
        "weight",
        "体尺",
        "体高",
        "体长",
        "胸围",
        "胸深",
        "胸宽",
        "体重",
    }
    general_context_keywords = {
        "record",
        "document",
        "documented",
        "observation",
        "observations",
        "management",
        "managed",
        "weaning",
        "evidence",
        "discussed",
        "knowledge-base",
    }
    livestock_keywords = {
        "cattle",
        "calf",
        "cow",
        "yak",
        "livestock",
        "feeding",
        "feed",
        "weaning",
        "farm",
        "牛",
        "犊牛",
        "牦牛",
        "羊",
        "猪",
        "饲养",
        "养殖",
        "饲料",
        "断奶",
        "牧场",
        "畜牧",
    }
    out_of_scope_keywords = {
        "stock",
        "trading",
        "fund",
        "code",
        "travel",
        "movie",
        "股票",
        "交易",
        "基金",
        "代码",
        "旅游",
        "电影",
    }
    assistant_intro_exact_queries = {
        "hi",
        "hello",
        "hey",
        "你好",
        "您好",
        "你好啊",
        "您好啊",
        "早上好",
        "下午好",
        "晚上好",
    }
    assistant_intro_keywords = {
        "who are you",
        "what are you",
        "what can you do",
        "tell me about yourself",
        "introduce yourself",
        "你是谁",
        "你是什么",
        "介绍一下自己",
        "自我介绍",
        "你能做什么",
        "你可以做什么",
        "你会做什么",
    }

    def route(self, query: str) -> RouteResult:
        if self._contains_any(query, self.out_of_scope_keywords) and not self._contains_any(query, self.livestock_keywords):
            return RouteResult(intent="out_of_scope", confidence=0.9, reason="query is outside livestock domain")
        if self._is_assistant_intro_query(query):
            return RouteResult(intent="assistant_intro", confidence=0.88, reason="assistant greeting or self-introduction")
        if self._is_general_context_query(query):
            return RouteResult(intent="general_qa", confidence=0.78, reason="general livestock management context matched")
        if self._contains_any(query, self.disease_keywords):
            return RouteResult(intent="disease_consultation", confidence=0.86, reason="disease symptom keyword matched")
        if self._contains_any(query, self.measurement_keywords):
            return RouteResult(intent="measurement_analysis", confidence=0.84, reason="measurement keyword matched")
        if self._contains_any(query, self.livestock_keywords):
            return RouteResult(intent="general_qa", confidence=0.72, reason="livestock domain keyword matched")
        return RouteResult(intent="out_of_scope", confidence=0.7, reason="no livestock domain signal")

    def _contains_any(self, text: str, keywords: set[str]) -> bool:
        normalized = text.lower()
        return any(keyword.lower() in normalized for keyword in keywords)

    def _is_general_context_query(self, query: str) -> bool:
        if not self._contains_any(query, self.general_context_keywords):
            return False
        if "knowledge-base" in query.lower():
            return True
        return self._contains_any(query, self.livestock_keywords) and self._contains_any(query, self.disease_keywords)

    def _is_assistant_intro_query(self, query: str) -> bool:
        normalized = re.sub(r"[\s,，.。!！?？~～]+", "", query.lower())
        if normalized in self.assistant_intro_exact_queries:
            return True
        return self._contains_any(query, self.assistant_intro_keywords)
