from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from app.config import MainnetSafetyError, Settings, TESTNET_PATHUSD_ADDRESS


@dataclass(frozen=True)
class SettingsEnvironment:
    """Environment values required to construct application settings."""

    environment: str
    tempo_network: str
    mainnet_confirmation: str
    mpp_realm: str
    mpp_secret_key: str
    pathusd_address: str
    database_url: str


def load_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    settings_environment: SettingsEnvironment,
) -> Settings:
    """Set every required environment variable and return loaded settings."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ENVIRONMENT", settings_environment.environment)
    monkeypatch.setenv("TEMPO_NETWORK", settings_environment.tempo_network)
    monkeypatch.setenv(
        "MAINNET_CONFIRMATION",
        settings_environment.mainnet_confirmation,
    )
    monkeypatch.setenv("MPP_REALM", settings_environment.mpp_realm)
    monkeypatch.setenv("MPP_SECRET_KEY", settings_environment.mpp_secret_key)
    monkeypatch.setenv("PATHUSD_ADDRESS", settings_environment.pathusd_address)
    monkeypatch.setenv("DATABASE_URL", settings_environment.database_url)
    return Settings()


def valid_mainnet_environment() -> SettingsEnvironment:
    """Return a fully safe mainnet settings environment."""
    return SettingsEnvironment(
        environment="production",
        tempo_network="mainnet",
        mainnet_confirmation="true",
        mpp_realm="agent-context.example",
        mpp_secret_key="secret-key",
        pathusd_address="0x0000000000000000000000000000000000000001",
        database_url="postgresql+psycopg://thoth:thoth@127.0.0.1:55432/thoth_test",
    )


def test_mainnet_rejects_non_production_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = load_settings(
        monkeypatch,
        tmp_path,
        replace(valid_mainnet_environment(), environment="development"),
    )

    with pytest.raises(
        MainnetSafetyError,
        match="ENVIRONMENT must be production on mainnet",
    ):
        settings.validate_mainnet_safety()


def test_mainnet_rejects_missing_confirmation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = load_settings(
        monkeypatch,
        tmp_path,
        replace(valid_mainnet_environment(), mainnet_confirmation="false"),
    )

    with pytest.raises(
        MainnetSafetyError,
        match="MAINNET_CONFIRMATION must be true on mainnet",
    ):
        settings.validate_mainnet_safety()


def test_mainnet_rejects_local_realm(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = load_settings(
        monkeypatch,
        tmp_path,
        replace(valid_mainnet_environment(), mpp_realm="http://localhost"),
    )

    with pytest.raises(
        MainnetSafetyError,
        match="MPP_REALM must not be local on mainnet",
    ):
        settings.validate_mainnet_safety()


def test_mainnet_rejects_testnet_pathusd_address(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = load_settings(
        monkeypatch,
        tmp_path,
        replace(
            valid_mainnet_environment(),
            pathusd_address=TESTNET_PATHUSD_ADDRESS,
        ),
    )

    with pytest.raises(
        MainnetSafetyError,
        match="PATHUSD_ADDRESS must not use the testnet default",
    ):
        settings.validate_mainnet_safety()


def test_mainnet_accepts_safe_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = load_settings(monkeypatch, tmp_path, valid_mainnet_environment())

    settings.validate_mainnet_safety()


def test_moderato_skips_mainnet_safety_checks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    settings = load_settings(
        monkeypatch,
        tmp_path,
        SettingsEnvironment(
            environment="development",
            tempo_network="moderato",
            mainnet_confirmation="false",
            mpp_realm="http://127.0.0.1",
            mpp_secret_key="secret-key",
            pathusd_address=TESTNET_PATHUSD_ADDRESS,
            database_url="postgresql+psycopg://thoth:thoth@127.0.0.1:55432/thoth_test",
        ),
    )

    settings.validate_mainnet_safety()


def test_settings_rejects_non_postgres_database_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="DATABASE_URL must use postgresql\\+psycopg"):
        load_settings(
            monkeypatch,
            tmp_path,
            replace(
                valid_mainnet_environment(),
                database_url="postgresql://thoth:thoth@127.0.0.1:55432/thoth_test",
            ),
        )


def test_settings_rejects_unknown_dotenv_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tmp_path.joinpath(".env").write_text("UNEXPECTED_KEY=value\n")

    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        load_settings(monkeypatch, tmp_path, valid_mainnet_environment())
