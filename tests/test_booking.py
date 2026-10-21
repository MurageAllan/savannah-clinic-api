
from datetime import datetime, time, timedelta

from zoneinfo import ZoneInfo

from app.models import Doctor, Patient, WorkingHours
from app.services.appointments import book_appointment

import pytest

from fastapi import HTTPException
from sqlalchemy import select

from app.models import Appointment


CLINIC_TZ = ZoneInfo("Africa/Nairobi")


def test_successful_booking(db_session):

    # 1. Create a doctor
    doctor = Doctor(name="Test Doctor")

    # 2. Create a patient
    patient = Patient(
        name="Test Patient",
        email="booking-test@example.com"
    )

    db_session.add_all([doctor, patient])
    db_session.flush()

    # 3. Create a Monday working schedule
    db_session.add(
        WorkingHours(
            doctor_id=doctor.id,
            day_of_week=0,
            start_time=time(9, 0),
            end_time=time(17, 0)
        )
    )

    db_session.flush()

    # 4. Choose a future Monday
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

    # 5. Execute our actual booking service
    appointment = book_appointment(
        db=db_session,
        doctor_id=doctor.id,
        patient_id=patient.id,
        starts_at=appointment_time
    )

    # 6. Verify expected results
    assert appointment.id is not None
    assert appointment.doctor_id == doctor.id
    assert appointment.patient_id == patient.id
    assert appointment.status == "BOOKED"

    assert (
        appointment.starts_at.astimezone(CLINIC_TZ)
        == appointment_time
    )




def test_duplicate_booking(db_session):

    # Arrange: create one doctor and two patients
    doctor = Doctor(name="Duplicate Test Doctor")

    patient_a = Patient(
        name="Patient A",
        email="patient-a@example.com"
    )

    patient_b = Patient(
        name="Patient B",
        email="patient-b@example.com"
    )

    db_session.add_all([doctor, patient_a, patient_b])
    db_session.flush()

    # Give the doctor Monday working hours
    db_session.add(
        WorkingHours(
            doctor_id=doctor.id,
            day_of_week=0,
            start_time=time(9, 0),
            end_time=time(17, 0)
        )
    )

    db_session.flush()

    # Find a future Monday
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

    # Act: first patient successfully books
    first_booking = book_appointment(
        db=db_session,
        doctor_id=doctor.id,
        patient_id=patient_a.id,
        starts_at=appointment_time
    )

    assert first_booking.status == "BOOKED"

    # Act: second patient attempts the same slot
    with pytest.raises(HTTPException) as exc_info:
        book_appointment(
            db=db_session,
            doctor_id=doctor.id,
            patient_id=patient_b.id,
            starts_at=appointment_time
        )

    # Assert: the second booking was rejected
    assert exc_info.value.status_code == 409

    # Assert: the original booking still exists
    active_bookings = db_session.scalars(
        select(Appointment).where(
            Appointment.doctor_id == doctor.id,
            Appointment.status == "BOOKED"
        )
    ).all()

    assert len(active_bookings) == 1
    assert active_bookings[0].patient_id == patient_a.id




@pytest.mark.parametrize(
    "hour, minute, expected_error",
    [
        (8, 30, "outside the doctor's working hours"),
        (9, 15, "30-minute boundary"),
        (17, 0, "outside the doctor's working hours"),
    ]
)
def test_invalid_appointment_time(
    db_session, hour, minute, expected_error
):

    # Arrange: create doctor and patient
    doctor = Doctor(name="Validation Test Doctor")

    patient = Patient(
        name="Validation Test Patient",
        email="validation@example.com"
    )

    db_session.add_all([doctor, patient])
    db_session.flush()

    # Doctor works Monday, 09:00 to 17:00
    db_session.add(
        WorkingHours(
            doctor_id=doctor.id,
            day_of_week=0,
            start_time=time(9, 0),
            end_time=time(17, 0)
        )
    )

    db_session.flush()

    # Find a future Monday
    today = datetime.now(CLINIC_TZ).date()

    days_until_monday = (0 - today.weekday()) % 7 + 7

    appointment_date = today + timedelta(
        days=days_until_monday
    )

    appointment_time = datetime.combine(
        appointment_date,
        time(hour, minute),
        tzinfo=CLINIC_TZ
    )

    # Act: attempt invalid booking
    with pytest.raises(HTTPException) as exc_info:
        book_appointment(
            db=db_session,
            doctor_id=doctor.id,
            patient_id=patient.id,
            starts_at=appointment_time
        )

    # Assert: correct validation error
    assert exc_info.value.status_code == 400
    assert expected_error in exc_info.value.detail



@pytest.mark.parametrize(
    "scenario",
    ["past", "within_one_hour"]
)
def test_booking_time_restrictions(db_session, scenario):

    # Arrange: create doctor and patient
    doctor = Doctor(name="Time Restriction Doctor")

    patient = Patient(
        name="Time Restriction Patient",
        email="time-test@example.com"
    )

    db_session.add_all([doctor, patient])
    db_session.flush()

    now = datetime.now(CLINIC_TZ)

    if scenario == "past":
        # A slot from yesterday, aligned to the hour
        appointment_time = (
            now - timedelta(days=1)
        ).replace(
            minute=0,
            second=0,
            microsecond=0
        )

    else:
        # Next 30-minute boundary, always less than
        # 30 minutes away
        appointment_time = now.replace(
            minute=(now.minute // 30) * 30,
            second=0,
            microsecond=0
        ) + timedelta(minutes=30)

    # Act: attempt invalid booking
    with pytest.raises(HTTPException) as exc_info:
        book_appointment(
            db=db_session,
            doctor_id=doctor.id,
            patient_id=patient.id,
            starts_at=appointment_time
        )

    # Assert: booking is rejected
    assert exc_info.value.status_code == 400

    assert (
        "at least one hour in advance"
        in exc_info.value.detail
    )
