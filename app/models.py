from datetime import date

from pydantic import BaseModel, ConfigDict


class ArticleMetadata(BaseModel):
    """Public article metadata exposed before context purchase."""

    model_config = ConfigDict(extra="forbid")

    title: str
    author: str
    published_date: date
    price: str
    slug: str


class ContextPackage(BaseModel):
    """Paid context response exposed after receipt validation."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    key_claims: list[str]
    allowed_excerpts: list[str]
    suggested_citation: str
    license: str
    receipt: dict[str, str]
