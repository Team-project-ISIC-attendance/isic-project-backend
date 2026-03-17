from pydantic import BaseModel


class WeekResponse(BaseModel):
    week_number: int
    note: str
    date_range: str


class WeekNoteUpdate(BaseModel):
    note: str
