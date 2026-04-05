"""
Shared tools catalogue — re-exports all tool functions available in this library.

FHIR tools (fhir.py)
────────────────────
  get_patient_demographics   Patient name, DOB, gender, contacts
  get_active_medications     Active MedicationRequest resources
  get_active_conditions      Active Condition resources (problem list)
  get_recent_observations    Observation resources — vitals, labs, etc.
  get_allergy_intolerance_resources_full AllergyIntolerance resources
  get_encounter_resources_full           Encounter resources
  get_procedure_resources_full           Procedure resources
  get_diagnostic_report_resources_full   DiagnosticReport resources
  get_document_reference_resources_full  DocumentReference resources
  get_immunization_resources_full        Immunization resources
  get_care_plan_resources_full           CarePlan resources
  get_medication_statement_resources_full MedicationStatement resources
  get_service_request_resources_full     ServiceRequest resources
  get_imaging_study_resources_full       ImagingStudy resources

To add new shared tools:
  1. Create a new file in shared/tools/ (e.g. scheduling.py).
  2. Write your tool functions there (last param must be tool_context: ToolContext).
  3. Import and re-export them below.
  4. Add them to the tools=[...] list in whichever agent(s) need them.
"""

from .fhir import (
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

__all__ = [
    "get_patient_demographics",
    "get_active_medications",
    "get_active_conditions",
    "get_recent_observations",
    "get_allergy_intolerance_resources_full",
    "get_encounter_resources_full",
    "get_procedure_resources_full",
    "get_diagnostic_report_resources_full",
    "get_document_reference_resources_full",
    "get_immunization_resources_full",
    "get_care_plan_resources_full",
    "get_medication_statement_resources_full",
    "get_service_request_resources_full",
    "get_imaging_study_resources_full",
]
