# Railly - AI-Powered IRCTC Backend Architecture Plan

## Context

Build a production-grade backend for **Railly** — an AI-powered Indian Railways application that makes finding train details, checking charts, and discovering vacant seats direct and easy. The user plans to deploy this for a real audience, so the architecture must support transitioning from seed data to real-time data. Frontend will come later from Figma.

**Key user emphasis**: Vacant seat finding should be dead simple and direct.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12+ |
| Framework | FastAPI 0.115+ (async, auto-docs, Pydantic v2) |
| Database | PostgreSQL 16 (via SQLAlchemy 2.0 async + Alembic) |
| Cache | Redis 7 (availability caching, rate limiting) |
| AI | Anthropic Claude API (`claude-sonnet-4-20250514`) via `anthropic` SDK |
| Auth | JWT (PyJWT) + bcrypt |
| Task Queue | Celery + Redis broker |
| Testing | pytest + pytest-asyncio + httpx |
| Local Dev | Local PostgreSQL + Redis (no Docker for now) |

---

## Project Structure

```
railly/
├── pyproject.toml
├── alembic.ini
├── .env.example
├── .gitignore
├── requirements.txt
│
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│
├── app/
│   ├── __init__.py
│   ├── main.py                       # FastAPI app, lifespan, middleware registration
│   ├── config.py                     # Pydantic BaseSettings
│   │
│   ├── core/
│   │   ├── __init__.py
│   │   ├── database.py               # Async engine, session, get_db dependency
│   │   ├── redis.py                  # Redis pool, get_redis dependency
│   │   ├── security.py               # JWT encode/decode, password hashing
│   │   ├── exceptions.py             # Custom exceptions (NotFound, Unauthorized, etc.)
│   │   └── error_handlers.py         # FastAPI exception handlers
│   │
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── auth.py                   # JWT bearer dependency
│   │   ├── rate_limiter.py           # Redis sliding window rate limiter
│   │   └── request_id.py             # X-Request-ID header injection
│   │
│   ├── models/                       # SQLAlchemy ORM models
│   │   ├── __init__.py
│   │   ├── base.py                   # DeclarativeBase + TimestampMixin (id, created_at, updated_at)
│   │   ├── user.py                   # User, UserPreference
│   │   ├── passenger.py              # SavedPassenger
│   │   ├── station.py                # Station
│   │   ├── train.py                  # Train, TrainScheduleStop
│   │   ├── coach.py                  # CoachLayout, TrainCoach, Seat
│   │   ├── availability.py           # SeatAvailability, SeatStatus
│   │   ├── booking.py                # Booking, BookingPassenger
│   │   ├── chart.py                  # ReservationChart, ChartEntry
│   │   ├── notification.py           # Notification
│   │   └── conversation.py           # AIConversation, AIMessage
│   │
│   ├── schemas/                      # Pydantic request/response models
│   │   ├── __init__.py
│   │   ├── common.py                 # PaginationParams, PaginatedResponse, ErrorResponse
│   │   ├── user.py                   # UserCreate, UserLogin, UserResponse, TokenPair
│   │   ├── passenger.py
│   │   ├── station.py
│   │   ├── train.py                  # TrainSearchRequest, TrainResponse, ScheduleResponse
│   │   ├── availability.py           # AvailabilityResponse, VacantSeatResponse
│   │   ├── booking.py                # BookingRequest, BookingResponse
│   │   ├── pnr.py                    # PNRStatusResponse
│   │   ├── chart.py                  # ChartSummaryResponse
│   │   ├── notification.py
│   │   └── ai.py                     # ChatRequest, ChatResponse
│   │
│   ├── routers/
│   │   ├── __init__.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── router.py             # Aggregates all v1 sub-routers
│   │       ├── auth.py
│   │       ├── users.py
│   │       ├── stations.py
│   │       ├── trains.py
│   │       ├── availability.py       # /vacant-seats is the star endpoint
│   │       ├── bookings.py
│   │       ├── pnr.py
│   │       ├── charts.py
│   │       ├── notifications.py
│   │       └── ai.py
│   │
│   ├── services/                     # Business logic
│   │   ├── __init__.py
│   │   ├── auth_service.py
│   │   ├── user_service.py
│   │   ├── station_service.py
│   │   ├── train_service.py
│   │   ├── availability_service.py   # Core: vacant seat finder logic
│   │   ├── booking_service.py
│   │   ├── pnr_service.py
│   │   ├── chart_service.py
│   │   ├── notification_service.py
│   │   └── ai_service.py
│   │
│   ├── ai/                           # AI/LLM modules
│   │   ├── __init__.py
│   │   ├── client.py                 # Anthropic SDK wrapper
│   │   ├── prompts.py                # System prompts, templates
│   │   ├── intent_parser.py          # NL query -> structured intent
│   │   ├── tools.py                  # Claude tool-use definitions
│   │   └── conversation_manager.py   # Multi-turn context
│   │
│   ├── workers/                      # Celery background tasks
│   │   ├── __init__.py
│   │   ├── celery_app.py
│   │   ├── notification_tasks.py
│   │   └── availability_sync.py
│   │
│   └── seed/                         # Seed data
│       ├── __init__.py
│       ├── loader.py                 # CLI seed command
│       ├── stations.json             # Major Indian railway stations (~500 initially)
│       ├── trains.json               # Popular trains with schedules (~100 initially)
│       └── coaches.json              # Standard coach layouts per class
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_routers/
│   └── test_services/
│
└── scripts/
    ├── seed_db.py
    └── generate_mock_availability.py
```

---

## Database Schema Design

### Users & Passengers

**`users`** — id (UUID PK), email (UNIQUE), phone, password_hash, full_name, is_active, is_verified, created_at, updated_at

**`user_preferences`** — id (UUID PK), user_id (FK users UNIQUE), preferred_class, preferred_berth, preferred_quota (default "GN"), home_station_code (FK stations), notifications_enabled

**`saved_passengers`** — id (UUID PK), user_id (FK users), full_name, age, gender (M/F/O), berth_preference, id_type, id_number (encrypted), is_primary

### Railway Data

**`stations`** — code (VARCHAR PK, e.g. "HYB", "NDLS"), name, city, state, zone, latitude, longitude, is_junction
- GIN index on `name` for trigram fuzzy search (pg_trgm extension)

**`trains`** — id (UUID PK), number (UNIQUE), name, train_type (RAJDHANI/SHATABDI/EXPRESS/SUPERFAST/MAIL), source_station_code (FK), destination_station_code (FK), runs_on_days ("1100110"), total_distance_km, has_pantry, is_active

**`train_schedule_stops`** — id (UUID PK), train_id (FK), station_code (FK), stop_sequence, arrival_time, departure_time, halt_minutes, distance_from_source_km, day_offset, platform_number
- Unique: (train_id, stop_sequence), (train_id, station_code)

### Coach & Seat Layout

**`coach_layouts`** — id (UUID PK), class_type (1A/2A/3A/SL/CC/2S/GN), coach_label_prefix, total_berths, total_compartments, layout_json (JSONB — full berth map)

**`train_coaches`** — id (UUID PK), train_id (FK), coach_label (e.g. "B1"), class_type, coach_layout_id (FK), coach_position

**`seats`** — id (UUID PK), train_coach_id (FK), seat_number, berth_type (LOWER/MIDDLE/UPPER/SIDE_LOWER/SIDE_UPPER/WINDOW/AISLE), compartment_number, is_accessible
- Unique: (train_coach_id, seat_number)

### Availability (THE Critical Tables)

**`seat_availability`** — Aggregate per class/date/segment:
- id, train_id (FK), journey_date, from_station_code, to_station_code, class_type, total_seats, available_seats, rac_count, waitlist_count, current_booking_status, fare_inr, tatkal_available, last_updated_at
- **Hot index**: (train_id, journey_date, class_type, from_station_code, to_station_code)

**`seat_status`** — Per-seat occupancy (powers vacant seat finder):
- id, seat_id (FK), journey_date, segment_from_code, segment_to_code, status (VACANT/BOOKED/RAC/BLOCKED), booking_id (FK nullable), passenger_name, boarding_station_code, deboarding_station_code
- Unique: (seat_id, journey_date, segment_from_code, segment_to_code)
- **Vacant seat logic**: A seat is vacant for segment A->B if no BOOKED row exists with overlapping stop_sequence ranges

### Bookings & PNR

**`bookings`** — id (UUID PK), user_id (FK), pnr_number (10-digit UNIQUE), train_id (FK), journey_date, from_station_code, to_station_code, class_type, quota (GN/TK/LD), booking_status (CONFIRMED/RAC/WAITLISTED/CANCELLED), total_fare_inr, payment_status, booked_at, cancelled_at, cancellation_charge_inr

**`booking_passengers`** — id, booking_id (FK), passenger_name, age, gender, berth_preference, current_status (CNF/RAC/WL/CAN), coach_label, seat_number, berth_type

### Charts

**`reservation_charts`** — id, train_id (FK), journey_date, chart_sequence (1st/2nd), status (PENDING/PREPARED/FINAL), prepared_at

**`chart_entries`** — id, chart_id (FK), coach_label, seat_number, berth_type, passenger_name, age, gender, from_station_code, to_station_code, booking_status, pnr_number

### Notifications & AI

**`notifications`** — id, user_id (FK), type (PNR_UPDATE/TRAIN_DELAY/CHART_PREPARED/WL_MOVEMENT), title, body, data_json (JSONB), is_read, created_at

**`ai_conversations`** — id, user_id (FK), title, created_at, updated_at

**`ai_messages`** — id, conversation_id (FK), role (user/assistant), content, tool_calls_json (JSONB), token_usage (JSONB), created_at

---

## API Endpoints

### Auth — `/api/v1/auth`
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/register` | No | Create account |
| POST | `/login` | No | Returns access + refresh tokens |
| POST | `/refresh` | refresh_token | New access token |
| POST | `/logout` | Yes | Blacklist refresh token |

### Users — `/api/v1/users`
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/me` | Yes | Profile |
| PUT | `/me` | Yes | Update profile |
| PUT | `/me/preferences` | Yes | Travel preferences |
| GET/POST/PUT/DELETE | `/me/passengers[/{id}]` | Yes | Saved passenger CRUD |

### Stations — `/api/v1/stations`
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/` | No | Search: `?q=hydera&limit=10` (fuzzy) |
| GET | `/{code}` | No | Station details |

### Trains — `/api/v1/trains`
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/search` | No | `?from=HYB&to=NDLS&date=2026-04-10` |
| GET | `/{number}` | No | Train details |
| GET | `/{number}/schedule` | No | Full route with stops/times |
| GET | `/{number}/running-status` | No | Live status (mock initially) |

### Availability — `/api/v1/availability` (Star Feature)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/` | No | Class-wise availability for a train/date/segment |
| GET | `/between-stations` | No | All trains availability for a route/date |
| GET | `/vacant-seats` | No | **Coach-wise vacant seat list with berth types** |
| GET | `/fare` | No | Fare calculation |

**`/vacant-seats` response format:**
```json
{
  "train_number": "12345",
  "train_name": "Telangana Express",
  "date": "2026-04-10",
  "class_type": "3A",
  "total_vacant": 42,
  "coaches": [
    {
      "coach_label": "B1",
      "vacant_count": 8,
      "seats": [
        {"seat_number": 5, "berth_type": "LOWER", "compartment": 1},
        {"seat_number": 6, "berth_type": "MIDDLE", "compartment": 1}
      ]
    }
  ]
}
```

### Bookings — `/api/v1/bookings`
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/` | Yes | Create booking (simulated) |
| GET | `/` | Yes | Booking history (paginated) |
| GET | `/{id}` | Yes | Booking details |
| POST | `/{id}/cancel` | Yes | Cancel with refund calculation |

### PNR — `/api/v1/pnr`
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/{pnr_number}` | No | PNR status with passenger-wise details |

### Charts — `/api/v1/charts`
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/{train_number}/{date}` | No | Chart status + full summary |
| GET | `/{train_number}/{date}/coach/{label}` | No | Coach-specific chart |
| GET | `/{train_number}/{date}/vacant` | No | Post-chart vacant berths |

### Notifications — `/api/v1/notifications`
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/` | Yes | Paginated notifications |
| PUT | `/{id}/read` | Yes | Mark read |
| PUT | `/read-all` | Yes | Mark all read |
| GET/PUT | `/preferences` | Yes | Notification settings |

### AI — `/api/v1/ai`
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/chat` | Yes | Send message, AI responds (uses tool calling for train lookups) |
| POST | `/search` | Optional | NL search: "trains from hyd to delhi tomorrow" -> structured results |
| GET | `/conversations` | Yes | List conversations |
| GET | `/conversations/{id}` | Yes | Full conversation |
| DELETE | `/conversations/{id}` | Yes | Delete conversation |

---

## AI Integration Design

### Claude Tool-Use Architecture
The AI chatbot uses Claude's native **tool calling** to interact with railway data:

**Tools defined in `app/ai/tools.py`:**
1. `search_trains` — Search trains between stations
2. `check_availability` — Check seat availability
3. `find_vacant_seats` — Find vacant seats (calls availability_service)
4. `get_pnr_status` — Check PNR
5. `get_train_schedule` — Train route/schedule
6. `calculate_fare` — Fare lookup
7. `get_chart_status` — Chart summary

**Flow**: User message -> Claude parses intent -> Claude calls tools -> Services execute DB queries -> Results fed back to Claude -> Claude generates natural language response

**System prompt** (`app/ai/prompts.py`): Railway-domain expert persona, knows Indian railway terminology (RAC, WL, berth types, quotas, zones).

### NL Search (`/ai/search`)
Direct natural language -> structured query:
- "Hyderabad to Delhi tomorrow AC 3-tier" -> `{from: "SC", to: "NDLS", date: "2026-04-08", class: "3A"}`
- Uses `intent_parser.py` for extraction

---

## Caching Strategy

| Data | Cache TTL | Key Pattern |
|---|---|---|
| Station list | 24 hours | `stations:all` |
| Train details | 12 hours | `train:{number}` |
| Seat availability | 5 minutes | `avail:{train}:{date}:{class}:{from}:{to}` |
| Vacant seats | 2 minutes | `vacant:{train}:{date}:{class}:{from}:{to}` |
| Train search results | 10 minutes | `search:{from}:{to}:{date}` |
| PNR status | 3 minutes | `pnr:{number}` |

---

## Data Strategy

### Phase 1 (Now): Seed Data
- `stations.json`: ~500 major Indian stations with codes, city, state, zone
- `trains.json`: ~100 popular trains with full schedules
- `coaches.json`: Standard coach layouts for all class types
- `generate_mock_availability.py`: Generates realistic availability patterns

### Phase 2 (Production): Real-Time Data
- Services use a **data provider abstraction** — swap `MockDataProvider` to `LiveDataProvider`
- Live provider integrates with third-party railway APIs
- No service/router code changes needed

---

## Implementation Order

### Phase 1: Foundation (Steps 1-4)
1. **Project setup** — pyproject.toml, requirements.txt, .env.example, .gitignore, app/main.py, app/config.py
2. **Core infrastructure** — database.py, redis.py, security.py, exceptions.py, error_handlers.py
3. **Auth system** — User model, auth schemas, auth_service, auth router, JWT middleware
4. **User management** — UserPreference, SavedPassenger models, user router

### Phase 2: Railway Core (Steps 5-8)
5. **Station & Train models** — Station, Train, TrainScheduleStop models + schemas + seed data
6. **Station & Train APIs** — station_service, train_service, routers, fuzzy search
7. **Coach & Seat layout** — CoachLayout, TrainCoach, Seat models + seed coach configs
8. **Availability system** — SeatAvailability, SeatStatus models + **vacant seat finder** + router

### Phase 3: Bookings & Charts (Steps 9-11)
9. **Booking flow** — Booking, BookingPassenger models, booking_service, PNR generation
10. **PNR status** — pnr_service, pnr router
11. **Chart system** — ReservationChart, ChartEntry models, chart_service, chart router

### Phase 4: AI & Notifications (Steps 12-14)
12. **AI client & tools** — Anthropic client wrapper, tool definitions, system prompts
13. **AI chat & search** — ai_service, conversation_manager, intent_parser, ai router
14. **Notifications** — Notification model, notification_service, Celery tasks

### Phase 5: Polish (Steps 15-16)
15. **Rate limiting & middleware** — Redis rate limiter, request ID, logging
16. **Seed data & scripts** — Complete seed data files, seed_db script, mock availability generator

---

## Verification Plan

1. `uvicorn app.main:app --reload` — Swagger docs at `/docs`
2. `python -m scripts.seed_db` — verify stations/trains populated
3. Auth flow: Register -> Login -> JWT-protected routes
4. Train search: `GET /api/v1/trains/search?from=HYB&to=NDLS&date=2026-04-10`
5. Vacant seats: `GET /api/v1/availability/vacant-seats?train_number=12345&date=2026-04-10&from=HYB&to=NDLS&class=3A`
6. Booking: Create -> PNR check -> Cancel
7. Chart: Summary for a train/date
8. AI chat: `POST /api/v1/ai/chat` with "Find me a train from Hyderabad to Delhi tomorrow"
9. `pytest -v` — all tests pass
