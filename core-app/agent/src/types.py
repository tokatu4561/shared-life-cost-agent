from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ReceiptCategory = Literal["食費", "日用品", "その他"]


@dataclass(frozen=True)
class ReceiptRequest:
    line_user_id: str
    line_display_name: str
    line_message_id: str
    bucket: str
    key: str
    image_s3_uri: str


@dataclass(frozen=True)
class NormalizedReceipt:
    line_user_id: str
    line_display_name: str
    line_message_id: str
    receipt_date: str | None
    store: str | None
    category: ReceiptCategory
    total: int | None
    image_s3_uri: str

    def has_required_fields(self) -> bool:
        return bool(self.store) and self.total is not None
