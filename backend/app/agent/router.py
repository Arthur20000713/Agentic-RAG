from __future__ import annotations

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
    livestock_keywords = {
        "cattle",
        "calf",
        "cow",
        "yak",
        "livestock",
        "feeding",
        "feed",
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

    def route(self, query: str) -> RouteResult:
        if self._contains_any(query, self.out_of_scope_keywords) and not self._contains_any(query, self.livestock_keywords):
            return RouteResult(intent="out_of_scope", confidence=0.9, reason="query is outside livestock domain")
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
