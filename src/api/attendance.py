from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user
from src.api.schemas.attendance import (
    AttendanceResponse,
    AttendanceUpdateRequest,
    AttendanceUpdateResponse,
)
from src.database.connection import get_db
from src.models.user import User, UserRole
from src.services.attendance_service import (
    get_lesson_attendance,
    update_attendance_status,
)

router = APIRouter(tags=["attendance"])


@router.get(
    "/lessons/{lesson_id}/attendance",
    response_model=AttendanceResponse,
    summary="Get attendance for a lesson",
    responses={
        404: {"description": "Lesson not found"},
        403: {"description": "Not your subject"},
    },
)
async def get_attendance(
    lesson_id: int,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> AttendanceResponse:
    data = await get_lesson_attendance(db, lesson_id)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Lesson not found",
        )
    if (
        current_user.role != UserRole.admin
        and data["teacher_id"] != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not your subject",
        )
    return AttendanceResponse(
        lesson=data["lesson"],
        students=data["students"],
        summary=data["summary"],
    )


@router.patch(
    "/attendance/{attendance_id}",
    response_model=AttendanceUpdateResponse,
    summary="Update attendance status",
    responses={404: {"description": "Attendance record not found"}},
)
async def patch_attendance(
    attendance_id: int,
    body: AttendanceUpdateRequest,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> AttendanceUpdateResponse:
    record = await update_attendance_status(db, attendance_id, body.status)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attendance record not found",
        )
    # Teacher isolation: record -> lesson -> schedule_entry -> subject -> teacher_id
    subject = record.lesson.schedule_entry.subject
    if (
        current_user.role != UserRole.admin
        and subject.teacher_id != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not your subject",
        )
    return AttendanceUpdateResponse(
        attendance_id=record.id,
        status=record.status.value,
        marked_by=record.marked_by.value,
    )
