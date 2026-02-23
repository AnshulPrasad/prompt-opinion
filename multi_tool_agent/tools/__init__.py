"""
Tools package — all ADK tool functions available to the agent.

To add new tools:
  1. Create a new file in this directory (e.g. scheduling.py, imaging.py).
  2. Write your tool functions there (last param must be tool_context: ToolContext).
  3. Import and re-export them below.
  4. Add them to the tools=[...] list in agent.py.

Current tools
─────────────
  FHIR (fhir.py)
    get_patient_demographics   Patient name, DOB, gender, contacts
    get_active_medications     Active MedicationRequest resources
    get_active_conditions      Active Condition resources (problem list)
    get_recent_observations    Observation resources — vitals, labs, etc.
"""

from .fhir import (
    get_active_conditions,
    get_active_medications,
    get_patient_demographics,
    get_recent_observations,
)

__all__ = [
    "get_patient_demographics",
    "get_active_medications",
    "get_active_conditions",
    "get_recent_observations",
]
