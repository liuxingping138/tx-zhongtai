"""图表用的省份归并。只影响图表分组，网站身份、表格和筛选仍用爬虫库里的原始省份值。"""

from __future__ import annotations

PROVINCES = (
    "北京市",
    "天津市",
    "河北省",
    "山西省",
    "内蒙古自治区",
    "辽宁省",
    "吉林省",
    "黑龙江省",
    "上海市",
    "江苏省",
    "浙江省",
    "安徽省",
    "福建省",
    "江西省",
    "山东省",
    "河南省",
    "湖北省",
    "湖南省",
    "广东省",
    "广西壮族自治区",
    "海南省",
    "重庆市",
    "四川省",
    "贵州省",
    "云南省",
    "西藏自治区",
    "陕西省",
    "甘肃省",
    "青海省",
    "宁夏回族自治区",
    "新疆维吾尔自治区",
)
# 「内蒙古」「黑龙江」要三个字才不歧义，其余取前两个字已能唯一区分（山西/山东、广东/广西等都不同）。
# 图表按「省份」字段的分类展示，不是一份只含行政区的名单：上面 31 个省级行政区都在列，不含港澳台；
# 「全国」「国央企」等字段里的其他分类原样保留，同样进图。
FIELD_CATEGORIES = ("全国", "国央企")
_PREFIXES = tuple((name[:3] if name.startswith(("内蒙古", "黑龙江")) else name[:2], name) for name in PROVINCES)
# 爬虫库里省份为空的网站都是国央企（2026-10-21 用户确认）：同步时就写成「国央企」，表格、筛选、图表一致。
EMPTY_PROVINCE_CATEGORY = "国央企"


def chart_province(raw: str) -> str:
    """「新疆维吾尔族自治区」「新疆」都归到「新疆维吾尔自治区」；「全国」「国央企」这类非省份值原样保留。"""

    value = raw.strip()
    if not value:
        return EMPTY_PROVINCE_CATEGORY
    for prefix, name in _PREFIXES:
        if value.startswith(prefix):
            return name
    return value
