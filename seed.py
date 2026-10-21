
from datetime import time

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Doctor, Patient, WorkingHours


doctors = [
    "Dr. Kamau",
    "Dr. Njeri",
    "Dr. Otieno",
    "Dr. Amina",
    "Dr. Hassan",
]

patients = [
    ("John Doe", "john@example.com"),
    ("Jane Doe", "jane@example.com"),
]


def seed_database():
    with SessionLocal.begin() as session:

        # Create doctors and their working hours
        for name in doctors:
            doctor = session.scalar(
                select(Doctor).where(Doctor.name == name)
            )

            if doctor is None:
                doctor = Doctor(name=name)
                session.add(doctor)
                session.flush()

            # Monday (0) through Friday (4)
            for day in range(5):
                existing = session.scalar(
                    select(WorkingHours).where(
                        WorkingHours.doctor_id == doctor.id,
                        WorkingHours.day_of_week == day
                    )
                )

                if existing is None:
                    session.add(
                        WorkingHours(
                            doctor_id=doctor.id,
                            day_of_week=day,
                            start_time=time(9, 0),
                            end_time=time(17, 0)
                        )
                    )

        # Create sample patients
        for name, email in patients:
            existing = session.scalar(
                select(Patient).where(
                    Patient.email == email
                )
            )

            if existing is None:
                session.add(
                    Patient(name=name, email=email)
                )

    print("Database seeding completed successfully.")


if __name__ == "__main__":
    seed_database()
