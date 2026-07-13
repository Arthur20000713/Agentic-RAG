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
        "body temperature",
        "cough",
        "respiratory",
        "sick",
        "illness",
        "symptom",
        "health problem",
        "abnormal",
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
        "heifer",
        "bull",
        "steer",
        "bovine",
        "yak",
        "livestock",
        "sheep",
        "lamb",
        "goat",
        "swine",
        "pig",
        "sow",
        "chicken",
        "poultry",
        "broiler",
        "layer hen",
        "duck",
        "goose",
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
        "鸡",
        "养鸡",
        "家禽",
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
    strong_out_of_scope_keywords = {
        "stock",
        "trading",
        "investment",
        "fund",
        "股票",
        "交易",
        "投资",
        "基金",
        "牛市",
    }
    measurement_action_keywords = {
        "analyze",
        "analysis",
        "measure",
        "measurement",
        "calculate",
        "report",
        "cm",
        "kg",
        "分析",
        "测量",
        "报告",
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
        has_livestock = self._contains_any(query, self.livestock_keywords)
        has_disease = self._contains_any(query, self.disease_keywords)
        if self._contains_any(query, self.strong_out_of_scope_keywords):
            return RouteResult(intent="out_of_scope", confidence=0.9, reason="query is outside livestock domain")
        if self._contains_any(query, self.out_of_scope_keywords) and not has_livestock:
            return RouteResult(intent="out_of_scope", confidence=0.9, reason="query is outside livestock domain")
        if self._is_general_context_query(query):
            return RouteResult(intent="general_qa", confidence=0.78, reason="general livestock management context matched")
        if self._is_measurement_query(query, has_livestock=has_livestock):
            return RouteResult(intent="measurement_analysis", confidence=0.84, reason="livestock measurement request matched")
        if has_livestock and has_disease:
            return RouteResult(intent="disease_consultation", confidence=0.86, reason="disease symptom keyword matched")
        if has_livestock:
            return RouteResult(intent="general_qa", confidence=0.72, reason="livestock domain keyword matched")
        if self._is_assistant_intro_query(query):
            return RouteResult(intent="assistant_intro", confidence=0.88, reason="assistant greeting or self-introduction")
        return RouteResult(intent="out_of_scope", confidence=0.7, reason="no livestock domain signal")

    def _contains_any(self, text: str, keywords: set[str]) -> bool:
        normalized = text.lower()
        for keyword in keywords:
            normalized_keyword = keyword.lower()
            if normalized_keyword.isascii():
                pattern = rf"(?<![a-z0-9]){re.escape(normalized_keyword)}(?![a-z0-9])"
                if re.search(pattern, normalized):
                    return True
            elif normalized_keyword in normalized:
                return True
        return False

    def _is_measurement_query(self, query: str, *, has_livestock: bool) -> bool:
        if not has_livestock or not self._contains_any(query, self.measurement_keywords):
            return False
        return bool(re.search(r"\d", query)) or self._contains_any(query, self.measurement_action_keywords)

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
