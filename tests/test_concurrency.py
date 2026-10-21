
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta
from threading import Barrier
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import delete, select

from app.database import engine, SessionLocal
from app.models import Doctor, Patient, WorkingHours, Appointment
from app.services.appointments import book_appointment


CLINIC_TZ = ZoneInfo("Africa/Nairobi")


def test_concurrent_booking_only_one_succeeds():

    # 1. Confirm we are using the test database.
    with engine.connect() as connection:
        database_name = connection.exec_driver_sql(
            "SELECT current_database()"
        ).scalar_one()

    if database_name != "savannah_clinic_test":
        raise RuntimeError(
            "Concurrency test requires savannah_clinic_test"
        )

    # 2. Create committed records visible to both threads.
    unique_id = uuid4().hex

    with SessionLocal.begin() as db:
        doctor = Doctor(name="Concurrency Test Doctor")

        patient_a = Patient(
            name="Concurrency Patient A",
            email=f"concurrency-a-{unique_id}@example.com"
        )

        patient_b = Patient(
            name="Concurrency Patient B",
            email=f"concurrency-b-{unique_id}@example.com"
        )

        db.add_all([doctor, patient_a, patient_b])
        db.flush()

        doctor_id = doctor.id
        patient_a_id = patient_a.id
        patient_b_id = patient_b.id

        db.add(
            WorkingHours(
                doctor_id=doctor_id,
                day_of_week=0,
                start_time=time(9, 0),
                end_time=time(17, 0)
            )
        )

    # 3. Choose a future Monday at 09:00.
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

    # Synchronize the start of the two booking attempts.
    barrier = Barrier(2)

    def attempt_booking(patient_id):

        barrier.wait(timeout=10)

        # Each thread gets its own SQLAlchemy session.
        with SessionLocal() as db:
            try:
                appointment = book_appointment(
                    db=db,
                    doctor_id=doctor_id,
                    patient_id=patient_id,
                    starts_at=appointment_time
                )

                return 201, appointment.id

            except HTTPException as exc:
                return exc.status_code, None

    try:
        # 4. Execute both booking attempts concurrently.
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_a = executor.submit(
                attempt_booking, patient_a_id
            )

            future_b = executor.submit(
                attempt_booking, patient_b_id
            )

            result_a = future_a.result(timeout=20)
            result_b = future_b.result(timeout=20)

        # 5. Exactly one must succeed and one must conflict.
        status_codes = sorted([
            result_a[0],
            result_b[0]
        ])

        assert status_codes == [201, 409]

        # 6. Verify the database contains one active booking.
        with SessionLocal() as db:
            appointments = db.scalars(
                select(Appointment).where(
                    Appointment.doctor_id == doctor_id,
                    Appointment.starts_at == appointment_time,
                    Appointment.status == "BOOKED"
                )
            ).all()

            assert len(appointments) == 1

            assert appointments[0].patient_id in (
                patient_a_id,
                patient_b_id
            )

    finally:
        # 7. Clean up the committed test data.
        with SessionLocal.begin() as db:

            db.execute(
                delete(Appointment).where(
                    Appointment.doctor_id == doctor_id
                )
            )

            db.execute(
                delete(WorkingHours).where(
                    WorkingHours.doctor_id == doctor_id
                )
            )

            db.execute(
                delete(Patient).where(
                    Patient.id.in_([
                        patient_a_id,
                        patient_b_id
                    ])
                )
            )

            db.execute(
                delete(Doctor).where(
                    Doctor.id == doctor_id
                )
            )
