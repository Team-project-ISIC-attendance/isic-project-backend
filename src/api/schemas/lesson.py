from pydantic import BaseModel


class LessonResponse(BaseModel):
    id: int
    week_number: int
    date: str
    cancelled: bool


class LessonUpdateRequest(BaseModel):
    cancelled: bool | None = None


class WeekLessonAttendanceSummary(BaseModel):
    total: int
    pritomny: int
    nepritomny: int
    nahrada: int


class WeekLessonResponse(BaseModel):
    lesson_id: int
    schedule_entry_id: int
    subject_name: str
    lesson_type: str
    day_of_week: int
    start_time: str
    end_time: str
    room: str | None
    attendance_summary: WeekLessonAttendanceSummary
