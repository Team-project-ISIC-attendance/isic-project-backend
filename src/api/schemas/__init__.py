from src.api.schemas.attendance import (
    AttendanceLessonInfo,
    AttendanceResponse,
    AttendanceStudentEntry,
    AttendanceSummary,
    AttendanceUpdateRequest,
    AttendanceUpdateResponse,
)
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
from src.api.schemas.enrollment import (
    EnrollmentResponse,
    EnrollStudentRequest,
    ImportError_,
    ImportResult,
)
from src.api.schemas.lesson import (
    LessonResponse,
    LessonUpdateRequest,
    WeekLessonAttendanceSummary,
    WeekLessonResponse,
)
from src.api.schemas.schedule import ScheduleEntryCreate, ScheduleEntryResponse
from src.api.schemas.semester import SemesterCreate, SemesterResponse
from src.api.schemas.subject import SubjectCreate, SubjectResponse, SubjectUpdate
from src.api.schemas.week import WeekNoteUpdate, WeekResponse

__all__ = [
    "AttendanceLessonInfo",
    "AttendanceResponse",
    "AttendanceStudentEntry",
    "AttendanceSummary",
    "AttendanceUpdateRequest",
    "AttendanceUpdateResponse",
    "EnrollStudentRequest",
    "EnrollmentResponse",
    "HealthResponse",
    "ISICResponse",
    "ISICUpdateRequest",
    "ImportError_",
    "ImportResult",
    "LessonResponse",
    "LessonUpdateRequest",
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
    "WeekLessonAttendanceSummary",
    "WeekLessonResponse",
    "WeekNoteUpdate",
    "WeekResponse",
]
