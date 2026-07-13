from __future__ import annotations

from backend.app.agent.router import IntentRouter


def test_router_detects_disease_consultation() -> None:
    result = IntentRouter().route("犊牛腹泻两天，精神差，怎么办？")

    assert result.intent == "disease_consultation"
    assert result.confidence >= 0.8


def test_router_detects_real_chinese_livestock_disease_queries() -> None:
    router = IntentRouter()

    assert router.route("牛拉稀了怎么办？").intent == "disease_consultation"
    assert router.route("犊牛腹泻两天，体温40.2度，精神差，不吃草，没有群体发病").intent == "disease_consultation"
    assert router.route("羊咳嗽一天，体温正常").intent == "disease_consultation"


def test_router_detects_measurement_analysis() -> None:
    result = IntentRouter().route("牦牛体高 114 cm，胸围 158 cm，帮我分析体尺")

    assert result.intent == "measurement_analysis"


def test_router_detects_general_qa() -> None:
    result = IntentRouter().route("犊牛断奶后应该怎么饲养管理？")

    assert result.intent == "general_qa"


def test_router_detects_out_of_scope() -> None:
    result = IntentRouter().route("帮我写一个股票交易策略")

    assert result.intent == "out_of_scope"


def test_router_treats_poultry_questions_as_livestock_qa() -> None:
    router = IntentRouter()

    assert router.route("夏季养鸡需要注意什么？").intent == "general_qa"
    assert router.route("How should poultry be managed in summer?").intent == "general_qa"
    assert router.route("What should heifer management focus on?").intent == "general_qa"
    assert router.route("How should sheep and goats be housed?").intent == "general_qa"


def test_router_detects_assistant_intro_without_livestock_signal() -> None:
    router = IntentRouter()

    assert router.route("你好").intent == "assistant_intro"
    assert router.route("你是谁？").intent == "assistant_intro"
    assert router.route("What can you do?").intent == "assistant_intro"


def test_router_keeps_substantive_out_of_scope_when_greeting_is_prefixed() -> None:
    result = IntentRouter().route("你好，帮我写一个股票交易策略")

    assert result.intent == "out_of_scope"


def test_router_detects_english_livestock_intents() -> None:
    router = IntentRouter()

    assert router.route("Calf diarrhea and fever for two days").intent == "disease_consultation"
    assert router.route("calf has a health problem").intent == "disease_consultation"
    assert router.route("Analyze cattle body height and chest girth").intent == "measurement_analysis"
    assert router.route("How should calf feeding be managed after weaning?").intent == "general_qa"
    assert router.route("How should a farm record calf diarrhea observations?").intent == "general_qa"
    assert router.route("empty knowledge-base question 1").intent == "general_qa"
    assert router.route("Write a stock trading strategy").intent == "out_of_scope"


def test_router_avoids_livestock_false_positives_in_ordinary_topics() -> None:
    router = IntentRouter()

    assert router.route("我今天在牛市买了股票，聊聊投资风险。").intent == "out_of_scope"
    assert router.route("What is the temperature in Beijing today?").intent == "out_of_scope"
    assert router.route("I want to lose weight, any tips?").intent == "out_of_scope"
    assert router.route("我的电脑发烧了，讲个笑话吧").intent == "out_of_scope"


def test_router_prioritizes_livestock_part_of_mixed_intro_queries() -> None:
    router = IntentRouter()

    assert router.route("Who are you, and how should I manage calf weaning?").intent == "general_qa"
    assert router.route("你是谁？顺便说说犊牛腹泻怎么办").intent == "disease_consultation"


def test_router_keeps_environmental_temperature_management_in_general_qa() -> None:
    result = IntentRouter().route("What should calf care emphasize during cold temperature conditions?")

    assert result.intent == "general_qa"
