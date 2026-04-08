# Railly - AI-Powered IRCTC Backend

## Context & Core Problem

**The real-world pain point**: You and your friends are traveling Vizag → Raipur. One friend's ticket isn't confirmed — they paid ~₹100 for a general/RAC ticket. They CAN board the train and sit in vacant seats, but **finding which seats are actually vacant for their journey is the nightmare**.

Why it's hard:
- Some passengers board AFTER you → their seat is vacant until their station
- Some passengers deboard BEFORE your destination → their seat becomes vacant mid-journey
- You need to know which seats are free for your ENTIRE segment, or when they free up

**How we solve it**: Once the railway **reservation chart is prepared** (~4 hrs before departure), the exact seat-wise passenger mapping is known. We fetch this real chart data, apply segment-overlap logic, and tell the user exactly which seats are vacant for their journey.

**This is backend only.** Frontend will be added later from a Figma project.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12+ |
| Framework | FastAPI (async, auto-docs, Pydantic v2) |
| Database | PostgreSQL (SQLAlchemy 2.0 async + Alembic) |
| Cache | Redis (vacancy caching, rate limiting) |
| AI | Anthropic Claude API via `anthropic` SDK |
| Auth | JWT (PyJWT) + bcrypt |
| Local Dev | Local PostgreSQL + Redis |

---

## Project Structure — One File Per Functionality

Each module is self-contained: **model + schema + service logic + router — all in one file.**

```
railly/
├── requirements.txt
├── alembic.ini
├── .env.example
├── .gitignore
│
├── alembic/
│   ├── env.py
│   └── versions/
│
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app creation, lifespan, router registration
│   ├── config.py             # Settings via Pydantic BaseSettings (.env loading)
│   ├── database.py           # Async engine, session factory, get_db dependency
│   ├── redis.py              # Redis pool, get_redis dependency
│   ├── auth.py               # JWT helpers, password hashing, auth dependency
│   ├── exceptions.py         # Custom exceptions + FastAPI error handlers
│   │
│   ├── models/               # SQLAlchemy models (one file per domain)
│   │   ├── __init__.py       # Base + re-exports all models (needed for Alembic)
│   │   ├── user.py           # User, UserPreference, SavedPassenger
│   │   ├── station.py        # Station
│   │   ├── train.py          # Train, TrainScheduleStop
│   │   ├── coach.py          # CoachLayout, TrainCoach, Seat
│   │   ├── seat_map.py       # SeatMap (THE CORE — seat-wise booking data from chart)
│   │   ├── booking.py        # Booking, BookingPassenger
│   │   ├── chart.py          # ReservationChart, ChartEntry
│   │   └── conversation.py   # AIConversation, AIMessage
│   │
│   ├── modules/              # One file per feature — schema + service + router
│   │   ├── __init__.py
│   │   ├── auth.py           # Register/login schemas, auth service, auth routes
│   │   ├── users.py          # Profile/passenger schemas, user service, user routes
│   │   ├── stations.py       # Station search schemas, station service, station routes
│   │   ├── trains.py         # Train search schemas, train service, train routes
│   │   ├── vacancy.py        # ★ THE CORE — vacancy schemas, segment-overlap algorithm, vacancy routes
│   │   ├── availability.py   # Class-wise availability schemas, service, routes
│   │   ├── bookings.py       # Booking schemas, booking service, booking routes
│   │   ├── pnr.py            # PNR schemas, PNR service, PNR routes
│   │   ├── charts.py         # Chart schemas, chart data fetcher, chart routes
│   │   └── ai.py             # AI client, tool definitions, chat service, AI routes
│   │
│   └── seed/
│       ├── __init__.py
│       ├── loader.py         # CLI seed command
│       ├── stations.json     # Indian railway stations
│       ├── trains.json       # Popular trains with schedules
│       ├── coaches.json      # Coach layouts per class
│       └── mock_charts.json  # Simulated chart data for testing vacancy finder
│
├── tests/
│   ├── conftest.py
│   ├── test_vacancy.py       # Extensive tests for the core feature
│   ├── test_auth.py
│   ├── test_trains.py
│   └── test_ai.py
│
└── scripts/
    ├── seed_db.py
    └── generate_mock_charts.py
```

**Each module file structure** (e.g., `modules/vacancy.py`):
```python
# --- Schemas (Pydantic) ---
class VacancyRequest(BaseModel): ...
class VacantSeat(BaseModel): ...
class VacancyResponse(BaseModel): ...

# --- Service Logic ---
async def find_vacant_seats(db, params): ...
async def find_best_seats(db, params): ...
async def get_vacancy_summary(db, params): ...

# --- Router ---
router = APIRouter(prefix="/vacancy", tags=["Vacancy"])

@router.get("/find")
async def find_vacant_seats_endpoint(...): ...
```

---

## Real-Time Chart Data — The Data Source

### How Indian Railway Charts Work
1. Reservation chart is **prepared ~4 hours before train departure**
2. Once prepared, we know EXACTLY: which seat → which passenger → boarding station → deboarding station
3. After chart, unconfirmed tickets become either CNF (confirmed) or cancelled
4. This chart data is our **primary source of truth** for vacancy

### Data Flow
```
Chart Released → Fetch Chart Data → Parse into seat_map table → Vacancy algorithm runs on seat_map
```

### Phase 1 (Now): Mock chart data
- `mock_charts.json` + `generate_mock_charts.py` simulate realistic chart data
- Seed script populates `seat_map` table from mock data

### Phase 2 (Production): Real chart data
- `modules/charts.py` will have a `ChartDataProvider` abstraction
- Swap `MockChartProvider` → `LiveChartProvider` (scraping/API)
- `seat_map` table gets populated from real chart releases
- Celery background task polls for chart preparation and auto-fetches

---

## Database Schema

### Core Table: `seat_map` (Powers the vacancy finder)

This table holds **one row per booked seat per journey date**, populated from chart data.

| Column | Type | Notes |
|---|---|---|
| id | UUID | PK |
| seat_id | UUID | FK → seats |
| train_id | UUID | FK → trains (denormalized for speed) |
| journey_date | DATE | |
| boarding_stop_seq | INTEGER | **Stop sequence where passenger boards** |
| deboarding_stop_seq | INTEGER | **Stop sequence where passenger deboards** |
| boarding_station_code | VARCHAR(10) | For display |
| deboarding_station_code | VARCHAR(10) | For display |
| status | VARCHAR(15) | BOOKED / RAC |
| passenger_name | VARCHAR(150) | From chart |
| pnr_number | VARCHAR(10) | |
| coach_label | VARCHAR(10) | Denormalized for speed |
| seat_number | INTEGER | Denormalized for speed |
| berth_type | VARCHAR(10) | Denormalized for speed |

**Index**: `(train_id, journey_date, boarding_stop_seq, deboarding_stop_seq)`

### Vacancy Algorithm (in `modules/vacancy.py`)

```
Input: train_number, date, from_station (VSKP), to_station (R), class (SL)

Step 1: Get user's stop_sequence range
  - from_seq = stop_sequence of VSKP for this train  (e.g., 1)
  - to_seq = stop_sequence of R for this train  (e.g., 12)

Step 2: Get all seats in requested class for this train

Step 3: Get all seat_map entries for this train + date where:
  boarding_stop_seq < to_seq AND deboarding_stop_seq > from_seq
  (these are the bookings that OVERLAP with user's journey)

Step 4: For each seat, classify:
  - No overlapping booking → FULLY_VACANT
  - Booking exists but deboarding_stop_seq < to_seq → BECOMES_VACANT_AT (that station)
  - Booking exists but boarding_stop_seq > from_seq → VACANT_UNTIL (that station)
  - Full overlap → OCCUPIED

Step 5: Sort: fully_vacant first, then by longest vacant duration
```

### Supporting Tables

**`stations`** — code (PK), name, city, state, zone, latitude, longitude

**`trains`** — id, number (UNIQUE), name, train_type, source_station_code, destination_station_code, runs_on_days, total_distance_km, is_active

**`train_schedule_stops`** — id, train_id (FK), station_code (FK), stop_sequence, arrival_time, departure_time, halt_minutes, distance_from_source_km, day_offset

**`coach_layouts`** — id, class_type, total_berths, layout_json (JSONB)

**`train_coaches`** — id, train_id (FK), coach_label, class_type, coach_layout_id (FK), coach_position

**`seats`** — id, train_coach_id (FK), seat_number, berth_type, compartment_number

**`users`** — id, email (UNIQUE), phone, password_hash, full_name, is_active, created_at, updated_at

**`user_preferences`** — id, user_id (FK UNIQUE), preferred_class, preferred_berth, home_station_code

**`saved_passengers`** — id, user_id (FK), full_name, age, gender, berth_preference

**`bookings`** — id, user_id (FK), pnr_number (UNIQUE), train_id (FK), journey_date, from_station_code, to_station_code, class_type, quota, booking_status, total_fare_inr, payment_status

**`booking_passengers`** — id, booking_id (FK), passenger_name, age, gender, current_status, coach_label, seat_number, berth_type

**`reservation_charts`** — id, train_id (FK), journey_date, chart_sequence, status (PENDING/PREPARED/FINAL), prepared_at, raw_data_json (JSONB — cached raw chart)

**`chart_entries`** — id, chart_id (FK), coach_label, seat_number, berth_type, passenger_name, from_station_code, to_station_code, booking_status, pnr_number

**`ai_conversations`** — id, user_id (FK), title, created_at
**`ai_messages`** — id, conversation_id (FK), role, content, tool_calls_json, created_at

---

## API Endpoints

### Vacancy — `/api/v1/vacancy` (THE CORE)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/find` | No | **Segment-aware vacant seat finder** |
| GET | `/find?berth=LOWER` | No | Filter by berth type |
| GET | `/find?group_size=3` | No | Find adjacent vacant seats for groups |
| GET | `/best` | No | AI-ranked best seats for your journey |
| GET | `/summary` | No | Quick count: fully vacant, becomes-vacant, vacant-until |

**`/find` response:**
```json
{
  "train": {"number": "18519", "name": "Visakhapatnam - Raipur Express"},
  "journey": {"from": "VSKP", "to": "R", "date": "2026-04-10"},
  "chart_status": "PREPARED",
  "summary": {
    "total_seats_in_class": 72,
    "fully_vacant": 18,
    "becomes_vacant_midway": 8,
    "vacant_until_midway": 5,
    "occupied": 41
  },
  "coaches": [
    {
      "coach": "S1",
      "fully_vacant": [
        {"seat": 5, "berth": "LOWER", "compartment": 1},
        {"seat": 33, "berth": "SIDE_LOWER", "compartment": 5}
      ],
      "becomes_vacant": [
        {
          "seat": 23, "berth": "LOWER",
          "vacant_from_station": {"code": "RJY", "name": "Rajahmundry"},
          "vacant_from_time": "14:30",
          "note": "Passenger deboarding at Rajahmundry"
        }
      ],
      "vacant_until": [
        {
          "seat": 45, "berth": "UPPER",
          "vacant_until_station": {"code": "BPQ", "name": "Balharshah"},
          "vacant_until_time": "22:15",
          "note": "Passenger boarding at Balharshah"
        }
      ]
    }
  ]
}
```

### Charts — `/api/v1/charts`
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/{train_number}/{date}` | No | Chart status + entries |
| GET | `/{train_number}/{date}/status` | No | Is chart prepared yet? |
| POST | `/{train_number}/{date}/refresh` | Yes | Trigger chart data re-fetch |

### Trains — `/api/v1/trains`
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/search` | No | `?from=VSKP&to=R&date=2026-04-10` |
| GET | `/{number}` | No | Train details |
| GET | `/{number}/schedule` | No | Full route with stops |

### Stations — `/api/v1/stations`
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/` | No | Search: `?q=vizag&limit=10` (fuzzy) |
| GET | `/{code}` | No | Station details |

### Availability — `/api/v1/availability`
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/` | No | Class-wise availability |
| GET | `/between-stations` | No | All trains for a route |

### Auth — `/api/v1/auth`
| POST | `/register` | No | Create account |
| POST | `/login` | No | JWT tokens |
| POST | `/refresh` | refresh | New access token |

### Users — `/api/v1/users`
| GET/PUT | `/me` | Yes | Profile |
| CRUD | `/me/passengers[/{id}]` | Yes | Saved passengers |

### Bookings — `/api/v1/bookings`
| POST | `/` | Yes | Create booking |
| GET | `/` | Yes | History |
| POST | `/{id}/cancel` | Yes | Cancel |

### PNR — `/api/v1/pnr`
| GET | `/{pnr_number}` | No | PNR status |

### AI — `/api/v1/ai`
| POST | `/chat` | Yes | AI chatbot (primary tool: find_vacant_seats) |
| POST | `/search` | Optional | NL search → structured results |

---

## AI Integration

**Primary AI tool**: `find_vacant_seats` — the AI knows how to find vacant seats via tool calling.

User: *"Vizag se Raipur, kal sleeper mein kaunsi seats khaali hain?"*
→ Claude extracts intent → calls `find_vacant_seats` tool → responds naturally

Other tools: `search_trains`, `check_availability`, `get_pnr_status`, `get_train_schedule`

---

## Implementation Order

### Phase 1: Foundation
1. **Project setup** — requirements.txt, .env.example, .gitignore, app/main.py, app/config.py
2. **Core infra** — database.py, redis.py, auth.py, exceptions.py
3. **Auth module** — modules/auth.py (User model, register/login, JWT)
4. **Users module** — modules/users.py (profile, preferences, saved passengers)

### Phase 2: Railway Data
5. **Stations module** — modules/stations.py (Station model, fuzzy search, seed data)
6. **Trains module** — modules/trains.py (Train + Schedule models, search, seed data)
7. **Coach & Seats** — coach.py model + seat layout seed data

### Phase 3: THE CORE — Vacancy Finder
8. **Chart module** — modules/charts.py (Chart model, chart data fetcher, chart routes)
9. **Seat map model** — models/seat_map.py (the core table, populated from chart data)
10. **Vacancy module** — modules/vacancy.py (segment-overlap algorithm, berth filter, group finder, routes)
11. **Mock chart data** — seed/mock_charts.json + generate_mock_charts.py + seed loader

### Phase 4: Supporting Features
12. **Availability module** — modules/availability.py
13. **Bookings module** — modules/bookings.py (simulated booking, PNR generation)
14. **PNR module** — modules/pnr.py

### Phase 5: AI
15. **AI module** — modules/ai.py (Claude client, tools, chat, NL search)

---

## Verification

1. `uvicorn app.main:app --reload` — Swagger docs at `/docs`
2. `python -m scripts.seed_db` — seed stations, trains, coaches, mock chart data
3. **Test the hero**:
   - `GET /api/v1/vacancy/find?train_number=18519&date=2026-04-10&from=VSKP&to=R&class=SL`
   - Verify: fully_vacant, becomes_vacant, vacant_until all correct
4. Test: berth filter (`?berth=LOWER`), group finder (`?group_size=3`)
5. Test AI: "Vizag to Raipur kal sleeper mein khaali seats batao"
6. `pytest -v`
