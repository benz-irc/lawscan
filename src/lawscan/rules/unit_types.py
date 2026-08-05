"""The shape a split section has, without the rest of a schema layer.

The splitter came over from a system where this was one class among forty in a
Pydantic module tied to an API. Here it is a dataclass, because nothing
validates it over a wire and nothing serialises it to a client — it exists to
be counted and written into one CSV cell.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class StructureUnitType(StrEnum):
    CHAPTER = "CHAPTER"  # หมวด
    PART = "PART"  # ส่วน
    SECTION = "SECTION"  # มาตรา
    CLAUSE = "CLAUSE"  # ข้อ
    PARAGRAPH = "PARAGRAPH"  # วรรค
    SUBPARAGRAPH = "SUBPARAGRAPH"  # อนุมาตรา
    ITEM = "ITEM"
    TRANSITIONAL = "TRANSITIONAL"  # บทเฉพาะกาล
    PENALTY = "PENALTY"  # บทกำหนดโทษ


@dataclass(slots=True)
class StructureUnit:
    """One numbered unit as the document printed it."""

    unit_type: StructureUnitType
    order_no: int
    content: str
    page_number: int
    source_text: str
    confidence: float
    section_no: str | None = None
    paragraph_no: str | None = None
    parent_ref: str | None = None
    title: str | None = None
