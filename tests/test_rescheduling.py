
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.models import Doctor, Patient, WorkingHours
from app.services.appointments import (
    book_appointment,
    cancel_appointment,
    reschedule_appointment
)
from app.services.availability import get_available_slots

import pytest
from fastapi import HTTPException


CLINIC_TZ = ZoneInfo("Africa/Nairobi")


def test_successful_rescheduling(db_session):

    # Arrange: create a doctor and patient
    doctor = Doctor(name="Rescheduling Test Doctor")

    patient = Patient(
        name="Rescheduling Test Patient",
        email="reschedule@example.com"
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

    # Calculate a future Monday
    today = datetime.now(CLINIC_TZ).date()
    days_until_monday = (0 - today.weekday()) % 7 + 7
    appointment_date = today + timedelta(
        days=days_until_monday
    )

    original_time = datetime.combine(
        appointment_date,
        time(11, 0),
        tzinfo=CLINIC_TZ
    )

    new_time = datetime.combine(
        appointment_date,
        time(11, 30),
        tzinfo=CLINIC_TZ
    )

    # Act 1: book the original appointment
    appointment = book_appointment(
        db=db_session,
        doctor_id=doctor.id,
        patient_id=patient.id,
        starts_at=original_time
    )

    original_id = appointment.id

    # Verify initial availability
    slots_before = get_available_slots(
        db_session,
        doctor.id,
        appointment_date
    )

    assert original_time.isoformat() not in slots_before
    assert new_time.isoformat() in slots_before

    # Act 2: reschedule the appointment
    updated = reschedule_appointment(
        db=db_session,
        appointment_id=original_id,
        starts_at=new_time
    )

    # Assert: appointment identity and state
    assert updated.id == original_id
    assert updated.status == "BOOKED"
    assert updated.patient_id == patient.id
    assert updated.doctor_id == doctor.id

    assert (
        updated.starts_at.astimezone(CLINIC_TZ)
        == new_time
    )

    # Assert: old slot released, new slot occupied
    slots_after = get_available_slots(
        db_session,
        doctor.id,
        appointment_date
    )

    assert original_time.isoformat() in slots_after
    assert new_time.isoformat() not in slots_after

    # Verify the appointment remains persisted
    db_session.refresh(updated)

    assert (
        updated.starts_at.astimezone(CLINIC_TZ)
        == new_time
    )




def test_rescheduling_to_occupied_slot(db_session):

    # Arrange: create doctor and two patients
    doctor = Doctor(name="Reschedule Conflict Doctor")

    patient_a = Patient(
        name="Patient A",
        email="reschedule-a@example.com"
    )

    patient_b = Patient(
        name="Patient B",
        email="reschedule-b@example.com"
    )

    db_session.add_all([doctor, patient_a, patient_b])
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

    # Calculate a future Monday
    today = datetime.now(CLINIC_TZ).date()
    days_until_monday = (0 - today.weekday()) % 7 + 7
    appointment_date = today + timedelta(
        days=days_until_monday
    )

    original_time = datetime.combine(
        appointment_date,
        time(11, 0),
        tzinfo=CLINIC_TZ
    )

    occupied_time = datetime.combine(
        appointment_date,
        time(11, 30),
        tzinfo=CLINIC_TZ
    )

    # Book first appointment at 11:00
    appointment_a = book_appointment(
        db=db_session,
        doctor_id=doctor.id,
        patient_id=patient_a.id,
        starts_at=original_time
    )

    # Book second appointment at 11:30
    appointment_b = book_appointment(
        db=db_session,
        doctor_id=doctor.id,
        patient_id=patient_b.id,
        starts_at=occupied_time
    )

    # Attempt to move appointment A into B's slot
    with pytest.raises(HTTPException) as exc_info:
        reschedule_appointment(
            db=db_session,
            appointment_id=appointment_a.id,
            starts_at=occupied_time
        )

    # Verify conflict response
    assert exc_info.value.status_code == 409

    # Reload the appointments from PostgreSQL
    db_session.refresh(appointment_a)
    db_session.refresh(appointment_b)

    # Verify appointment A was not changed
    assert appointment_a.status == "BOOKED"
    assert (
        appointment_a.starts_at.astimezone(CLINIC_TZ)
        == original_time
    )

    # Verify appointment B was not changed
    assert appointment_b.status == "BOOKED"
    assert (
        appointment_b.starts_at.astimezone(CLINIC_TZ)
        == occupied_time
    )

    # Verify neither occupied slot appears as available
    slots = get_available_slots(
        db=db_session,
        doctor_id=doctor.id,
        requested_date=appointment_date
    )

    assert original_time.isoformat() not in slots
    assert occupied_time.isoformat() not in slots




def test_cannot_reschedule_cancelled_appointment(db_session):

    # Arrange: create a doctor and patient
    doctor = Doctor(name="Cancelled Reschedule Doctor")

    patient = Patient(
        name="Cancelled Reschedule Patient",
        email="cancelled-reschedule@example.com"
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

    original_time = datetime.combine(
        appointment_date,
        time(11, 0),
        tzinfo=CLINIC_TZ
    )

    new_time = datetime.combine(
        appointment_date,
        time(11, 30),
        tzinfo=CLINIC_TZ
    )

    # Act 1: create the original booking
    appointment = book_appointment(
        db=db_session,
        doctor_id=doctor.id,
        patient_id=patient.id,
        starts_at=original_time
    )

    appointment_id = appointment.id

    # Act 2: cancel the appointment
    cancelled = cancel_appointment(
        db=db_session,
        appointment_id=appointment_id,
        reason="Patient requested cancellation"
    )

    assert cancelled.status == "CANCELLED"

    # Act 3: attempt to reschedule a cancelled appointment
    with pytest.raises(HTTPException) as exc_info:
        reschedule_appointment(
            db=db_session,
            appointment_id=appointment_id,
            starts_at=new_time
        )

    # Assert: rescheduling is rejected
    assert exc_info.value.status_code == 409

    assert (
        exc_info.value.detail
        == "Cancelled appointments cannot be rescheduled"
    )

    # Verify the original cancellation remains intact
    db_session.refresh(appointment)

    assert appointment.status == "CANCELLED"
    assert appointment.cancellation_reason == (
        "Patient requested cancellation"
    )

    assert (
        appointment.starts_at.astimezone(CLINIC_TZ)
        == original_time
    )

    # Verify neither slot is occupied by this appointment
    available_slots = get_available_slots(
        db=db_session,
        doctor_id=doctor.id,
        requested_date=appointment_date
    )

    assert original_time.isoformat() in available_slots
    assert new_time.isoformat() in available_slots
    assert len(available_slots) == 16
