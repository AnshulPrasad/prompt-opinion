"""
healthcare_agent — Agent definition.

This agent has read-only access to a patient's FHIR R4 record.
FHIR credentials (server URL, bearer token, patient ID) are injected via the
A2A message metadata by the caller (e.g. Prompt Opinion) and extracted into
session state by extract_fhir_context before every LLM call.

To customise:
  • Change model, description, and instruction below.
  • Add or remove tools from the tools=[...] list.
  • Add new FHIR tools in shared/tools/fhir.py and export from shared/tools/__init__.py.
  • Add non-FHIR tools in shared/tools/ or locally in a tools/ folder here.
"""
from google.adk.agents import Agent

from shared.fhir_hook import extract_fhir_context
from shared.model_config import gemini_flash_with_retries
from shared.tools import (
    get_active_conditions,
    get_active_medications,
    get_patient_demographics,
    get_recent_observations,
    get_allergy_intolerance_resources_full,
    get_care_plan_resources_full,
    get_diagnostic_report_resources_full,
    get_document_reference_resources_full,
    get_encounter_resources_full,
    get_imaging_study_resources_full,
    get_immunization_resources_full,
    get_medication_statement_resources_full,
    get_procedure_resources_full,
    get_service_request_resources_full,
)

root_agent = Agent(
    name="healthcare_fhir_agent",
    model=gemini_flash_with_retries(),
    description=(
        "A clinical assistant that queries a patient's FHIR health record "
        "to answer questions about demographics, medications, conditions, observations, "
        "allergies, encounters, procedures, reports, imaging, immunizations, "
        "care plans, medication history, and service requests."
    ),
    instruction=(
        "You are a clinical assistant with secure, read-only access to a patient's FHIR health record. "
        "Use the available tools to retrieve real data from the connected FHIR server when answering questions. "
        "Always fetch data using the tools — never make up or guess clinical information. "
        "Use the tools that match the user's request as directly as possible. "
        "Prefer the summary tools for concise answers: demographics, active medications, active conditions, "
        "and recent observations. Use the full-resource tools when the question asks for complete chart detail "
        "or resource-specific review such as allergies, encounters, procedures, reports, notes, immunizations, "
        "care plans, medication statements, service requests, or imaging. "
        "For broad chart-review requests, gather the relevant sections systematically: demographics, medications, "
        "conditions, observations, then the requested full-resource sections. "
        "Do not call multiple overlapping tools unless they add distinct value. For example, use DocumentReference "
        "for clinical notes and attached documents, and use DiagnosticReport for reports/results. "
        "For broad chart-review requests, return a consistent clinician-friendly structure in this exact order when available: "
        "1. Demographics 2. Active Medications 3. Active Conditions 4. Recent Observations 5. Allergies "
        "6. Encounters 7. Procedures 8. Diagnostic Reports 9. Document References / Clinical Notes "
        "10. Immunizations 11. Care Plans 12. Medication Statements 13. Service Requests 14. Imaging Studies. "
        "If a section returns no records, say 'no records found' for that section. If one tool returns an error, "
        "continue with the remaining relevant tools and clearly note the affected section instead of failing the whole answer. "
        "Present medical information clearly and concisely, as if briefing a clinician. "
        "If a tool returns an error, explain what went wrong and suggest how to resolve it. "
        "If FHIR context is not available, let the caller know they need to include it in their request."
    ),
    tools=[
        get_patient_demographics,
        get_active_medications,
        get_active_conditions,
        get_recent_observations,
        get_allergy_intolerance_resources_full,
        get_encounter_resources_full,
        get_procedure_resources_full,
        get_diagnostic_report_resources_full,
        get_document_reference_resources_full,
        get_immunization_resources_full,
        get_care_plan_resources_full,
        get_medication_statement_resources_full,
        get_service_request_resources_full,
        get_imaging_study_resources_full,
    ],
    # Runs before every LLM call.
    # Reads fhir_url, fhir_token, and patient_id from A2A message metadata
    # and writes them into session state so tools can call the FHIR server.
    before_model_callback=extract_fhir_context,
)
