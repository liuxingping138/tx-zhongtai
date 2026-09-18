"""信源行政区划纠正、网站编码与内部唯一 id。"""

from __future__ import annotations

import hashlib
import re

_DIGITS = re.compile(r"\D")


def digits_only(value: str | None) -> str:
    return _DIGITS.sub("", value or "")


def normalize_region(province_code: str, city_code: str, district_code: str) -> tuple[str, str, str]:
    """纠正并补齐：省 2 位、市 4 位、区 6 位。6 位地市编码视为误填的区县。"""

    province = digits_only(province_code)
    city = digits_only(city_code)
    district = digits_only(district_code)

    if not district and len(city) == 6:
        district = city
        city = city[:4]
        if not province:
            province = district[:2]
    elif len(city) == 6:
        city = city[:4]

    if not province:
        if len(district) >= 2:
            province = district[:2]
        elif len(city) >= 2:
            province = city[:2]
        else:
            province = "00"
    province = (province + "00")[:2]

    if not city:
        city = province + "00"
    elif len(city) < 4:
        city = (city + "0000")[:4]
    else:
        city = city[:4]

    if not district:
        district = city + "00"
    elif len(district) < 6:
        district = (district + "000000")[:6]
    else:
        district = district[:6]

    return district[:2], district[:4], district


def make_internal_id(site_name: str, province_name: str, city_name: str, tag: str) -> str:
    raw = f"{site_name}{province_name}{city_name}{tag}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def make_policy_uid(policy_title: str) -> str:
    return hashlib.md5((policy_title or "").encode("utf-8")).hexdigest()


def make_relation_key(policy_uid: str, industry_scenario_code: str, opportunity_type: str) -> str:
    return f"{policy_uid}{industry_scenario_code}{opportunity_type}"


def next_site_code(district_code: str, existing_codes: list[str]) -> str:
    prefix = district_code
    max_seq = 0
    for code in existing_codes:
        digits = digits_only(code)
        if len(digits) == 11 and digits.startswith(prefix):
            try:
                max_seq = max(max_seq, int(digits[6:]))
            except ValueError:
                continue
    return f"{prefix}{max_seq + 1:05d}"
