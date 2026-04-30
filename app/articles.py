from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True)
class Article:
    """Internal article content loaded from markdown files."""

    title: str
    author: str
    published_date: date
    price: str
    license: str
    summary: str
    key_claims: list[str]
    allowed_excerpts: list[str]
    suggested_citation: str
    slug: str
    body: str


REQUIRED_FIELDS = [
    "title",
    "author",
    "published_date",
    "price",
    "license",
    "summary",
    "key_claims",
    "allowed_excerpts",
    "suggested_citation",
]
LIST_FIELDS = {"key_claims", "allowed_excerpts"}
ARTICLES_DIR = Path(__file__).resolve().parent.parent / "articles"


def load_articles(articles_dir: Path) -> dict[str, Article]:
    """Load strict markdown articles from a directory."""
    return {
        article_path.stem: _load_article(article_path)
        for article_path in sorted(articles_dir.glob("*.md"))
    }


def _load_article(article_path: Path) -> Article:
    lines = article_path.read_text(encoding="utf-8").splitlines()
    if len(lines) < 3 or lines[0] != "---":
        raise ValueError(f"{article_path.name} must start with frontmatter")
    closing_index = lines.index("---", 1)
    if closing_index == 1:
        raise ValueError(f"{article_path.name} frontmatter is empty")

    parsed = _parse_frontmatter(lines[1:closing_index], article_path)
    _validate_fields(parsed, article_path)
    return Article(
        title=_scalar(parsed, "title"),
        author=_scalar(parsed, "author"),
        published_date=_published_date(parsed),
        price=_price(parsed),
        license=_scalar(parsed, "license"),
        summary=_scalar(parsed, "summary"),
        key_claims=_list(parsed, "key_claims"),
        allowed_excerpts=_list(parsed, "allowed_excerpts"),
        suggested_citation=_scalar(parsed, "suggested_citation"),
        slug=article_path.stem,
        body=_body("\n".join(lines[closing_index + 1 :]), article_path),
    )


def _parse_frontmatter(
    frontmatter: list[str],
    article_path: Path,
) -> dict[str, str | list[str]]:
    parsed: dict[str, str | list[str]] = {}
    current_list_key: str | None = None
    for line in frontmatter:
        if line.startswith("  - "):
            if current_list_key is None:
                raise ValueError(f"{article_path.name} has list item without list key")
            value = line[4:].strip()
            if value == "":
                raise ValueError(
                    f"{article_path.name} has empty {current_list_key} item"
                )
            current_list = parsed[current_list_key]
            if not isinstance(current_list, list):
                raise ValueError(f"{article_path.name} malformed {current_list_key}")
            current_list.append(value)
            continue
        current_list_key = None
        if line.startswith(" ") or ":" not in line:
            raise ValueError(f"{article_path.name} has malformed frontmatter line")
        key, value = line.split(":", 1)
        if key == "" or key.strip() != key or key in parsed:
            raise ValueError(f"{article_path.name} has malformed key {key}")
        stripped_value = value.strip()
        if key in LIST_FIELDS:
            if stripped_value != "":
                raise ValueError(f"{article_path.name} list field {key} must use items")
            parsed[key] = []
            current_list_key = key
            continue
        if stripped_value == "":
            raise ValueError(f"{article_path.name} has empty {key}")
        parsed[key] = stripped_value
    return parsed


def _validate_fields(parsed: dict[str, str | list[str]], article_path: Path) -> None:
    for field in REQUIRED_FIELDS:
        if field not in parsed:
            raise ValueError(f"{article_path.name} missing required field {field}")
    unexpected_fields = set(parsed) - set(REQUIRED_FIELDS)
    if unexpected_fields:
        raise ValueError(
            f"{article_path.name} has unexpected fields {unexpected_fields}"
        )


def _scalar(parsed: dict[str, str | list[str]], field: str) -> str:
    value = parsed[field]
    if not isinstance(value, str):
        raise ValueError(f"{field} must be scalar")
    return value


def _list(parsed: dict[str, str | list[str]], field: str) -> list[str]:
    value = parsed[field]
    if not isinstance(value, list) or len(value) == 0:
        raise ValueError(f"{field} must be a non-empty list")
    return value


def _published_date(parsed: dict[str, str | list[str]]) -> date:
    return date.fromisoformat(_scalar(parsed, "published_date"))


def _price(parsed: dict[str, str | list[str]]) -> str:
    value = _scalar(parsed, "price")
    decimal_value = Decimal(value)
    if not decimal_value.is_finite():
        raise ValueError("price must be finite")
    return value


def _body(body: str, article_path: Path) -> str:
    stripped_body = body.strip()
    if stripped_body == "":
        raise ValueError(f"{article_path.name} body is empty")
    return stripped_body
