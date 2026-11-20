"""大模型的调用参数与计费规则。模型清单存在 ai_models 表里，在「模型配置」页维护，这里只有规则。

价格单位：输入/输出 元每千 token，联网 元每次。
推理费用 = 未命中缓存的输入token/1000×输入价 + 命中缓存的输入token/1000×缓存价 + 输出token/1000×输出价；
联网费用 = 联网次数 × 联网价。
输入/输出价按调用时刻选：低优档用低优价；配了高峰价的，工作日高峰时段用高峰价；其余用常规价。
缓存价不分常规、低优档：配了高峰缓存价的工作日高峰时段用它，其余用缓存价；没配缓存价的按此刻的输入价算，
和没有缓存计价之前算出来的钱一样。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime, time
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from platform_common.clock import BEIJING

ARK_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
BAIDU_BASE_URL = "https://qianfan.baidubce.com/v2"
PROVIDERS = {"ark": "字节方舟", "baidu": "百度千帆"}
# 服务档位：auto 常规、flex 低优（价格低、不保证速度）；空串表示不传，部分接入点不认这个参数。
SERVICE_TIERS = ("auto", "flex")
# 深度思考：enabled/disabled 固定传；switch 由提问时的开关决定（千帆默认开启，不开时必须显式关掉）；空串不传。
THINKING_MODES = ("enabled", "disabled", "switch")
REASONING_EFFORTS = ("low", "high", "max")
DEFAULT_PEAK_HOURS = "09:00-12:00,14:00-18:00"
_SATURDAY = 5
_COST_QUANT = Decimal("0.000001")
_THOUSAND = Decimal(1000)
_HOURS, _MINUTES = 24, 60
_PEAK_RANGE = re.compile(r"(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})")


@dataclass(frozen=True)
class LlmModel:
    id: str
    name: str
    provider: str  # "ark" | "baidu"
    model: str  # 厂商侧的模型名或接入点 ID
    web_search: bool
    thinking: str
    reasoning_effort: str
    service_tier: str
    input_price: Decimal
    output_price: Decimal
    flex_input_price: Decimal | None = None
    flex_output_price: Decimal | None = None
    peak_input_price: Decimal | None = None
    peak_output_price: Decimal | None = None
    peak_hours: str = ""
    search_price: Decimal = Decimal(0)
    cache_price: Decimal | None = None
    peak_cache_price: Decimal | None = None

    @property
    def provider_name(self) -> str:
        return PROVIDERS.get(self.provider, self.provider)

    @property
    def base_url(self) -> str:
        return ARK_BASE_URL if self.provider == "ark" else BAIDU_BASE_URL

    @property
    def supports_thinking(self) -> bool:
        """提问时能不能自己选开不开思考。"""

        return self.thinking == "switch"

    def prices_at(self, when: datetime) -> tuple[Decimal, Decimal]:
        if self.service_tier == "flex" and self.flex_input_price is not None and self.flex_output_price is not None:
            return self.flex_input_price, self.flex_output_price
        if self.peak_input_price is not None and self.peak_output_price is not None and in_peak(when, self.peak_hours):
            return self.peak_input_price, self.peak_output_price
        return self.input_price, self.output_price

    def cache_price_at(self, when: datetime) -> Decimal:
        """命中上下文缓存的输入按什么价算。没配缓存价的模型按此刻的输入价，费用和以前一样。"""

        if self.peak_cache_price is not None and in_peak(when, self.peak_hours):
            return self.peak_cache_price
        if self.cache_price is not None:
            return self.cache_price
        return self.prices_at(when)[0]

    def price_note(self, when: datetime) -> str:
        """prices_at 给的是哪一档：页面价格旁边写清，免得同一个模型上午下午看到的价不一样，以为价格乱跳。"""

        if self.service_tier == "flex" and self.flex_input_price is not None and self.flex_output_price is not None:
            return "低优档"
        peak_io = self.peak_input_price is not None and self.peak_output_price is not None
        if not peak_io and self.peak_cache_price is None:
            return ""
        hours = (self.peak_hours or DEFAULT_PEAK_HOURS).replace(",", "、")
        return f"高峰价（工作日 {hours}）" if in_peak(when, self.peak_hours) else f"平时价（工作日 {hours} 涨价）"


def parse_peak_hours(text: str) -> list[tuple[time, time]]:
    """「09:00-12:00,14:00-18:00」→ 时段列表。格式不对抛 ValueError，由调用方转成中文提示。"""

    ranges: list[tuple[time, time]] = []
    for part in re.split(r"[,，;；\s]+", text.strip()):
        if not part:
            continue
        match = _PEAK_RANGE.fullmatch(part)
        if match is None:
            raise ValueError(part)
        start_h, start_m, end_h, end_m = (int(value) for value in match.groups())
        start, end = _clock(start_h, start_m), _clock(end_h, end_m, end=True)
        if start is None or end is None or start >= end:
            raise ValueError(part)
        ranges.append((start, end))
    return ranges


def _clock(hour: int, minute: int, *, end: bool = False) -> time | None:
    """时刻不合法返回 None。结束时刻可以写 24:00，表示到当天结束（time 本身只到 23 点，会抛英文的错）。"""

    if end and (hour, minute) == (_HOURS, 0):
        return time.max
    if hour >= _HOURS or minute >= _MINUTES:
        return None
    return time(hour, minute)


def in_peak(when: datetime, peak_hours: str) -> bool:
    """北京时间周一到周五落在高峰时段内。不认节假日和调休：节假日按工作日算，费用只会偏高不会偏低。"""

    local = when.astimezone(BEIJING)
    if local.weekday() >= _SATURDAY:
        return False
    try:
        ranges = parse_peak_hours(peak_hours or DEFAULT_PEAK_HOURS)
    except ValueError:
        ranges = parse_peak_hours(DEFAULT_PEAK_HOURS)
    moment = local.time()
    return any(start <= moment < end for start, end in ranges)


def with_service_tier(model: LlmModel, tier: str) -> LlmModel:
    """任务指定了档位（定时任务用低优档）时覆盖模型默认档位。

    只在接入点本来就传档位参数、且配了对应单价时才换：不认这个参数的接入点传了会报错，没配低优价就算不准钱。
    """

    if tier != "flex" or not model.service_tier or model.flex_input_price is None or model.flex_output_price is None:
        return model
    return replace(model, service_tier=tier)


def build_body(model: LlmModel, message: str, *, thinking: bool = False) -> dict[str, Any]:
    body: dict[str, Any] = {"model": model.model, "input": [{"role": "user", "content": message}], "stream": True}
    if model.service_tier:
        body["service_tier"] = model.service_tier
    if model.web_search:
        body["tools"] = [{"type": "web_search", "max_keyword": 3}]
    if model.thinking == "switch":
        body["thinking"] = {"type": "enabled" if thinking else "disabled"}
    elif model.thinking:
        body["thinking"] = {"type": model.thinking}
    if model.reasoning_effort:
        body["reasoning"] = {"effort": model.reasoning_effort}
    return body


def calc_costs(
    model: LlmModel,
    input_tokens: int,
    output_tokens: int,
    search_calls: int,
    when: datetime,
    cached_tokens: int = 0,
) -> tuple[Decimal, Decimal]:
    """(推理费用, 联网费用)，单位元，保留 6 位。cached_tokens 是输入里命中缓存的部分，夹在 0 到输入数之间。"""

    input_price, output_price = model.prices_at(when)
    cached = min(max(cached_tokens, 0), max(input_tokens, 0))
    uncached = max(input_tokens - cached, 0)
    inference = (
        Decimal(uncached) / _THOUSAND * input_price
        + Decimal(cached) / _THOUSAND * model.cache_price_at(when)
        + Decimal(output_tokens) / _THOUSAND * output_price
    ).quantize(_COST_QUANT, rounding=ROUND_HALF_UP)
    search = (Decimal(search_calls) * model.search_price).quantize(_COST_QUANT, rounding=ROUND_HALF_UP)
    return inference, search
