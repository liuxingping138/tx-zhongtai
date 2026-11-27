"""IP 与网段的解析、匹配规则。纯函数，不碰数据库。"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable
from functools import lru_cache

Network = ipaddress.IPv4Network | ipaddress.IPv6Network
Address = ipaddress.IPv4Address | ipaddress.IPv6Address

# 白名单网段最宽只到这里：再宽就等于对一大片公网放行（同一运营商的其他用户也能进），白名单就没意义了。
MIN_IPV4_PREFIX = 24
MIN_IPV6_PREFIX = 64


class InvalidNetworkError(ValueError):
    """管理员填的 IP / 网段不合格，message 直接给页面看。"""


def parse_address(raw: str) -> Address | None:
    """请求来源 IP。解析不了（如单测的 testclient）返回 None，按不在任何网络里处理。"""

    try:
        addr = ipaddress.ip_address(raw.strip())
    except ValueError:
        return None
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        return addr.ipv4_mapped
    return addr


def parse_network(raw: str) -> Network:
    """管理员填的白名单：单个 IP 或网段（1.2.3.0/24）。"""

    text = raw.strip()
    if not text:
        raise InvalidNetworkError("请填写 IP 地址")
    try:
        net = ipaddress.ip_network(text, strict=False)
    except ValueError as exc:
        raise InvalidNetworkError(f"「{text}」不是有效的 IP 地址或网段") from exc
    min_prefix = MIN_IPV4_PREFIX if isinstance(net, ipaddress.IPv4Network) else MIN_IPV6_PREFIX
    if net.prefixlen < min_prefix:
        raise InvalidNetworkError(f"网段最宽只能到 /{min_prefix}，请填写具体的 IP")
    return net


def normalize_network(raw: str) -> str:
    """存库的统一写法：单个地址不带掩码，网段写成网络号/掩码。"""

    net = parse_network(raw)
    return str(net.network_address) if net.num_addresses == 1 else str(net)


@lru_cache(maxsize=8)
def _office_networks(items: tuple[str, ...]) -> tuple[Network, ...]:
    return tuple(ipaddress.ip_network(item, strict=False) for item in items)


def office_networks(items: Iterable[str]) -> tuple[Network, ...]:
    """公司出口 IP（配置项，启动时已校验过格式）。"""

    return _office_networks(tuple(items))


def contains(networks: Iterable[Network], addr: Address) -> bool:
    return any(addr.version == net.version and addr in net for net in networks)


def range_contains(ip_range: str, addr: Address) -> bool:
    """库里存的一条白名单是否覆盖这个地址；历史脏数据解析不了就当不覆盖。"""

    try:
        net = ipaddress.ip_network(ip_range, strict=False)
    except ValueError:
        return False
    return addr.version == net.version and addr in net
