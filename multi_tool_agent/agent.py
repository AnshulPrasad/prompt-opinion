"""
Agent definition — THIS IS THE FILE YOU CUSTOMIZE.

Steps to build your own agent on top of this template:
  1. Replace (or add to) the tool functions below with your own business logic.
  2. Update root_agent: change the model, description, instruction, and tools list.
  3. If you need per-request context (e.g. FHIR credentials, tenant info), read it
     from tool_context.state — the fhir_hook.py callback populates that state
     before the model is called.

Everything else (security, logging, FHIR metadata extraction, A2A wiring) is
handled by the other modules and does not need to change for most use cases.
"""
import datetime
import logging
from zoneinfo import ZoneInfo

from google.adk.agents import Agent
from google.adk.tools import ToolContext

from .fhir_hook import extract_fhir_context

logger = logging.getLogger(__name__)


# ── Tools ──────────────────────────────────────────────────────────────────────
# Each tool function is registered with the Agent below.
# Tool functions may read from tool_context.state to access per-request context
# (e.g. patient_id, fhir_url, fhir_token) that was injected by the FHIR hook.

def get_weather(city: str, tool_context: ToolContext) -> dict:
    """Retrieves the current weather report for a specified city."""
    patient_id = tool_context.state.get("patient_id", "unknown")
    logger.info("tool_get_weather_called city=%s patient_id=%s", city, patient_id)

    if city.lower() == "new york":
        return {
            "status": "success",
            "report": (
                f"The weather in New York is sunny with a temperature of 25 degrees "
                f"Celsius (77 degrees Fahrenheit). Patient context: {patient_id}"
            ),
        }
    return {
        "status": "error",
        "error_message": f"Weather information for '{city}' is not available.",
    }


def get_current_time(city: str, tool_context: ToolContext) -> dict:
    """Returns the current time in a specified city."""
    patient_id = tool_context.state.get("patient_id", "unknown")
    logger.info("tool_get_current_time_called city=%s patient_id=%s", city, patient_id)

    if city.lower() == "new york":
        tz  = ZoneInfo("America/New_York")
        now = datetime.datetime.now(tz)
        return {
            "status": "success",
            "report": f"The current time in {city} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}",
        }
    return {
        "status": "error",
        "error_message": f"Sorry, I don't have timezone information for {city}.",
    }


# ── Agent ──────────────────────────────────────────────────────────────────────

root_agent = Agent(
    name="weather_time_agent",
    model="gemini-2.0-flash",
    description="Agent to answer questions about the time and weather in a city.",
    instruction="You are a helpful agent who can answer user questions about the time and weather in a city.",
    tools=[get_weather, get_current_time],
    # extract_fhir_context runs before every LLM call and loads FHIR credentials
    # from the A2A message metadata into session state for the tools above.
    before_model_callback=extract_fhir_context,
)
