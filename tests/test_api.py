
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.models import Doctor, Patient, WorkingHours


CLINIC_TZ = ZoneInfo("Africa/Nairobi")


def test_booking_api_and_duplicate_conflict(client, db_session):

    # Arrange: create one doctor and two patients
    doctor = Doctor(name="API Test Doctor")

    patient_a = Patient(
        name="API Patient A",
        email="api-patient-a@example.com"
    )

    patient_b = Patient(
        name="API Patient B",
        email="api-patient-b@example.com"
    )

    db_session.add_all([doctor, patient_a, patient_b])
    db_session.flush()

    # Doctor works Mondays from 09:00 to 17:00
    db_session.add(
        WorkingHours(
            doctor_id=doctor.id,
            day_of_week=0,
            start_time=time(9, 0),
            end_time=time(17, 0)
        )
    )

    db_session.flush()

    # Choose a future Monday
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

    # Act 1: book through the REST API
    response = client.post(
        "/appointments",
        json={
            "doctor_id": doctor.id,
            "patient_id": patient_a.id,
            "starts_at": appointment_time.isoformat()
        }
    )

    # Assert: HTTP response is correct
    assert response.status_code == 201

    data = response.json()

    assert data["doctor_id"] == doctor.id
    assert data["patient_id"] == patient_a.id
    assert data["status"] == "BOOKED"

    assert (
        datetime.fromisoformat(data["starts_at"])
        == appointment_time
    )

    # Act 2: another patient requests the same slot
    duplicate_response = client.post(
        "/appointments",
        json={
            "doctor_id": doctor.id,
            "patient_id": patient_b.id,
            "starts_at": appointment_time.isoformat()
        }
    )

    # Assert: API returns HTTP 409 Conflict
    assert duplicate_response.status_code == 409

    assert duplicate_response.json()["detail"] == (
        "This appointment slot is already booked"
    )

    # Act 3: check the doctor's availability via HTTP
    availability_response = client.get(
        f"/doctors/{doctor.id}/availability",
        params={"date": appointment_date.isoformat()}
    )

    assert availability_response.status_code == 200

    available_slots = availability_response.json()[
        "available_slots"
    ]

    # The booked 09:00 slot should not be available
    assert appointment_time.isoformat() not in available_slots

    # Doctor originally had 16 slots; one is now booked
    assert len(available_slots) == 15




def test_cancellation_api_releases_slot(client, db_session):

    # Arrange: create a doctor and patient
    doctor = Doctor(name="API Cancellation Doctor")

    patient = Patient(
        name="API Cancellation Patient",
        email="api-cancellation@example.com"
    )

    db_session.add_all([doctor, patient])
    db_session.flush()

    # Doctor works on Mondays, 09:00 to 17:00
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

    # Act 1: book an appointment through the API
    booking_response = client.post(
        "/appointments",
        json={
            "doctor_id": doctor.id,
            "patient_id": patient.id,
            "starts_at": appointment_time.isoformat()
        }
    )

    assert booking_response.status_code == 201

    appointment_id = booking_response.json()["id"]

    # Act 2: cancel the appointment through the API
    cancellation_response = client.patch(
        f"/appointments/{appointment_id}/cancel",
        json={
            "reason": "Patient is unavailable"
        }
    )

    # Assert: cancellation succeeded
    assert cancellation_response.status_code == 200

    cancelled = cancellation_response.json()

    assert cancelled["id"] == appointment_id
    assert cancelled["status"] == "CANCELLED"

    assert (
        cancelled["cancellation_reason"]
        == "Patient is unavailable"
    )

    assert cancelled["cancelled_at"] is not None

    # Act 3: check availability through the API
    availability_response = client.get(
        f"/doctors/{doctor.id}/availability",
        params={"date": appointment_date.isoformat()}
    )

    assert availability_response.status_code == 200

    available_slots = availability_response.json()[
        "available_slots"
    ]

    # The cancelled 09:00 slot must be available again
    assert appointment_time.isoformat() in available_slots
    assert len(available_slots) == 16

    # Act 4: attempt to cancel again
    repeated_response = client.patch(
        f"/appointments/{appointment_id}/cancel",
        json={
            "reason": "Second cancellation attempt"
        }
    )

    # Assert: repeated cancellation is rejected
    assert repeated_response.status_code == 409

    assert repeated_response.json()["detail"] == (
        "Appointment is already cancelled"
    )



def test_rescheduling_api(client, db_session):

    # Arrange: create doctor and two patients
    doctor = Doctor(name="API Rescheduling Doctor")

    patient_a = Patient(
        name="API Reschedule Patient A",
        email="api-reschedule-a@example.com"
    )

    patient_b = Patient(
        name="API Reschedule Patient B",
        email="api-reschedule-b@example.com"
    )

    db_session.add_all([doctor, patient_a, patient_b])
    db_session.flush()

    # Doctor works Monday from 09:00 to 17:00
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
        appointment_date, time(11, 0), tzinfo=CLINIC_TZ
    )

    new_time = datetime.combine(
        appointment_date, time(11, 30), tzinfo=CLINIC_TZ
    )

    occupied_time = datetime.combine(
        appointment_date, time(12, 0), tzinfo=CLINIC_TZ
    )

    # Book Patient A at 11:00
    response_a = client.post(
        "/appointments",
        json={
            "doctor_id": doctor.id,
            "patient_id": patient_a.id,
            "starts_at": original_time.isoformat()
        }
    )

    assert response_a.status_code == 201
    appointment_a_id = response_a.json()["id"]

    # Book Patient B at 12:00
    response_b = client.post(
        "/appointments",
        json={
            "doctor_id": doctor.id,
            "patient_id": patient_b.id,
            "starts_at": occupied_time.isoformat()
        }
    )

    assert response_b.status_code == 201
    appointment_b_id = response_b.json()["id"]

    # Act 1: successfully reschedule A to 11:30
    reschedule_response = client.patch(
        f"/appointments/{appointment_a_id}/reschedule",
        json={"starts_at": new_time.isoformat()}
    )

    assert reschedule_response.status_code == 200

    updated = reschedule_response.json()

    assert updated["id"] == appointment_a_id
    assert updated["status"] == "BOOKED"

    assert (
        datetime.fromisoformat(updated["starts_at"])
        == new_time
    )

    # Act 2: attempt to move A into B's occupied slot
    conflict_response = client.patch(
        f"/appointments/{appointment_a_id}/reschedule",
        json={"starts_at": occupied_time.isoformat()}
    )

    # Verify the API rejects the conflicting change
    assert conflict_response.status_code == 409

    assert conflict_response.json()["detail"] == (
        "The requested appointment slot is already booked"
    )

    # Verify availability after both requests
    availability_response = client.get(
        f"/doctors/{doctor.id}/availability",
        params={"date": appointment_date.isoformat()}
    )

    assert availability_response.status_code == 200

    available_slots = availability_response.json()[
        "available_slots"
    ]

    # Original 11:00 slot has been released
    assert original_time.isoformat() in available_slots

    # Patient A still occupies 11:30
    assert new_time.isoformat() not in available_slots

    # Patient B still occupies 12:00
    assert occupied_time.isoformat() not in available_slots

    # Two active bookings mean 14 free slots remain
    assert len(available_slots) == 14




def test_patient_appointments_api(client, db_session):

    # Arrange: create doctor and three patients
    doctor = Doctor(name="Patient Appointments Doctor")

    patient_a = Patient(
        name="Patient A",
        email="appointments-a@example.com"
    )

    patient_b = Patient(
        name="Patient B",
        email="appointments-b@example.com"
    )

    patient_c = Patient(
        name="Patient C",
        email="appointments-c@example.com"
    )

    db_session.add_all([
        doctor,
        patient_a,
        patient_b,
        patient_c
    ])

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

    def appointment_time(hour, minute=0):
        return datetime.combine(
            appointment_date,
            time(hour, minute),
            tzinfo=CLINIC_TZ
        )

    # Helper: create appointments through the REST API
    def book(patient_id, starts_at):
        response = client.post(
            "/appointments",
            json={
                "doctor_id": doctor.id,
                "patient_id": patient_id,
                "starts_at": starts_at.isoformat()
            }
        )

        assert response.status_code == 201

        return response.json()["id"]

    # Create Patient A's later booking first
    later_id = book(
        patient_a.id,
        appointment_time(12)
    )

    # Create Patient A's earlier booking second
    earlier_id = book(
        patient_a.id,
        appointment_time(9)
    )

    # Create an appointment for another patient
    other_patient_id = book(
        patient_b.id,
        appointment_time(10)
    )

    # Create and cancel another Patient A appointment
    cancelled_id = book(
        patient_a.id,
        appointment_time(11)
    )

    cancellation_response = client.patch(
        f"/appointments/{cancelled_id}/cancel",
        json={"reason": "Patient unavailable"}
    )

    assert cancellation_response.status_code == 200

    # Act 1: retrieve Patient A's appointments
    response = client.get(
        f"/patients/{patient_a.id}/appointments"
    )

    assert response.status_code == 200

    appointments = response.json()

    # Exactly two active appointments
    assert len(appointments) == 2

    # Verify chronological ordering
    assert [item["id"] for item in appointments] == [
        earlier_id,
        later_id
    ]

    # Verify start times
    assert datetime.fromisoformat(
        appointments[0]["starts_at"]
    ) == appointment_time(9)

    assert datetime.fromisoformat(
        appointments[1]["starts_at"]
    ) == appointment_time(12)

    # Verify status and ownership
    for item in appointments:
        assert item["patient_id"] == patient_a.id
        assert item["status"] == "BOOKED"

    # Act 2: Patient B sees only their appointment
    response_b = client.get(
        f"/patients/{patient_b.id}/appointments"
    )

    assert response_b.status_code == 200
    assert len(response_b.json()) == 1
    assert response_b.json()[0]["id"] == other_patient_id

    # Act 3: existing patient without appointments
    response_c = client.get(
        f"/patients/{patient_c.id}/appointments"
    )

    assert response_c.status_code == 200
    assert response_c.json() == []

    # Act 4: nonexistent patient
    missing_response = client.get(
        "/patients/999999/appointments"
    )

    assert missing_response.status_code == 404
    assert missing_response.json()["detail"] == (
        "Patient not found"
    )
