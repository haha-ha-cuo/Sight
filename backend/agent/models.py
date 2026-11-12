"""原型使用的数据对象；只在当前请求中存在，不映射数据库。"""

from dataclasses import asdict, dataclass

from pydantic import BaseModel, Field


@dataclass
class Article:
    id: str
    title: str
    url: str
    source: str
    published_at: str | None
    feed_summary: str
    summary: str
    summary_kind: str = "feed"

    def to_dict(self) -> dict:
        return asdict(self)


class ArticleSummary(BaseModel):
    article_id: str
    summary: str = Field(min_length=1, max_length=800)


class DigestSummary(BaseModel):
    overview: str = Field(min_length=1, max_length=1600)
    articles: list[ArticleSummary] = Field(min_length=1, max_length=20)
