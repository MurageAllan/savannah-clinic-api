
from datetime import datetime, time

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# Doctor model
class Doctor(Base):
    __tablename__ = "doctors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))


# Patient model
class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True
    )


# Doctor working schedule
class WorkingHours(Base):
    __tablename__ = "working_hours"

    id: Mapped[int] = mapped_column(primary_key=True)

    doctor_id: Mapped[int] = mapped_column(
        ForeignKey("doctors.id"),
        nullable=False
    )

    day_of_week: Mapped[int]

    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)

    __table_args__ = (
        UniqueConstraint(
            "doctor_id",
            "day_of_week",
            name="uq_doctor_working_day"
        ),
        CheckConstraint(
            "day_of_week BETWEEN 0 AND 6",
            name="ck_valid_day"
        ),
        CheckConstraint(
            "start_time < end_time",
            name="ck_valid_working_hours"
        ),
    )


# Appointment model
class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(primary_key=True)

    doctor_id: Mapped[int] = mapped_column(
        ForeignKey("doctors.id"),
        nullable=False
    )

    patient_id: Mapped[int] = mapped_column(
        ForeignKey("patients.id"),
        nullable=False
    )

    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(16),
        default="BOOKED",
        server_default="BOOKED"
    )

    cancellation_reason: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True
    )

    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('BOOKED', 'CANCELLED')",
            name="ck_appointment_status"
        ),
        Index(
            "uq_active_doctor_slot",
            "doctor_id",
            "starts_at",
            unique=True,
            postgresql_where=text("status = 'BOOKED'")
        ),
    )
