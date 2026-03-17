from pydantic import BaseModel


class SubjectCreate(BaseModel):
    name: str
    code: str
    color: str = "#4CAF50"


class SubjectUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    color: str | None = None


class SubjectResponse(BaseModel):
    id: int
    name: str
    code: str
    color: str
    teacher_name: str
