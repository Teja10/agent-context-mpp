"""Token registry for supported Tempo payment currencies."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class TokenInfo:
    """Immutable record of a supported payment token."""

    symbol: str
    address: str
    decimals: int


MAINNET_PATHUSD_ADDRESS = "0x20c0000000000000000000000000000000000000"

MAINNET_TOKENS: dict[str, TokenInfo] = {
    "0x20c0000000000000000000000000000000000000": TokenInfo(
        symbol="pathUSD",
        address="0x20c0000000000000000000000000000000000000",
        decimals=6,
    ),
    "0x20c000000000000000000000b9537d11c60e8b50": TokenInfo(
        symbol="USDC.e",
        address="0x20c000000000000000000000b9537d11c60e8b50",
        decimals=6,
    ),
    "0x20c00000000000000000000014f22ca97301eb73": TokenInfo(
        symbol="USDT0",
        address="0x20c00000000000000000000014f22ca97301eb73",
        decimals=6,
    ),
    "0x20c0000000000000000000002f52d5cc21a3207b": TokenInfo(
        symbol="USDe",
        address="0x20c0000000000000000000002f52d5cc21a3207b",
        decimals=6,
    ),
}

MODERATO_TOKENS: dict[str, TokenInfo] = {
    "0x20c0000000000000000000000000000000000000": TokenInfo(
        symbol="pathUSD",
        address="0x20c0000000000000000000000000000000000000",
        decimals=6,
    ),
    "0x20c000000000000000000000b9537d11c60e8b50": TokenInfo(
        symbol="USDC.e",
        address="0x20c000000000000000000000b9537d11c60e8b50",
        decimals=6,
    ),
}


def resolve(network: Literal["mainnet", "moderato"], address: str) -> TokenInfo:
    """Look up a token by address on the given network.

    Args:
        network: The Tempo network name.
        address: The token contract address (case-insensitive).

    Returns:
        The matching TokenInfo.

    Raises:
        ValueError: If the address is not in the registry for the network.
    """
    registry = MAINNET_TOKENS if network == "mainnet" else MODERATO_TOKENS
    token = registry.get(address.lower())
    if token is None:
        raise ValueError(f"Unsupported currency address {address} on {network}")
    return token
