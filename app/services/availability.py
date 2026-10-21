
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Appointment, WorkingHours


CLINIC_TIMEZONE = ZoneInfo("Africa/Nairobi")
SLOT_DURATION = timedelta(minutes=30)


def get_available_slots(
    db: Session,
    doctor_id: int,
    requested_date: date
) -> list[str]:

    # 1. Determine the requested weekday
    weekday = requested_date.weekday()

    # 2. Find the doctor's working schedule
    working_hours = db.scalar(
        select(WorkingHours).where(
            WorkingHours.doctor_id == doctor_id,
            WorkingHours.day_of_week == weekday
        )
    )

    # Doctor does not work on this day
    if working_hours is None:
        return []

    # 3. Construct timezone-aware working hours
    start = datetime.combine(
        requested_date,
        working_hours.start_time,
        tzinfo=CLINIC_TIMEZONE
    )

    end = datetime.combine(
        requested_date,
        working_hours.end_time,
        tzinfo=CLINIC_TIMEZONE
    )

    # 4. Get active appointments in this period
    booked_times = db.scalars(
        select(Appointment.starts_at).where(
            Appointment.doctor_id == doctor_id,
            Appointment.status == "BOOKED",
            Appointment.starts_at >= start,
            Appointment.starts_at < end
        )
    ).all()

    booked_slots = {
        appointment_time.astimezone(CLINIC_TIMEZONE)
        for appointment_time in booked_times
    }

    # 5. Generate free 30-minute slots
    available_slots = []
    current_slot = start

    # Minimum notice of one hour
    earliest_booking = datetime.now(CLINIC_TIMEZONE) + timedelta(hours=1)

    while current_slot + SLOT_DURATION <= end:

        if current_slot >= earliest_booking and current_slot not in booked_slots:
            available_slots.append(current_slot.isoformat())

        current_slot += SLOT_DURATION
    return available_slots