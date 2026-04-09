"""AI module — Claude-powered chatbot with tool calling for railway queries."""

import json
from datetime import date
from uuid import UUID

import anthropic
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_id
from app.config import settings
from app.database import get_db
from app.exceptions import BadRequestError

# Import services for tool execution
from app.modules.vacancy import find_vacant_seats
from app.modules.trains import search_trains, get_train_detail
from app.modules.stations import search_stations

# --- Schemas ---


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    tool_calls_made: list[str] = []


class NLSearchRequest(BaseModel):
    query: str  # e.g. "trains from vizag to raipur tomorrow"


# --- System Prompt ---

SYSTEM_PROMPT = """You are Railly AI, a helpful Indian Railways assistant. You help users:
1. Find vacant seats on trains (your MAIN specialty)
2. Search for trains between stations
3. Check train schedules and routes
4. Answer general Indian Railways questions

You know Indian railway terminology: PNR, RAC, WL (waitlist), berth types (LOWER, MIDDLE, UPPER, SIDE_LOWER, SIDE_UPPER), classes (SL=Sleeper, 3A=AC 3-tier, 2A=AC 2-tier, 1A=First AC, CC=Chair Car, 2S=Second Sitting), quotas (GN=General, TK=Tatkal).

Common station codes: VSKP=Visakhapatnam, R=Raipur, SC=Secunderabad/Hyderabad, NDLS=New Delhi, MAS=Chennai, BZA=Vijayawada, NGP=Nagpur, BSP=Bilaspur, HWH=Howrah/Kolkata, BPQ=Balharshah.

When users ask about vacant seats, always use the find_vacant_seats tool. Present results clearly — fully vacant seats first, then becomes_vacant and vacant_until seats. Be concise but helpful. Use Hindi/Telugu phrases naturally if the user does.

Today's date is {today}.
"""

# --- Tool Definitions ---

TOOLS = [
    {
        "name": "find_vacant_seats",
        "description": "Find vacant/available seats on a specific train for a journey segment. Shows fully vacant seats and partially vacant seats (ones that free up mid-journey or are free until someone boards). This is the MAIN tool.",
        "input_schema": {
            "type": "object",
            "properties": {
                "train_number": {"type": "string", "description": "Train number e.g. '18519'"},
                "journey_date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                "from_station": {"type": "string", "description": "Boarding station code e.g. 'VSKP'"},
                "to_station": {"type": "string", "description": "Deboarding station code e.g. 'R'"},
                "class_type": {"type": "string", "description": "Class: SL, 3A, 2A, 1A, CC, 2S", "default": "SL"},
                "berth_filter": {"type": "string", "description": "Optional berth filter: LOWER, UPPER, MIDDLE, SIDE_LOWER, SIDE_UPPER"},
            },
            "required": ["train_number", "journey_date", "from_station", "to_station"],
        },
    },
    {
        "name": "search_trains",
        "description": "Search for trains between two stations on a specific date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "from_station": {"type": "string", "description": "Source station code"},
                "to_station": {"type": "string", "description": "Destination station code"},
                "journey_date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
            },
            "required": ["from_station", "to_station", "journey_date"],
        },
    },
    {
        "name": "search_stations",
        "description": "Search for Indian railway stations by name, city, or code.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query (station name, city, or code)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_train_details",
        "description": "Get full details and schedule of a train by its number.",
        "input_schema": {
            "type": "object",
            "properties": {
                "train_number": {"type": "string", "description": "Train number"},
            },
            "required": ["train_number"],
        },
    },
]


# --- Tool Execution ---


async def execute_tool(tool_name: str, tool_input: dict, db: AsyncSession) -> str:
    """Execute a tool call and return the result as a string."""
    try:
        if tool_name == "find_vacant_seats":
            result = await find_vacant_seats(
                db=db,
                train_number=tool_input["train_number"],
                journey_date=date.fromisoformat(tool_input["journey_date"]),
                from_code=tool_input["from_station"],
                to_code=tool_input["to_station"],
                class_type=tool_input.get("class_type", "SL"),
                berth_filter=tool_input.get("berth_filter"),
            )
            return result.model_dump_json()

        elif tool_name == "search_trains":
            results = await search_trains(
                db=db,
                from_code=tool_input["from_station"],
                to_code=tool_input["to_station"],
                journey_date=date.fromisoformat(tool_input["journey_date"]),
            )
            return json.dumps([r.model_dump(mode="json") for r in results])

        elif tool_name == "search_stations":
            results = await search_stations(db, tool_input["query"])
            return json.dumps([{"code": s.code, "name": s.name, "city": s.city} for s in results])

        elif tool_name == "get_train_details":
            train = await get_train_detail(db, tool_input["train_number"])
            from app.modules.trains import TrainDetailResponse
            return TrainDetailResponse.model_validate(train).model_dump_json()

        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# --- Chat Service ---


async def chat(db: AsyncSession, message: str) -> ChatResponse:
    if not settings.anthropic_api_key:
        raise BadRequestError("Anthropic API key not configured. Set ANTHROPIC_API_KEY in .env")

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    messages = [{"role": "user", "content": message}]
    tool_calls_made = []

    # Initial request
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        system=SYSTEM_PROMPT.format(today=date.today().isoformat()),
        tools=TOOLS,
        messages=messages,
    )

    # Handle tool use loop
    while response.stop_reason == "tool_use":
        # Collect all tool uses and results
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                tool_calls_made.append(block.name)
                result = await execute_tool(block.name, block.input, db)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

        # Continue conversation with tool results
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            system=SYSTEM_PROMPT.format(today=date.today().isoformat()),
            tools=TOOLS,
            messages=messages,
        )

    # Extract text response
    reply = ""
    for block in response.content:
        if hasattr(block, "text"):
            reply += block.text

    return ChatResponse(reply=reply, tool_calls_made=tool_calls_made)


# --- Router ---

router = APIRouter(prefix="/ai", tags=["AI"])


@router.post("/chat", response_model=ChatResponse)
async def ai_chat(
    data: ChatRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    return await chat(db, data.message)
