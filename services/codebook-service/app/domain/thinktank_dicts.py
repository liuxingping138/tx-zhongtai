"""智库专属 6 张码表规格定义与初始种子清单。

智库码表独立于通用数据字典与 AI 提示词系统码表（CODE_TABLES），
统一存放在 codebook_thinktank_dicts 表中按 dict_type 分区维护。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from platform_common.columns import ColumnSpec

SEED_NAMESPACE = uuid.UUID("7a4e2c91-5d3b-4f80-8e12-9b6a1c3d5e77")


def stable_seed_id(dict_type: str, name: str) -> uuid.UUID:
    return uuid.uuid5(SEED_NAMESPACE, f"{dict_type}:{name}")


@dataclass(frozen=True)
class ThinktankDictSpec:
    dict_type: str
    slug: str
    resource: str
    title: str
    label: str
    seed_values: tuple[str, ...]

    @property
    def columns(self) -> tuple[ColumnSpec, ...]:
        return (ColumnSpec("name", self.label, searchable=True),)

    @property
    def import_columns(self) -> tuple[ColumnSpec, ...]:
        return (
            ColumnSpec("name", self.label, searchable=True),
            ColumnSpec("name", "名称"),
        )


THINKTANK_DICT_SPECS: tuple[ThinktankDictSpec, ...] = (
    ThinktankDictSpec(
        dict_type="file_types",
        slug="file-types",
        resource="codebook.thinktank_file_types",
        title="文件类别码表",
        label="文件类别",
        seed_values=(
            "经分",
            "通报",
            "工作会",
            "行业营销指引",
            "工作部署&专项行动",
            "网络规划",
            "考核",
            "产品",
            "政企改革&数字化",
            "客户视图",
            "通知",
            "渠道&生态",
            "国际业务",
            "其他",
        ),
    ),
    ThinktankDictSpec(
        dict_type="departments",
        slug="departments",
        resource="codebook.thinktank_departments",
        title="客户部门归属码表",
        label="客户部门归属",
        seed_values=(
            "政企部",
            "市场部",
            "工业行业事业部",
            "公众客户销售中心",
            "国际部",
            "集团商业客户拓展部",
            "集团政企应急行业事业部",
            "交通物流行业事业部",
            "柯瑞文董事长",
        ),
    ),
    ThinktankDictSpec(
        dict_type="industries",
        slug="industries",
        resource="codebook.thinktank_industries",
        title="行业类别码表",
        label="行业类别",
        seed_values=(
            "党政",
            "工业能源",
            "教育",
            "医卫",
            "交通物流",
            "IT互联网",
            "金融",
            "农业",
            "住建",
            "文旅",
            "中小",
            "无",
        ),
    ),
    ThinktankDictSpec(
        dict_type="product_types",
        slug="product-types",
        resource="codebook.thinktank_product_types",
        title="产品类别码表",
        label="产品类别",
        seed_values=(
            "云",
            "网",
            "数",
            "智",
            "安",
            "语音",
            "消息",
            "数字平台",
            "量子",
            "解决方案",
            "服务",
            "无",
        ),
    ),
    ThinktankDictSpec(
        dict_type="provinces",
        slug="provinces",
        resource="codebook.thinktank_provinces",
        title="省份码表",
        label="省份名称",
        seed_values=(
            "集团",
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
        ),
    ),
    ThinktankDictSpec(
        dict_type="market_categories",
        slug="market-categories",
        resource="codebook.thinktank_market_categories",
        title="市场类别码表",
        label="市场类别",
        seed_values=(
            "行客",
            "商客",
            "综合",
            "无",
        ),
    ),
)

THINKTANK_DICT_BY_TYPE: dict[str, ThinktankDictSpec] = {spec.dict_type: spec for spec in THINKTANK_DICT_SPECS}
THINKTANK_DICT_BY_SLUG: dict[str, ThinktankDictSpec] = {spec.slug: spec for spec in THINKTANK_DICT_SPECS}
