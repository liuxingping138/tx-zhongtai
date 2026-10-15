"""可选的大模型清单与单价。新增模型或调价只改这一处。

价格单位：输入/输出 元每千 token，联网 元每次。
推理费用 = 输入token/1000×输入价 + 输出token/1000×输出价；联网费用 = 联网次数 × 联网价。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
BAIDU_BASE_URL = "https://qianfan.baidubce.com/v2"
_COST_QUANT = Decimal("0.000001")
_THOUSAND = Decimal(1000)


@dataclass(frozen=True)
class LlmModel:
    id: str
    name: str
    provider: str  # "ark" | "baidu"
    model: str  # 厂商侧的模型名或接入点 ID
    web_search: bool
    supports_thinking: bool
    input_price: Decimal
    output_price: Decimal
    search_price: Decimal = Decimal(0)
    # 原样并进请求体的固定参数（服务档位、思考强度等）
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def provider_name(self) -> str:
        return "字节方舟" if self.provider == "ark" else "百度千帆"

    @property
    def base_url(self) -> str:
        return ARK_BASE_URL if self.provider == "ark" else BAIDU_BASE_URL


_ARK_FLASH = "ep-20260915173105-gv9tb"
# 方舟 Flash 按低优档计价：输入 0.0015、输出 0.0045 元/千 token，联网 0.004 元/次。
_ARK_COMMON: dict[str, Any] = {
    "service_tier": "auto",
    "thinking": {"type": "enabled"},
    "reasoning": {"effort": "low"},
}

MODELS: tuple[LlmModel, ...] = (
    LlmModel(
        id="deepseek-v4-flash",
        name="字节-DeepSeek-V4-Flash（联网）",
        provider="ark",
        model=_ARK_FLASH,
        web_search=True,
        supports_thinking=False,
        input_price=Decimal("0.0015"),
        output_price=Decimal("0.0045"),
        search_price=Decimal("0.004"),
        extra={**_ARK_COMMON, "tools": [{"type": "web_search", "max_keyword": 3}]},
    ),
    LlmModel(
        id="deepseek-v4-flash-nw",
        name="字节-DeepSeek-V4-Flash（不联网）",
        provider="ark",
        model=_ARK_FLASH,
        web_search=False,
        supports_thinking=False,
        input_price=Decimal("0.0015"),
        output_price=Decimal("0.0045"),
        extra=dict(_ARK_COMMON),
    ),
    LlmModel(
        id="baidu-deepseek-v3.2",
        name="百度-DeepSeek-V3.2",
        provider="baidu",
        model="deepseek-v3.2",
        web_search=False,
        supports_thinking=True,
        input_price=Decimal("0.001"),
        output_price=Decimal("0.005"),
    ),
    LlmModel(
        id="baidu-deepseek-v4-flash",
        name="百度-DeepSeek-V4-Flash",
        provider="baidu",
        model="deepseek-v4-flash",
        web_search=False,
        supports_thinking=True,
        input_price=Decimal("0.001"),
        output_price=Decimal("0.005"),
    ),
)

MODEL_BY_ID = {model.id: model for model in MODELS}


def find_model(model_id: str) -> LlmModel | None:
    return MODEL_BY_ID.get(model_id)


def model_display_name(model_id: str) -> str:
    model = find_model(model_id)
    return model.name if model else model_id


def build_body(
    model: LlmModel, message: str, *, previous_response_id: str | None = None, thinking: bool = False
) -> dict[str, Any]:
    body: dict[str, Any] = {"model": model.model, "input": [{"role": "user", "content": message}], "stream": True}
    body.update(model.extra)
    if model.supports_thinking:
        # 千帆 Responses 默认开启思考，不开的时候必须显式关掉。
        body["thinking"] = {"type": "enabled" if thinking else "disabled"}
    if previous_response_id:
        body["previous_response_id"] = previous_response_id
    return body


def calc_costs(model_id: str, input_tokens: int, output_tokens: int, search_calls: int) -> tuple[Decimal, Decimal]:
    """(推理费用, 联网费用)，单位元，保留 6 位。未登记的模型按 0 计，不猜价格。"""

    model = find_model(model_id)
    if model is None:
        return Decimal(0), Decimal(0)
    inference = (
        Decimal(input_tokens) / _THOUSAND * model.input_price + Decimal(output_tokens) / _THOUSAND * model.output_price
    ).quantize(_COST_QUANT, rounding=ROUND_HALF_UP)
    search = (Decimal(search_calls) * model.search_price).quantize(_COST_QUANT, rounding=ROUND_HALF_UP)
    return inference, search
