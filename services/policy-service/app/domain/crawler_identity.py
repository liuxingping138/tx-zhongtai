"""按网站名称关联爬虫数据，编码只在缺少名称时兜底。"""

from __future__ import annotations

import hashlib


def site_key(site_code: str, site_name: str, _province_name: str = "", _city_name: str = "") -> str:
    name = site_name.strip(" ")
    if name:
        return "name:" + hashlib.md5(name.encode(), usedforsecurity=False).hexdigest()
    return "code:" + site_code.strip(" ")
