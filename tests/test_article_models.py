from app.models import ArticleMetadata, ContextPackage


def test_public_models_do_not_expose_article_body() -> None:
    """Ensure public article/context models do not expose article body text."""
    assert "body" not in ArticleMetadata.model_fields
    assert "body" not in ContextPackage.model_fields
