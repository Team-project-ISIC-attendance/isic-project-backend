import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user
from src.database.connection import get_db
from src.models.user import User
from src.services.export_service import (
    generate_attendance_csv,
    generate_attendance_xlsx,
    generate_students_csv,
    generate_students_xlsx,
    get_attendance_matrix,
    get_students_data,
)

router = APIRouter(
    prefix="/subjects/{subject_id}/export",
    tags=["export"],
)

VALID_FORMATS = {"csv", "xlsx"}


@router.get("/students", summary="Export enrolled students")
async def export_students(
    subject_id: int,
    format: str = "csv",
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> StreamingResponse:
    if format not in VALID_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported format: {format}. Use csv or xlsx.",
        )

    subject, students_data = await get_students_data(db, subject_id)
    today = date.today().isoformat()

    if format == "csv":
        content = generate_students_csv(students_data)
        return StreamingResponse(
            iter([content.encode("utf-8")]),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": (
                    f"attachment; filename={subject.code}_students_{today}.csv"
                ),
            },
        )

    xlsx_bytes = generate_students_xlsx(students_data)
    return StreamingResponse(
        io.BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f"attachment; filename={subject.code}_students_{today}.xlsx"
            ),
        },
    )


@router.get("/attendance", summary="Export attendance matrix")
async def export_attendance(
    subject_id: int,
    semester_id: int,
    format: str = "csv",
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> StreamingResponse:
    if format not in VALID_FORMATS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported format: {format}. Use csv or xlsx.",
        )

    subject, column_headers, data_rows = await get_attendance_matrix(
        db, subject_id, semester_id
    )
    today = date.today().isoformat()

    if format == "csv":
        content = generate_attendance_csv(column_headers, data_rows)
        return StreamingResponse(
            iter([content.encode("utf-8")]),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": (
                    f"attachment; filename={subject.code}_attendance_{today}.csv"
                ),
            },
        )

    xlsx_bytes = generate_attendance_xlsx(column_headers, data_rows)
    return StreamingResponse(
        io.BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f"attachment; filename={subject.code}_attendance_{today}.xlsx"
            ),
        },
    )
