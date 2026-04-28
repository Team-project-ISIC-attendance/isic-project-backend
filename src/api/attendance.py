from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.dependencies import get_current_user
from src.api.schemas.attendance import (
    AttendanceMoveRequest,
    AttendanceMoveResponse,
    AttendanceResponse,
    AttendanceUpdateRequest,
    AttendanceUpdateResponse,
)
from src.database.connection import get_db
from src.models.attendance import AttendanceRecord
from src.models.lesson import Lesson
from src.models.schedule_entry import ScheduleEntry
from src.models.subject import Subject
from src.models.user import User, UserRole
from src.services.attendance_service import (
    get_lesson_attendance,
    move_attendance,
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


@router.post(
    "/attendance/{attendance_id}/move",
    response_model=AttendanceMoveResponse,
    summary="Move attendance record to a different lesson",
    responses={
        400: {"description": "Validation error"},
        403: {"description": "Not your subject"},
        404: {"description": "Attendance record not found"},
    },
)
async def move_attendance_record(
    attendance_id: int,
    body: AttendanceMoveRequest,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> AttendanceMoveResponse:
    result = await move_attendance(db, attendance_id, body.target_lesson_id)
    if isinstance(result, str):
        if "not found" in result.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=result,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result,
        )

    record: AttendanceRecord = result
    # Teacher isolation: re-load with relationships
    reload_stmt = (
        sa_select(AttendanceRecord)
        .where(AttendanceRecord.id == record.id)
        .options(
            selectinload(AttendanceRecord.lesson)
            .selectinload(Lesson.schedule_entry)
            .selectinload(ScheduleEntry.subject)
        )
    )
    reload_result = await db.execute(reload_stmt)
    reloaded = reload_result.scalar_one()
    subject: Subject = reloaded.lesson.schedule_entry.subject

    if (
        current_user.role != UserRole.admin
        and subject.teacher_id != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not your subject",
        )

    return AttendanceMoveResponse(
        attendance_id=record.id,
        lesson_id=record.lesson_id,
        status=record.status.value,
    )
