from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import (
    ensure_subject_access,
    get_current_user,
    require_teacher_or_admin,
)
from src.api.schemas import (
    EnrollmentResponse,
    EnrollStudentRequest,
    ImportResult,
)
from src.database.connection import get_db
from src.models.subject import Subject
from src.models.user import User
from src.services.csv_parser import parse_csv
from src.services.enrollment_service import (
    delete_enrollment,
    enroll_student,
    import_students,
    list_enrolled_students,
)
from src.utils.datetime import isoformat_utc

router = APIRouter(
    prefix="/subjects/{subject_id}/students",
    tags=["students"],
)


def _enrollment_response(enrollment: "Enrollment") -> EnrollmentResponse:  # type: ignore[name-defined]  # noqa: F821
    return EnrollmentResponse(
        enrollment_id=enrollment.id,
        isic_id=enrollment.isic.id,
        student_identifier=enrollment.isic.student_identifier,
        isic_identifier=enrollment.isic.isic_identifier,
        full_name=enrollment.isic.full_name,
        first_name=enrollment.isic.first_name,
        last_name=enrollment.isic.last_name,
        study_identification=enrollment.isic.study_identification,
        email_is=enrollment.isic.email_is,
        enrolled_at=isoformat_utc(enrollment.enrolled_at) or "",
    )


@router.get(
    "",
    response_model=list[EnrollmentResponse],
    summary="List enrolled students",
)
async def list_students(
    subject_id: int,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[EnrollmentResponse]:
    subject = await db.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subject not found",
        )
    ensure_subject_access(current_user, subject)
    enrollments = await list_enrolled_students(db, subject_id)
    return [_enrollment_response(e) for e in enrollments]


@router.post(
    "",
    response_model=EnrollmentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Enroll a student",
    responses={409: {"description": "Student already enrolled"}},
)
async def enroll_student_endpoint(
    subject_id: int,
    data: EnrollStudentRequest,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> EnrollmentResponse:
    require_teacher_or_admin(current_user)
    subject = await db.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subject not found",
        )
    ensure_subject_access(current_user, subject)
    try:
        enrollment = await enroll_student(
            db,
            subject_id=subject_id,
            isic_identifier=data.isic_identifier,
            first_name=data.first_name,
            last_name=data.last_name,
        )
    except IntegrityError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Student already enrolled in this subject",
        ) from err
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err
    return _enrollment_response(enrollment)


@router.post(
    "/import",
    response_model=ImportResult,
    summary="Import students from CSV",
)
async def import_students_endpoint(
    subject_id: int,
    file: UploadFile,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> ImportResult:
    require_teacher_or_admin(current_user)
    subject = await db.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subject not found",
        )
    ensure_subject_access(current_user, subject)
    content = await file.read()
    rows, errors = parse_csv(content)
    try:
        return await import_students(db, subject_id, rows, errors)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(err),
        ) from err


@router.delete(
    "/{enrollment_id}",
    summary="Remove student enrollment",
    responses={404: {"description": "Enrollment not found"}},
)
async def delete_enrollment_endpoint(
    subject_id: int,
    enrollment_id: int,
    current_user: User = Depends(get_current_user),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict[str, str]:
    require_teacher_or_admin(current_user)
    subject = await db.get(Subject, subject_id)
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subject not found",
        )
    ensure_subject_access(current_user, subject)
    deleted = await delete_enrollment(db, enrollment_id, subject_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Enrollment not found",
        )
    return {"detail": "Enrollment deleted"}
