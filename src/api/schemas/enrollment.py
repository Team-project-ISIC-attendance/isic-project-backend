from pydantic import BaseModel


class EnrollStudentRequest(BaseModel):
    isic_identifier: str
    first_name: str
    last_name: str


class EnrollmentResponse(BaseModel):
    enrollment_id: int
    isic_id: int
    isic_identifier: str
    first_name: str | None
    last_name: str | None
    enrolled_at: str


class ImportError_(BaseModel):  # noqa: N801
    row: int
    reason: str


class ImportResult(BaseModel):
    imported: int
    skipped: int
    errors: list[ImportError_]
