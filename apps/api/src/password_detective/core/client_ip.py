from __future__ import annotations

from collections.abc import Iterable
from ipaddress import IPv4Address, IPv4Network, IPv6Address, IPv6Network, ip_address, ip_network

from starlette.requests import Request

IpAddress = IPv4Address | IPv6Address
IpNetwork = IPv4Network | IPv6Network


def normalize_network_cidrs(values: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        candidate = value.strip()
        if not candidate:
            continue
        network = ip_network(candidate, strict=False)
        canonical = network.with_prefixlen
        if canonical not in seen:
            normalized.append(canonical)
            seen.add(canonical)
    return normalized


def parse_network_cidrs(values: Iterable[str]) -> tuple[IpNetwork, ...]:
    return tuple(ip_network(value, strict=False) for value in normalize_network_cidrs(values))


def parse_network_csv(value: str) -> tuple[IpNetwork, ...]:
    return parse_network_cidrs(value.split(","))


def _parse_address(value: str | None) -> IpAddress | None:
    if not value:
        return None
    candidate = value.strip().strip("[]")
    if "%" in candidate:
        candidate = candidate.split("%", 1)[0]
    try:
        return ip_address(candidate)
    except ValueError:
        return None


def address_in_networks(address: IpAddress, networks: Iterable[IpNetwork]) -> bool:
    return any(address.version == network.version and address in network for network in networks)


def resolve_client_ip(request: Request, *, trusted_proxy_cidrs: str) -> IpAddress | None:
    peer = _parse_address(request.client.host if request.client else None)
    if peer is None:
        return None

    trusted_proxies = parse_network_csv(trusted_proxy_cidrs)
    if not address_in_networks(peer, trusted_proxies):
        return peer

    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if not forwarded_for:
        return peer
    forwarded_chain = [_parse_address(item) for item in forwarded_for.split(",")]
    if not forwarded_chain or any(item is None for item in forwarded_chain):
        return peer

    addresses = [item for item in forwarded_chain if item is not None]
    for address in reversed(addresses):
        if not address_in_networks(address, trusted_proxies):
            return address
    return addresses[0] if addresses else peer


def masked_ip_prefix(address: IpAddress | None) -> str | None:
    if address is None:
        return None
    prefix_length = 24 if address.version == 4 else 64
    return ip_network(f"{address}/{prefix_length}", strict=False).with_prefixlen
