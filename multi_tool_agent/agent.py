"""
Agent definition — the only file you need to edit to build your own agent.

To customise:
  • Change model, description, and instruction below.
  • Add or remove tools from the tools=[...] list.
  • Write new tool functions in the tools/ package (see tools/__init__.py).
  • Swap out the before_model_callback if you need a different context hook.
"""
from google.adk.agents import Agent

from .fhir_hook import extract_fhir_context
from .tools import (
    get_active_conditions,
    get_active_medications,
    get_patient_demographics,
    get_recent_observations,
)

root_agent = Agent(
    name="healthcare_fhir_agent",
    model="gemini-2.0-flash",
    description=(
        "A clinical assistant that queries a patient's FHIR health record "
        "to answer questions about demographics, medications, conditions, and observations."
    ),
    instruction=(
        "You are a clinical assistant with secure, read-only access to a patient's FHIR health record. "
        "Use the available tools to retrieve real data from the connected FHIR server when answering questions. "
        "Always fetch data using the tools — never make up or guess clinical information. "
        "Present medical information clearly and concisely, as if briefing a clinician. "
        "If a tool returns an error, explain what went wrong and suggest how to resolve it. "
        "If FHIR context is not available, let the caller know they need to include it in their request."
    ),
    tools=[
        get_patient_demographics,
        get_active_medications,
        get_active_conditions,
        get_recent_observations,
    ],
    # Runs before every LLM call.
    # Reads fhir_url, fhir_token, and patient_id from A2A message metadata
    # and writes them into session state so tools can call the FHIR server.
    before_model_callback=extract_fhir_context,
)
