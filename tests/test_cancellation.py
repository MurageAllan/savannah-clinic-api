
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.models import Doctor, Patient, WorkingHours
from app.services.appointments import (
    book_appointment,
    cancel_appointment
)
from app.services.availability import get_available_slots

import pytest
from fastapi import HTTPException


CLINIC_TZ = ZoneInfo("Africa/Nairobi")


def test_successful_cancellation(db_session):

    # Arrange: create a doctor and patient
    doctor = Doctor(name="Cancellation Test Doctor")

    patient = Patient(
        name="Cancellation Test Patient",
        email="cancellation@example.com"
    )

    db_session.add_all([doctor, patient])
    db_session.flush()

    # Doctor works on Mondays from 09:00 to 17:00
    db_session.add(
        WorkingHours(
            doctor_id=doctor.id,
            day_of_week=0,
            start_time=time(9, 0),
            end_time=time(17, 0)
        )
    )

    db_session.flush()

    # Calculate a future Monday
    today = datetime.now(CLINIC_TZ).date()
    days_until_monday = (0 - today.weekday()) % 7 + 7
    appointment_date = today + timedelta(
        days=days_until_monday
    )

    appointment_time = datetime.combine(
        appointment_date,
        time(9, 0),
        tzinfo=CLINIC_TZ
    )

    # Act 1: book the appointment
    appointment = book_appointment(
        db=db_session,
        doctor_id=doctor.id,
        patient_id=patient.id,
        starts_at=appointment_time
    )

    appointment_id = appointment.id

    # Assert: 09:00 is now unavailable
    slots_before = get_available_slots(
        db=db_session,
        doctor_id=doctor.id,
        requested_date=appointment_date
    )

    assert appointment_time.isoformat() not in slots_before
    assert len(slots_before) == 15

    # Act 2: cancel the appointment
    cancelled = cancel_appointment(
        db=db_session,
        appointment_id=appointment_id,
        reason="Patient unavailable"
    )

    # Assert: appointment was cancelled
    assert cancelled.id == appointment_id
    assert cancelled.status == "CANCELLED"
    assert cancelled.cancellation_reason == "Patient unavailable"
    assert cancelled.cancelled_at is not None

    # Assert: cancelled slot is available again
    slots_after = get_available_slots(
        db=db_session,
        doctor_id=doctor.id,
        requested_date=appointment_date
    )

    assert appointment_time.isoformat() in slots_after
    assert len(slots_after) == 16

    # Attempt to cancel the same appointment again
    with pytest.raises(HTTPException) as exc_info:
        cancel_appointment(
            db=db_session,
            appointment_id=appointment_id,
            reason="Another cancellation request"
        )

    # Verify that repeated cancellation is rejected
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Appointment is already cancelled"

    # Verify original cancellation details remain unchanged
    db_session.refresh(cancelled)

    assert cancelled.status == "CANCELLED"
    assert cancelled.cancellation_reason == "Patient unavailable"
