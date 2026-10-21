
from datetime import datetime

from pydantic import BaseModel


class AppointmentCreate(BaseModel):
    doctor_id: int
    patient_id: int
    starts_at: datetime


class AppointmentResponse(BaseModel):
    id: int
    doctor_id: int
    patient_id: int
    starts_at: datetime
    status: str



class AppointmentCancel(BaseModel):
    reason: str


class AppointmentCancelResponse(AppointmentResponse):
    cancellation_reason: str
    cancelled_at: datetime



class AppointmentReschedule(BaseModel):
    starts_at: datetime
