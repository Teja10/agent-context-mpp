from pathlib import Path
from typing import Literal

from eth_utils.address import is_checksum_address
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

MAINNET_CHAIN_ID = 4217
MODERATO_CHAIN_ID = 42431
MAINNET_RPC_URL = "https://rpc.tempo.xyz"
MODERATO_RPC_URL = "https://rpc.moderato.tempo.xyz"
MAINNET_EXPLORER_URL = "https://explore.tempo.xyz"
MODERATO_EXPLORER_URL = "https://explore.tempo.xyz"
TESTNET_PATHUSD_ADDRESS = "0x20c0000000000000000000000000000000000000"


class MainnetSafetyError(RuntimeError):
    """Raised when mainnet configuration fails a required safety check."""


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="forbid")

    environment: str = Field(alias="ENVIRONMENT")
    tempo_network: Literal["mainnet", "moderato"] = Field(alias="TEMPO_NETWORK")
    mainnet_confirmation: bool = Field(alias="MAINNET_CONFIRMATION")
    mpp_realm: str = Field(alias="MPP_REALM")
    mpp_secret_key: str = Field(alias="MPP_SECRET_KEY")
    publisher_recipient: str = Field(alias="PUBLISHER_RECIPIENT")
    pathusd_address: str = Field(alias="PATHUSD_ADDRESS")
    database_path: Path = Field(alias="DATABASE_PATH")

    def __init__(self) -> None:
        super().__init__()

    @property
    def chain_id(self) -> int:
        """Return the Tempo chain ID for the configured network."""
        if self.tempo_network == "mainnet":
            return MAINNET_CHAIN_ID
        return MODERATO_CHAIN_ID

    @property
    def rpc_url(self) -> str:
        """Return the RPC URL for the configured network."""
        if self.tempo_network == "mainnet":
            return MAINNET_RPC_URL
        return MODERATO_RPC_URL

    @property
    def explorer_url(self) -> str:
        """Return the explorer URL for the configured network."""
        if self.tempo_network == "mainnet":
            return MAINNET_EXPLORER_URL
        return MODERATO_EXPLORER_URL

    def validate_mainnet_safety(self) -> None:
        """Validate explicit safeguards before allowing mainnet operation."""
        if self.tempo_network == "moderato":
            return
        if self.environment != "production":
            raise MainnetSafetyError("ENVIRONMENT must be production on mainnet")
        if not self.mainnet_confirmation:
            raise MainnetSafetyError("MAINNET_CONFIRMATION must be true on mainnet")
        mpp_realm = self.mpp_realm.lower()
        if "localhost" in mpp_realm or "127.0.0.1" in mpp_realm:
            raise MainnetSafetyError("MPP_REALM must not be local on mainnet")
        if not is_checksum_address(self.publisher_recipient):
            raise MainnetSafetyError("PUBLISHER_RECIPIENT must be EIP-55 checksummed")
        if self.pathusd_address.lower() == TESTNET_PATHUSD_ADDRESS:
            raise MainnetSafetyError("PATHUSD_ADDRESS must not use the testnet default")
