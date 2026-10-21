
from datetime import date

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Doctor
from app.services.availability import get_available_slots

from app.schemas import AppointmentCreate, AppointmentResponse
from app.services.appointments import book_appointment
from app.services.availability import CLINIC_TIMEZONE

from app.schemas import AppointmentCancel, AppointmentCancelResponse
from app.services.appointments import cancel_appointment

from app.schemas import AppointmentReschedule
from app.services.appointments import reschedule_appointment


from datetime import date, datetime, timezone
from sqlalchemy import select
from app.models import Doctor, Patient, Appointment

app = FastAPI(title="Savannah Clinic Booking API")


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/doctors/{doctor_id}/availability")
def doctor_availability(
    doctor_id: int,
    requested_date: date = Query(..., alias="date"),
    db: Session = Depends(get_db),
):
    # Verify the doctor exists
    doctor = db.get(Doctor, doctor_id)

    if doctor is None:
        raise HTTPException(
            status_code=404,
            detail="Doctor not found"
        )

    # Calculate available appointment slots
    slots = get_available_slots(
        db=db,
        doctor_id=doctor_id,
        requested_date=requested_date
    )

    return {
        "doctor_id": doctor_id,
        "date": requested_date.isoformat(),
        "available_slots": slots
    }



@app.post(
    "/appointments",
    response_model=AppointmentResponse,
    status_code=201
)
def create_appointment(
    payload: AppointmentCreate,
    db: Session = Depends(get_db)
):
    appointment = book_appointment(
        db=db,
        doctor_id=payload.doctor_id,
        patient_id=payload.patient_id,
        starts_at=payload.starts_at
    )

    return AppointmentResponse(
        id=appointment.id,
        doctor_id=appointment.doctor_id,
        patient_id=appointment.patient_id,
        starts_at=appointment.starts_at.astimezone(
            CLINIC_TIMEZONE
        ),
        status=appointment.status
    )




@app.patch(
    "/appointments/{appointment_id}/cancel",
    response_model=AppointmentCancelResponse
)
def cancel_existing_appointment(
    appointment_id: int,
    payload: AppointmentCancel,
    db: Session = Depends(get_db)
):
    appointment = cancel_appointment(
        db=db,
        appointment_id=appointment_id,
        reason=payload.reason
    )

    return AppointmentCancelResponse(
        id=appointment.id,
        doctor_id=appointment.doctor_id,
        patient_id=appointment.patient_id,
        starts_at=appointment.starts_at.astimezone(
            CLINIC_TIMEZONE
        ),
        status=appointment.status,
        cancellation_reason=appointment.cancellation_reason,
        cancelled_at=appointment.cancelled_at.astimezone(
            CLINIC_TIMEZONE
        )
    )



@app.patch(
    "/appointments/{appointment_id}/reschedule",
    response_model=AppointmentResponse
)
def reschedule_existing_appointment(
    appointment_id: int,
    payload: AppointmentReschedule,
    db: Session = Depends(get_db)
):
    appointment = reschedule_appointment(
        db=db,
        appointment_id=appointment_id,
        starts_at=payload.starts_at
    )

    return AppointmentResponse(
        id=appointment.id,
        doctor_id=appointment.doctor_id,
        patient_id=appointment.patient_id,
        starts_at=appointment.starts_at.astimezone(
            CLINIC_TIMEZONE
        ),
        status=appointment.status
    )



@app.get(
    "/patients/{patient_id}/appointments",
    response_model=list[AppointmentResponse]
)
def get_patient_appointments(
    patient_id: int,
    db: Session = Depends(get_db)
):
    # 1. Verify that the patient exists
    patient = db.get(Patient, patient_id)

    if patient is None:
        raise HTTPException(
            status_code=404,
            detail="Patient not found"
        )

    # 2. Retrieve upcoming active appointments
    appointments = db.scalars(
        select(Appointment)
        .where(
            Appointment.patient_id == patient_id,
            Appointment.status == "BOOKED",
            Appointment.starts_at >= datetime.now(timezone.utc)
        )
        .order_by(Appointment.starts_at.asc())
    ).all()

    # 3. Return appointments in clinic timezone
    return [
        AppointmentResponse(
            id=appointment.id,
            doctor_id=appointment.doctor_id,
            patient_id=appointment.patient_id,
            starts_at=appointment.starts_at.astimezone(
                CLINIC_TIMEZONE
            ),
            status=appointment.status
        )
        for appointment in appointments
    ]
