from datetime import date

from pydantic import BaseModel, Field, model_validator

from src.utils.semester import count_semester_weeks


class SemesterCreate(BaseModel):
    name: str
    start_date: date
    end_date: date
    total_weeks: int = Field(default=13, ge=1, le=52)

    @model_validator(mode="after")
    def validate_week_range(self) -> "SemesterCreate":
        expected_weeks = count_semester_weeks(self.start_date, self.end_date)
        if self.total_weeks != expected_weeks:
            raise ValueError(
                "total_weeks must match the calendar weeks covered by the selected dates"
            )
        return self


class SemesterResponse(BaseModel):
    id: int
    name: str
    start_date: date
    end_date: date
    total_weeks: int
