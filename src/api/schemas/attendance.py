from pydantic import BaseModel, field_validator


class AttendanceLessonInfo(BaseModel):
    id: int
    subject_name: str
    subject_color: str
    lesson_type: str
    week_number: int
    date: str
    start_time: str
    end_time: str
    room: str | None
    day_of_week: int
    recurrence: str


class AttendanceStudentEntry(BaseModel):
    attendance_id: int
    isic_identifier: str
    first_name: str | None
    last_name: str | None
    status: str
    marked_by: str
    scan_timestamp: str | None


class AttendanceSummary(BaseModel):
    total: int
    pritomny: int
    nepritomny: int
    nahrada: int


class AttendanceResponse(BaseModel):
    lesson: AttendanceLessonInfo
    students: list[AttendanceStudentEntry]
    summary: AttendanceSummary


class AttendanceUpdateRequest(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {"pritomny", "nepritomny", "nahrada"}
        if v not in allowed:
            msg = f"Status must be one of: {', '.join(sorted(allowed))}"
            raise ValueError(msg)
        return v


class AttendanceUpdateResponse(BaseModel):
    attendance_id: int
    status: str
    marked_by: str
