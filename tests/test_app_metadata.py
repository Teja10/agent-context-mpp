from app.main import app


def test_app_title_is_thoth_api() -> None:
    assert app.title == "Thoth API"
