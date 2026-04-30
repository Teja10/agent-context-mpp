from pathlib import Path

import pytest

from app.articles import ARTICLES_DIR, Article, load_articles
from app.models import ArticleMetadata, ContextPackage


def write_article(article_path: Path, frontmatter: str) -> None:
    article_path.write_text(
        f"""---
{frontmatter}
---
# Custom Article

Body.
""",
        encoding="utf-8",
    )


def test_loads_demo_articles_with_matching_slugs() -> None:
    articles = load_articles(ARTICLES_DIR)

    assert set(articles) == {
        "ai-agent-payments",
        "context-for-machines",
        "decentralized-identity",
    }
    for slug in articles:
        assert isinstance(articles[slug], Article)
        assert articles[slug].slug == slug


def test_article_missing_title_raises_value_error(tmp_path: Path) -> None:
    article_path = tmp_path / "missing-title.md"
    write_article(
        article_path,
        """author: Agent Context Research
published_date: 2026-04-29
price: 0.25
license: Context preview license
summary: Summary.
key_claims:
  - Claim.
allowed_excerpts:
  - Excerpt.
suggested_citation: Citation.""",
    )

    with pytest.raises(ValueError, match="missing required field title"):
        load_articles(tmp_path)


def test_custom_slug_loads_from_markdown_filename(tmp_path: Path) -> None:
    article_path = tmp_path / "custom-slug.md"
    write_article(
        article_path,
        """title: Custom Article
author: Agent Context Research
published_date: 2026-04-29
price: 0.25
license: Context preview license
summary: Summary.
key_claims:
  - Claim.
allowed_excerpts:
  - Excerpt.
suggested_citation: Citation.""",
    )

    articles = load_articles(tmp_path)

    assert list(articles) == ["custom-slug"]
    assert articles["custom-slug"].slug == "custom-slug"


def test_public_models_do_not_expose_article_body() -> None:
    assert "body" not in ArticleMetadata.model_fields
    assert "body" not in ContextPackage.model_fields
