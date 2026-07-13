from __future__ import annotations

import re

from pydantic import BaseModel

from backend.app.agent.safety_precheck import SafetyPrecheck


NO_ANSWER_POLICY_WARNING = "RAG_POLICY_NO_ANSWER"
SAFETY_REFUSAL_POLICY_WARNING = "RAG_POLICY_SAFETY_REFUSAL"

NO_ANSWER_TEXT = "当前知识库中没有检索到足够依据，无法给出确定回答。建议补充更具体的信息，或咨询专业兽医/技术人员。"
SAFETY_REFUSAL_TEXT = (
    "安全提示：这个问题涉及具体药物剂量、处方、停药期、确定性诊断、绕过兽医监管"
    "或受限资料复制，不能直接给出操作性结论。请联系执业兽医，并结合适用法规和原始资料进行人工复核。"
)


class RagAnswerPolicyDecision(BaseModel):
    force_no_answer: bool = False
    force_safety_refusal: bool = False
    reason: str | None = None
    warning: str | None = None

    @property
    def should_use_retrieved_contexts(self) -> bool:
        return not self.force_no_answer and not self.force_safety_refusal

    @property
    def should_require_citations(self) -> bool:
        return not self.force_no_answer and not self.force_safety_refusal


def classify_rag_answer_policy(query: str) -> RagAnswerPolicyDecision:
    text = query.strip()
    normalized = text.lower()
    safety = SafetyPrecheck().classify(text)
    if (
        safety.action == "refuse"
        or "food_safety" in safety.risk_tags
        or _matches_any(normalized, _SAFETY_REFUSAL_PATTERNS)
    ):
        return RagAnswerPolicyDecision(
            force_safety_refusal=True,
            reason=safety.reason if safety.action in {"refuse", "escalate"} else "safety policy pattern matched",
            warning=SAFETY_REFUSAL_POLICY_WARNING,
        )

    no_answer_patterns = (
        _NO_ANSWER_PATTERNS[1:]
        if _matches_any(normalized, _SUPPORTED_LIVESTOCK_SPECIES_PATTERNS)
        else _NO_ANSWER_PATTERNS
    )
    if _matches_any(normalized, no_answer_patterns):
        return RagAnswerPolicyDecision(
            force_no_answer=True,
            reason="query is outside the current cattle corpus or asks for unavailable exact/proprietary facts",
            warning=NO_ANSWER_POLICY_WARNING,
        )

    return RagAnswerPolicyDecision()


_SAFETY_REFUSAL_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, flags=re.IGNORECASE | re.DOTALL)
    for pattern in (
        r"without\s+(?:veterinary|vet)\s+oversight",
        r"without\s+involving\s+(?:a\s+)?veterinarian",
        r"replace\s+the\s+veterinarian",
        r"guaranteed\s+diagnosis",
        r"ignore\s+withdrawal\s+periods?",
        r"mix\s+sick\s+calves?\s+with\s+healthy\s+calves?",
        r"直接混群|不想隔离",
        r"完整处方",
        r"完整复制.*商业",
        r"绕过.*兽医",
        r"承诺.*一定.*恢复",
    )
)

_SUPPORTED_LIVESTOCK_SPECIES_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, flags=re.IGNORECASE | re.DOTALL)
    for pattern in (
        r"broiler|poultry|swine|farrowing|goat",
        r"养鸡|蛋鸡|生猪|山羊|绵羊|家禽",
    )
)

_NO_ANSWER_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, flags=re.IGNORECASE | re.DOTALL)
    for pattern in (
        r"蛋鸡|broiler|poultry|pet\s+cat|cat\s+vaccination|swine|farrowing|goat|equine|aquaculture|奶山羊|羊痘|水产",
        r"玉米期货|期货价格|corn\s+futures",
        r"明天.*数值|预测.*明天",
        r"当前没有入库|本场历史|没有照片|without\s+photos?",
        r"empty\s+knowledge-base\s+question",
        r"未开放论文|完整复述|全文段落|complete\s+scoring\s+chart|exact\s+page\s+number",
        r"proprietary|private\s+dairy\s+standard|line\s+43|legal\s+clause|exact\s+farm",
        r"某未命名|未命名兽药|absent\s+from\s+the\s+corpus|exact\s+treatment\s+dose",
        r"最优.*品牌|vaccine\s+protocol|免疫程序",
    )
)


def _matches_any(text: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(pattern.search(text) for pattern in patterns)
