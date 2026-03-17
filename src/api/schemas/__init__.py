from src.api.schemas.base import (
    HealthResponse,
    ISICResponse,
    ISICUpdateRequest,
    RegisterRequest,
    ScanQueryParams,
    ScanResponse,
    TokenResponse,
    UserResponse,
)
from src.api.schemas.schedule import ScheduleEntryCreate, ScheduleEntryResponse
from src.api.schemas.semester import SemesterCreate, SemesterResponse
from src.api.schemas.subject import SubjectCreate, SubjectResponse, SubjectUpdate
from src.api.schemas.week import WeekNoteUpdate, WeekResponse

__all__ = [
    "HealthResponse",
    "ISICResponse",
    "ISICUpdateRequest",
    "RegisterRequest",
    "ScanQueryParams",
    "ScanResponse",
    "ScheduleEntryCreate",
    "ScheduleEntryResponse",
    "SemesterCreate",
    "SemesterResponse",
    "SubjectCreate",
    "SubjectResponse",
    "SubjectUpdate",
    "TokenResponse",
    "UserResponse",
    "WeekNoteUpdate",
    "WeekResponse",
]
