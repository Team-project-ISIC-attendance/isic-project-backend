from datetime import date

from pydantic import BaseModel


class SemesterCreate(BaseModel):
    name: str
    start_date: date
    end_date: date
    total_weeks: int = 13


class SemesterResponse(BaseModel):
    id: int
    name: str
    start_date: date
    end_date: date
    total_weeks: int
