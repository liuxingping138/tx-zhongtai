"""展示字段.xlsx 的字段白名单；业务表名不接受客户端输入。"""

from typing import Literal

from platform_common.columns import ColumnSpec

Kind = Literal["purchaser", "winbid"]
Status = Literal["", "all", "0", "1"]
TABLES: dict[tuple[Kind, Status], str] = {
    ("purchaser", ""): "bid_purchaser_info_dis_pro",
    ("purchaser", "all"): "bid_purchaser_info_dis_pro",
    ("purchaser", "0"): "bid_purchaser_info_dis_pro",
    ("purchaser", "1"): "bid_purchaser_info_dis_approval_pro",
    ("winbid", ""): "bid_winbid_info_dis_pro",
    ("winbid", "all"): "bid_winbid_info_dis_pro",
    ("winbid", "0"): "bid_winbid_info_dis_pro",
    ("winbid", "1"): "bid_winbid_info_dis_approval_pro",
}
COMMON_FIELDS = (
    "id",
    "project_content_id",
    "project_name",
    "project_code",
    "purchaser_provname",
    "purchaser_cityname",
    "purchaser_countyname",
    "purchaser",
    "purchaser_address",
    "agency",
    "public_date",
    "from_url",
    "first_indty_name",
    "second_indty_name",
    "third_indty_name",
    "first_scene_name",
    "second_scene_name",
    "third_scene_name",
    "project_status",
    "is_supp_scene",
    "collect_date",
    "create_time",
)
REGION_FIELDS = ("purchaser_provname", "purchaser_cityname", "purchaser_countyname")


def columns(kind: Kind) -> tuple[str, ...]:
    return COMMON_FIELDS + (
        ("winbid", "accepted_amount", "bid_type") if kind == "winbid" else ("open_date", "end_date", "budget_fund")
    )


_COMMON_HEAD_SPECS: tuple[ColumnSpec, ...] = (
    ColumnSpec("project_name", "项目名称"),
    ColumnSpec("purchaser_provname", "招标单位省份"),
    ColumnSpec("purchaser_cityname", "招标单位市"),
    ColumnSpec("purchaser_countyname", "招标单位区县"),
    ColumnSpec("purchaser", "招标单位名称"),
    ColumnSpec("purchaser_address", "招标公司地址"),
    ColumnSpec("agency", "代理机构"),
)
_COMMON_TAIL_SPECS: tuple[ColumnSpec, ...] = (
    ColumnSpec("public_date", "发布时间"),
    ColumnSpec("from_url", "发布链接"),
    ColumnSpec("first_indty_name", "一级行业名称"),
    ColumnSpec("second_indty_name", "二级行业名称"),
    ColumnSpec("third_indty_name", "三级行业名称"),
    ColumnSpec("first_scene_name", "一级场景"),
    ColumnSpec("second_scene_name", "二级场景"),
    ColumnSpec("third_scene_name", "三级场景"),
    ColumnSpec("project_status", "项目状态"),
    ColumnSpec("is_supp_scene", "是否补充场景"),
    ColumnSpec("project_code", "项目编号"),
    ColumnSpec("project_content_id", "项目ID"),
    ColumnSpec("collect_date", "采集时间"),
    ColumnSpec("create_time", "入库时间"),
)
_SPECIFIC_SPECS: dict[Kind, tuple[ColumnSpec, ...]] = {
    "purchaser": (
        ColumnSpec("budget_fund", "预算金额（万元）"),
        ColumnSpec("open_date", "开标时间"),
        ColumnSpec("end_date", "结束时间"),
    ),
    "winbid": (
        ColumnSpec("winbid", "中标单位名称"),
        ColumnSpec("accepted_amount", "中标金额（万元）"),
        ColumnSpec("bid_type", "招标方式"),
    ),
}


def export_columns(kind: Kind) -> tuple[ColumnSpec, ...]:
    return _COMMON_HEAD_SPECS + _SPECIFIC_SPECS[kind] + _COMMON_TAIL_SPECS
