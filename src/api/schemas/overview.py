from pydantic import BaseModel


class OverviewScheduleEntry(BaseModel):
    id: int
    subject_name: str
    lesson_type: str
    start_time: str
    end_time: str
    day_of_week: int
    subject_color: str
    recurrence: str


class OverviewWeek(BaseModel):
    week_number: int
    date_range: str
    lesson_id: int | None
    is_current: bool


class OverviewStudentWeek(BaseModel):
    week_number: int
    attendance_id: int | None
    status: str | None


class OverviewStudent(BaseModel):
    isic_identifier: str
    first_name: str | None
    last_name: str | None
    weeks: list[OverviewStudentWeek]


class OverviewResponse(BaseModel):
    schedule_entry: OverviewScheduleEntry
    weeks: list[OverviewWeek]
    students: list[OverviewStudent]
