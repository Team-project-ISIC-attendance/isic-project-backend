from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user
from src.api.schemas import (
    EnrollmentResponse,
    EnrollStudentRequest,
    ImportResult,
)
from src.database.connection import get_db
from src.models.user import User
from src.services.csv_parser import parse_csv
from src.services.enrollment_service import (
    delete_enrollment,
    enroll_student,
    import_students,
    list_enrolled_students,
)

router = APIRouter(
    prefix="/subjects/{subject_id}/students",
    tags=["students"],
)


def _enrollment_response(enrollment: "Enrollment") -> EnrollmentResponse:  # type: ignore[name-defined]  # noqa: F821
    return EnrollmentResponse(
        enrollment_id=enrollment.id,
        isic_id=enrollment.isic.id,
        isic_identifier=enrollment.isic.isic_identifier,
        first_name=enrollment.isic.first_name,
        last_name=enrollment.isic.last_name,
        enrolled_at=enrollment.enrolled_at.isoformat(),
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
    content = await file.read()
    rows, errors = parse_csv(content)
    return await import_students(db, subject_id, rows, errors)


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
    deleted = await delete_enrollment(db, enrollment_id, subject_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Enrollment not found",
        )
    return {"detail": "Enrollment deleted"}
