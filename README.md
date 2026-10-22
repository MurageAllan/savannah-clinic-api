# Savannah Clinic Appointment API

Backend Developer Take-Home Assessment for Savannah Informatics Limited. A REST API for managing a clinic's doctor availability and 30-minute appointments, with protection against double booking, cancellation, rescheduling, automated tests, and continuous deployment.

Repository: https://github.com/MurageAllan/savannah-clinic-api 
Live health check: https://clinic.kashflowsacco.co.ke/health 
Interactive API documentation: https://clinic.kashflowsacco.co.ke/docs 
OpenAPI schema: https://clinic.kashflowsacco.co.ke/openapi.json

Assessment/demo application. The public API has no user authentication or authorization. I used synthetic patient information only, it is not intended to handle real clinical or personal records.

# Technology stack

- Python 3.12 / FastAPI for HTTP endpoints, request validation and OpenAPI documentation.
- SQLAlchemy 2 for persistence and transaction management.
- PostgreSQL 16 for relational data, constraints, row locks and race-condition protection.
- Alembic for reproducible database schema migrations.
- pytest / FastAPI TestClient for service, API and concurrency integration testing.
- GitHub Actions for pull-request CI and deployment after successful checks on main branch.
- Contabo Ubuntu VPS, systemd, Uvicorn, Nginx.

# Features and business rules

- Five doctors with fixed weekly hours, seeded Monday–Friday, 09:00–17:00 (Africa/Nairobi).
- Thirty-minute bookable slots, with no appointments outside a doctor's working hours.
- Booking and rescheduling require timezone-aware timestamps.
- Double-booking protection for each doctor's active appointment at a particular start time.
- Cancellation keeps an audit trail (cancellation_reason and cancelled_at) and makes the original slot available again.
- Already-cancelled appointments cannot be cancelled or rescheduled again.
- Patient appointment listing returns upcoming, BOOKED appointments sorted from earliest to latest.
- Times returned by the API are normalized to Africa/Nairobi (UTC+03:00).

# API endpoints

| Method | Route | Description | Success status |
| GET | /health | Application liveness check | 200 |
| GET | /doctors/{doctor_id}/availability?date=YYYY-MM-DD | Available 30-minute slots | 200 |
| POST | /appointments | Book an appointment | 201 |
| PATCH | /appointments/{appointment_id}/cancel | Cancel a booking, with reason | 200 |
| PATCH | /appointments/{appointment_id}/reschedule | Move a booking to an available slot | 200 |
| GET | /patients/{patient_id}/appointments | Upcoming active appointments, in chronological order | 200 |

Typical error responses include 400 for invalid times or business rules, 404 for missing records, 409 for an occupied slot or an invalid appointment state, and 422 for invalid requests or timezone-less datetimes. See /docs for request and response schemas.

# Example requests

Use an existing seeded doctor and patient, and replace the date with a **future Monday** at least one hour away. Times include the Nairobi timezone offset.

bash
# Check availability
curl 'https://clinic.kashflowsacco.co.ke/doctors/1/availability?date=2030-01-07'

# Book a slot (illustrative future date; check availability first)
curl -X POST 'https://clinic.kashflowsacco.co.ke/appointments' \
  -H 'Content-Type: application/json' \
  -d '{"doctor_id":1,"patient_id":1,"starts_at":"2030-01-07T09:00:00+03:00"}'

# Cancel: replace 1 with the actual appointment ID
curl -X PATCH 'https://clinic.kashflowsacco.co.ke/appointments/1/cancel' \
  -H 'Content-Type: application/json' \
  -d '{"reason":"Patient unavailable"}'

# Reschedule: replace 1 with an active appointment ID
curl -X PATCH 'https://clinic.kashflowsacco.co.ke/appointments/1/reschedule' \
  -H 'Content-Type: application/json' \
  -d '{"starts_at":"2030-01-07T09:30:00+03:00"}'


The example date is for illustration; use the application's current availability before booking. A cancellation request and a rescheduling request operate on different appointment states—do not reschedule an appointment you have already cancelled.

# Architecture

Client / Swagger UI
        |
        v
Nginx (HTTPS, public domain)
        |
        v
Uvicorn + FastAPI (127.0.0.1:8090, systemd)
        |
        +-- app/main.py                 HTTP routes / dependency injection
        +-- app/schemas.py              Pydantic request and response models
        +-- app/services/               Booking and availability rules
        +-- app/database.py             SQLAlchemy engine and session lifecycle
        +-- app/models.py               ORM models and database constraints
        |
        v
PostgreSQL (doctors, patients, working_hours, appointments)

Alembic migrations -> database schema
pytest + PostgreSQL test DB -> automated verification
GitHub Actions -> CI -> SSH deployment -> service restart -> health check


Database relationships: each appointment references one doctor and one patient; each doctor has per-weekday working-hours records. Appointment status is BOOKED or CANCELLED.

# Concurrency and transactional integrity

A PostgreSQL partial unique index on (doctor_id, starts_at) WHERE status = BOOKED guarantees that only one active appointment can occupy any doctor's start time, including when requests arrive from different processes. The booking service converts the relevant Integrity Error to HTTP 409 Conflict.

Cancellation and rescheduling lock the existing appointment row with SELECT ... FOR UPDATE to coordinate updates to the same record. A failed reschedule rolls back its transaction so that the original appointment remains intact. Cancellation is a status update rather than a physical delete, allowing the same slot to be booked again while preserving historical information.

Availability is computed from working hours and active appointments rather than stored in a separate slot table. This keeps the data model small and avoids keeping two sets of availability records synchronized.

# Local setup

# Prerequisites

Python 3.12, PostgreSQL 16 (or a compatible supported version), Git and a virtual environment.

bash
git clone https://github.com/MurageAllan/savannah-clinic-api.git
cd savannah-clinic-api
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
chmod 600 .env


Edit .env with the PostgreSQL credentials for your local environment. Create an empty PostgreSQL database named savannah_clinic, and grant the configured role ownership/permissions. Never commit .env.

bash
python -m alembic upgrade head
python seed.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000


The seed script adds five doctors, weekday schedules and sample patients for demonstration. Visit http://127.0.0.1:8000/docs to try the API.

# Configuration

| Environment variable | Description | Example |
| --- | --- | --- |
| DB_HOST | PostgreSQL hostname | 127.0.0.1 |
| DB_PORT | PostgreSQL port | 5432 |
| DB_NAME | Database name | savannah_clinic |
| DB_USER | PostgreSQL role | `savannah_user` |
| DB_PASSWORD | Database password | Set locally |

# Testing

A separate PostgreSQL database named savannah_clinic_test is required. The same Alembic migrations must be applied to that database before testing.

bash
DB_NAME=savannah_clinic_test python -m alembic upgrade head
DB_NAME=savannah_clinic_test python -m pytest tests/ -v


The suite contains 16 integration tests, covering valid booking, duplicates, time validation, cancellation, release of slots, repeated cancellation, successful and conflicting rescheduling, cancelled-state protection, patient filtering and sorting, REST responses and simultaneous booking attempts.

Most tests use an outer transaction plus SQLAlchemy savepoints to roll back their changes. The concurrency test uses **separate committed connections** and explicit cleanup because sharing one test transaction would not represent independent requests. Fixtures and concurrency tests check that they are connected to savannah_clinic_test.

A Starlette/HTTP client deprecation warning may appear with the pinned dependency versions; it does not indicate a failed test.

# CI/CD and deployment

The workflow is defined in .github/workflows/ci.yml.

CI: Pull requests to main and pushes to main provision PostgreSQL 16, install dependencies, run migrations and execute pytest.

CD: A successful CI job on a push to main permits a dependent job to connect to the Contabo VPS over SSH as the non-root savannah user. It fast-forwards the repository, installs dependencies, applies Alembic migrations to savannah_clinic, restarts savannah-clinic.service` via narrowly scoped sudo access and checks the internal and public HTTPS health endpoints.

Secrets such as VPS_SSH_KEY and VPS_KNOWN_HOSTS are stored in GitHub Actions Secrets. Database credentials remain in the server's excluded .env file. The Uvicorn service binds only to 127.0.0.1:8090, with Nginx providing public HTTPS access.

> Because CI also runs on direct pushes to main, automatic deployment is not technically merge-only. Protecting main with pull-request requirements ensures changes are reviewed and pass CI before reaching the deployment branch.

# Design choices and trade-offs

| Choice | Why | Limitation | improvement |
| PostgreSQL constraint rather than in-memory locking | Protects against double bookings across workers and processes | Does not replace broader monitoring or rate limits |
| Dynamically calculated slots | Avoids extra persistent slot records | One continuous working interval per doctor per weekday; no holidays or breaks modeled |
| Service functions separated from routes | Keeps business rules testable | A larger system might introduce repository interfaces and stronger domain abstractions |
| Soft cancellation | Preserves cancellation history and frees slots | No full audit/event-history subsystem |
| Single Uvicorn service under systemd | Simple, appropriate for a small assignment | Restart-based deployment has a brief interruption; no staged or zero-downtime rollout |
| GitHub Actions + existing VPS | Reproducible tests and practical cloud delivery | No infrastructure-as-code or disaster-recovery automation |

Deliberately out of scope: authentication/authorization, patient ownership enforcement, rate limiting, holiday schedules, notifications, time-off management, appointment duration beyond 30 minutes, and production patient-data controls. The publicly hosted instance should only contain synthetic demonstration data.

# AI usage reflection

AI assistance (ChatGPT) was used for architectural discussion, implementation examples, SQLAlchemy/Alembic guidance, testing patterns, debugging support, CI/CD workflow design and explanations of technical trade-offs. Suggested changes were applied and verified through shell commands, database queries, direct API requests and automated tests rather than assumed correct.

A mistake identified and corrected: An AI-assisted change to availability calculation left the current_slot += SLOT_DURATION increment outside the while loop. This caused the availability request to hang. The problem was investigated by inspecting the numbered source lines and correcting the loop indentation, then rerunning the endpoint and later the automated suite. It illustrates why generated code must be reviewed and executed, not just accepted.

Two decisions made by the developer:

1. Python for the assessment implementation. Python was selected for the backend solution, with FastAPI used to provide REST endpoints and automatic OpenAPI documentation.
2. Reuse of an existing Contabo Ubuntu VPS. Rather than provisioning another provider or introducing a container orchestration platform, the deployment reused an available cloud VPS with PostgreSQL and Nginx, adding a separate non-root app user, systemd service, local-only port and dedicated domain.

Where AI help could be improved: Proposed snippets should be validated against exact existing files and imports before being copied, especially for whitespace-sensitive Python code. The project could also add automated formatting/linting, deterministic clock-freezing tests for time boundaries, HTTP-level concurrency load tests, and security controls before any real-world use.

# Assessment deliverables

- Public source repository: https://github.com/MurageAllan/savannah-clinic-api
- Live health endpoint: https://clinic.kashflowsacco.co.ke/health
- Interactive endpoint documentation: https://clinic.kashflowsacco.co.ke/docs
- Automated workflow: https://github.com/MurageAllan/savannah-clinic-api/actions/workflows/ci.yml
