from pydantic import BaseModel


class RowErrorDetail(BaseModel):
    row: int
    error: str


class BulkImportResponse(BaseModel):
    created: int
    skipped: int
    errors: list[RowErrorDetail]
