"""信源行政区划纠正、网站编码与内部唯一 id。"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable

_DIGITS = re.compile(r"\D")

# 行政区划编码位数：省 2 位、市 4 位、区县 6 位，下级编码以上级编码为前缀。
PROVINCE_CODE_LENGTH = 2
CITY_CODE_LENGTH = 4
DISTRICT_CODE_LENGTH = 6


def digits_only(value: str | None) -> str:
    return _DIGITS.sub("", value or "")


def normalize_region(province_code: str, city_code: str, district_code: str) -> tuple[str, str, str]:
    """纠正并补齐：省 2 位、市 4 位、区 6 位。6 位地市编码视为误填的区县。"""

    province = digits_only(province_code)
    city = digits_only(city_code)
    district = digits_only(district_code)

    if len(city) == DISTRICT_CODE_LENGTH:
        if not district:
            district = city
        city = city[:CITY_CODE_LENGTH]

    if not province:
        source = next((code for code in (district, city) if len(code) >= PROVINCE_CODE_LENGTH), "")
        if not source:
            return "", "", ""
        province = source[:PROVINCE_CODE_LENGTH]
    province = _fit(province, PROVINCE_CODE_LENGTH)
    city = _fit(city, CITY_CODE_LENGTH) if city else _fit(province, CITY_CODE_LENGTH)
    district = _fit(district, DISTRICT_CODE_LENGTH) if district else _fit(city, DISTRICT_CODE_LENGTH)

    return district[:PROVINCE_CODE_LENGTH], district[:CITY_CODE_LENGTH], district


def region_conflict(province_code: str, city_code: str, district_code: str) -> str | None:
    """上下级编码对不上（区县不在这个地市下、地市不在这个省下）时的说明。

    入库时以区县编码为准反推省和市：区县编码是别处残留的话，信源会存成别省的编码，网站编码前缀也跟着错，
    而省份名称还是原来的，页面上看不出来。
    """

    province, city, district = (digits_only(code) for code in (province_code, city_code, district_code))
    if (
        len(city) >= CITY_CODE_LENGTH
        and len(district) >= CITY_CODE_LENGTH
        and district[:CITY_CODE_LENGTH] != city[:CITY_CODE_LENGTH]
    ):
        return f"区县编码 {district_code} 不在地市编码 {city_code} 下面，请核对"
    for code in (city, district):
        if (
            len(province) >= PROVINCE_CODE_LENGTH
            and len(code) >= PROVINCE_CODE_LENGTH
            and code[:PROVINCE_CODE_LENGTH] != province[:PROVINCE_CODE_LENGTH]
        ):
            return f"省份编码 {province_code} 和地市、区县编码不是同一个省，请核对"
    return None


def _fit(code: str, length: int) -> str:
    """右补 0 或截断到固定位数。"""

    return code.ljust(length, "0")[:length]


# 字段之间的分隔符（单元分隔符 U+001F，正常文本里不会出现）。原来直接拼接，("ab","c") 和 ("a","bc") 算出同一个 id，
# 两个不同的信源会被当成重复。库里已有的 id 由迁移 d8e9f0a1b2c5 按同一算法重算（PostgreSQL 的 md5 结果和这里一致）。
_ID_SEPARATOR = "\x1f"


def make_internal_id(site_name: str, province_name: str, city_name: str, tag: str) -> str:
    raw = _ID_SEPARATOR.join((site_name, province_name, city_name, tag))
    return hashlib.md5(raw.encode("utf-8"), usedforsecurity=False).hexdigest()


def make_policy_uid(policy_title: str) -> str:
    return hashlib.md5((policy_title or "").encode("utf-8"), usedforsecurity=False).hexdigest()


def make_relation_key(
    policy_uid: str, industry_scenario_code: str, opportunity_type: str, scenario_names: Iterable[str] = ()
) -> str:
    """政策 + 行业场景编码 + 机会类型。新增场景还没有编码时用六级名称代替（同 AI 写入的规则
    ``aitag.domain.interpret_rules.relation_key``），否则同一条政策的几个新增场景会撞成同一个主键。"""

    names = list(scenario_names)
    code = industry_scenario_code or ("新:" + "/".join(names) if any(names) else "")
    return f"{policy_uid}{code}{opportunity_type}"


def site_code_prefix(province_code: str, city_code: str, district_code: str) -> str:
    """网站编码前缀：有区县用 6 位区县，否则地市+00，再否则省份+0000。"""

    district = digits_only(district_code)
    city = digits_only(city_code)
    province = digits_only(province_code)
    if len(district) >= DISTRICT_CODE_LENGTH:
        return district[:DISTRICT_CODE_LENGTH]
    if len(city) >= CITY_CODE_LENGTH:
        return _fit(city[:CITY_CODE_LENGTH], DISTRICT_CODE_LENGTH)
    if len(province) >= PROVINCE_CODE_LENGTH:
        return _fit(province[:PROVINCE_CODE_LENGTH], DISTRICT_CODE_LENGTH)
    return ""


class SiteCodeAllocator:
    """导入一批时用：已有编码按区县前缀只扫一遍，之后每行 O(1) 取号。
    逐行调 next_site_code 是行数 × 库里编码数次正则，2 万行库 + 2 千行文件要跑几十秒，还占着事件循环。"""

    def __init__(self, existing_codes: Iterable[str]) -> None:
        self._max: dict[str, int] = {}
        for code in existing_codes:
            digits = digits_only(code)
            prefix, seq = digits[:DISTRICT_CODE_LENGTH], digits[DISTRICT_CODE_LENGTH:]
            if len(prefix) == DISTRICT_CODE_LENGTH and seq.isdigit():
                self._max[prefix] = max(self._max.get(prefix, 0), int(seq))

    def allocate(self, district_code: str) -> str:
        prefix = _fit(digits_only(district_code), DISTRICT_CODE_LENGTH)
        self._max[prefix] = self._max.get(prefix, 0) + 1
        return f"{prefix}{self._max[prefix]:05d}"


def next_site_code(district_code: str, existing_codes: Iterable[str]) -> str:
    """同区县取当前网站编码最大序号再 +1。"""

    prefix = _fit(digits_only(district_code), DISTRICT_CODE_LENGTH)
    max_seq = 0
    for code in existing_codes:
        digits = digits_only(code)
        if not digits.startswith(prefix) or len(digits) <= len(prefix):
            continue
        try:
            max_seq = max(max_seq, int(digits[len(prefix) :]))
        except ValueError:
            continue
    return f"{prefix}{max_seq + 1:05d}"
