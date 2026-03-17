from pydantic import BaseModel


class ScheduleEntryCreate(BaseModel):
    subject_id: int
    day_of_week: int
    start_time: str
    end_time: str
    room: str | None = None
    lesson_type: str


class ScheduleEntryResponse(BaseModel):
    id: int
    subject_id: int
    subject_name: str
    subject_code: str
    subject_color: str
    day_of_week: int
    start_time: str
    end_time: str
    room: str | None
    lesson_type: str
