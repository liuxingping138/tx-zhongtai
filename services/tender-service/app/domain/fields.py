"""展示字段.xlsx 的字段白名单；业务表名不接受客户端输入。"""

from typing import Literal

Kind = Literal["purchaser", "winbid"]
Status = Literal["0", "1"]
TABLES: dict[tuple[Kind, Status], str] = {
    ("purchaser", "0"): "bid_purchaser_info_dis_pro",
    ("purchaser", "1"): "bid_purchaser_info_dis_approval_pro",
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
        ("winbid", "accepted_amount", "bid_type") if kind == "winbid" else ("open_date", "end_date")
    )
