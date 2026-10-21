
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Doctor, Patient, WorkingHours, Appointment
from app.services.availability import CLINIC_TIMEZONE, SLOT_DURATION

from datetime import datetime, timedelta, timezone
from sqlalchemy import select


def book_appointment(
    db: Session,
    doctor_id: int,
    patient_id: int,
    starts_at: datetime
) -> Appointment:

    # 1. Check doctor and patient
    if db.get(Doctor, doctor_id) is None:
        raise HTTPException(404, "Doctor not found")

    if db.get(Patient, patient_id) is None:
        raise HTTPException(404, "Patient not found")

    # 2. Require timezone-aware datetime
    if starts_at.tzinfo is None or starts_at.utcoffset() is None:
        raise HTTPException(422, "Appointment time must include a timezone")

    # local_start = starts_at.astimezone(CLINIC_TIMEZONE)

    local_start = validate_appointment_slot(db,doctor_id,starts_at)

    # 3. Reject appointments less than one hour away
    if local_start < datetime.now(CLINIC_TIMEZONE) + timedelta(hours=1):
        raise HTTPException(
            400,
            "Appointments must be booked at least one hour in advance"
        )

    # 4. Enforce 30-minute slot boundaries
    if (
        local_start.minute not in (0, 30)
        or local_start.second != 0
        or local_start.microsecond != 0
    ):
        raise HTTPException(
            400,
            "Appointments must start on a 30-minute boundary"
        )

    # 5. Find the doctor's working hours
    schedule = db.scalar(
        select(WorkingHours).where(
            WorkingHours.doctor_id == doctor_id,
            WorkingHours.day_of_week == local_start.weekday()
        )
    )

    if schedule is None:
        raise HTTPException(400, "Doctor does not work on this day")

    work_start = datetime.combine(
        local_start.date(),
        schedule.start_time,
        tzinfo=CLINIC_TIMEZONE
    )

    work_end = datetime.combine(
        local_start.date(),
        schedule.end_time,
        tzinfo=CLINIC_TIMEZONE
    )

    # 6. Ensure appointment fits within working hours
    if local_start < work_start or local_start + SLOT_DURATION > work_end:
        raise HTTPException(
            400,
            "Appointment is outside the doctor's working hours"
        )

    # 7. Create the appointment
    appointment = Appointment(
        doctor_id=doctor_id,
        patient_id=patient_id,
        starts_at=local_start,
        status="BOOKED"
    )

    db.add(appointment)

    # 8. Commit and handle duplicate bookings
    try:
        db.commit()

    except IntegrityError as exc:
        db.rollback()

        constraint_name = getattr(
            getattr(exc.orig, "diag", None),
            "constraint_name",
            None
        )

        if constraint_name == "uq_active_doctor_slot":
            raise HTTPException(
                409,
                "This appointment slot is already booked"
            ) from exc

        raise

    db.refresh(appointment)
    return appointment



def cancel_appointment(
    db: Session,
    appointment_id: int,
    reason: str
) -> Appointment:

    # 1. Validate cancellation reason
    reason = reason.strip()

    if not reason:
        raise HTTPException(
            status_code=422,
            detail="Cancellation reason is required"
        )

    if len(reason) > 500:
        raise HTTPException(
            status_code=422,
            detail="Cancellation reason must not exceed 500 characters"
        )

    # 2. Find and lock the appointment
    appointment = db.scalar(
        select(Appointment)
        .where(Appointment.id == appointment_id)
        .with_for_update()
    )

    if appointment is None:
        raise HTTPException(
            status_code=404,
            detail="Appointment not found"
        )

    # 3. Check current status
    if appointment.status == "CANCELLED":
        raise HTTPException(
            status_code=409,
            detail="Appointment is already cancelled"
        )

    # 4. Update appointment
    appointment.status = "CANCELLED"
    appointment.cancellation_reason = reason
    appointment.cancelled_at = datetime.now(timezone.utc)

    # 5. Persist changes
    db.commit()
    db.refresh(appointment)

    return appointment



def reschedule_appointment(
    db: Session,
    appointment_id: int,
    starts_at: datetime
) -> Appointment:

    # 1. Retrieve and lock existing appointment
    appointment = db.scalar(
        select(Appointment)
        .where(Appointment.id == appointment_id)
        .with_for_update()
    )

    if appointment is None:
        raise HTTPException(
            404,
            "Appointment not found"
        )

    # 2. Cancelled appointments cannot be rescheduled
    if appointment.status == "CANCELLED":
        raise HTTPException(
            409,
            "Cancelled appointments cannot be rescheduled"
        )

    # 3. Validate new appointment time
    local_start = validate_appointment_slot(
        db,
        appointment.doctor_id,
        starts_at
    )

    # 4. Reject rescheduling to the same slot
    current_start = appointment.starts_at.astimezone(
        CLINIC_TIMEZONE
    )

    if current_start == local_start:
        raise HTTPException(
            400,
            "New appointment time must differ from current time"
        )

    # 5. Update existing appointment
    appointment.starts_at = local_start

    # 6. Commit atomically
    try:
        db.commit()

    except IntegrityError as exc:
        db.rollback()

        constraint_name = getattr(
            getattr(exc.orig, "diag", None),
            "constraint_name",
            None
        )

        if constraint_name == "uq_active_doctor_slot":
            raise HTTPException(
                409,
                "The requested appointment slot is already booked"
            ) from exc

        raise

    db.refresh(appointment)

    return appointment




def validate_appointment_slot(
    db: Session,
    doctor_id: int,
    starts_at: datetime
) -> datetime:

    # Require timezone-aware datetime
    if starts_at.tzinfo is None or starts_at.utcoffset() is None:
        raise HTTPException(
            422,
            "Appointment time must include a timezone"
        )

    local_start = starts_at.astimezone(CLINIC_TIMEZONE)

    # Minimum one-hour booking notice
    if local_start < datetime.now(CLINIC_TIMEZONE) + timedelta(hours=1):
        raise HTTPException(
            400,
            "Appointments must be booked at least one hour in advance"
        )

    # Enforce 30-minute slot boundaries
    if (
        local_start.minute not in (0, 30)
        or local_start.second != 0
        or local_start.microsecond != 0
    ):
        raise HTTPException(
            400,
            "Appointments must start on a 30-minute boundary"
        )

    # Retrieve doctor working hours
    schedule = db.scalar(
        select(WorkingHours).where(
            WorkingHours.doctor_id == doctor_id,
            WorkingHours.day_of_week == local_start.weekday()
        )
    )

    if schedule is None:
        raise HTTPException(
            400,
            "Doctor does not work on this day"
        )

    work_start = datetime.combine(
        local_start.date(),
        schedule.start_time,
        tzinfo=CLINIC_TIMEZONE
    )

    work_end = datetime.combine(
        local_start.date(),
        schedule.end_time,
        tzinfo=CLINIC_TIMEZONE
    )

    if local_start < work_start or local_start + SLOT_DURATION > work_end:
        raise HTTPException(
            400,
            "Appointment is outside the doctor's working hours"
        )

    return local_start
