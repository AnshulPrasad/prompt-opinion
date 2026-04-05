"""
FHIR tools — query a FHIR R4 server on behalf of the patient in context.

These tools are registered with the agent in agent.py.  At call time, each
tool reads the FHIR credentials (fhir_url, fhir_token, patient_id) from
tool_context.state — values that were injected by fhir_hook.extract_fhir_context
before the LLM was called.  The credentials never appear in the prompt.

─────────────────────────────────────────────────────────────────────────────
Adding your own FHIR tools
─────────────────────────────────────────────────────────────────────────────
1. Write a new function in this file (or create a new file in shared/tools/).
2. Add tool_context: ToolContext as the LAST parameter.
3. Start with  ctx = _get_fhir_context(tool_context); if isinstance(ctx, dict): return ctx
4. Export it from shared/tools/__init__.py.
5. Add it to the tools=[...] list in whichever agent(s) need it.

All FHIR REST calls go through _fhir_get(), which attaches the Bearer token
and sets the Accept header.  httpx is used (already a transitive dependency of
google-adk / a2a-sdk — no extra install required).
"""
import logging

import httpx
from google.adk.tools import ToolContext

logger = logging.getLogger(__name__)

_FHIR_TIMEOUT = 15  # seconds


# ── Private helpers ────────────────────────────────────────────────────────────

def _get_fhir_context(tool_context: ToolContext):
    """
    Read FHIR credentials injected by fhir_hook into the session state.

    Returns (fhir_url, fhir_token, patient_id) on success.
    Returns an error dict if any credential is missing so the caller can
    return it directly as the tool result.
    """
    fhir_url   = tool_context.state.get("fhir_url",   "").rstrip("/")
    fhir_token = tool_context.state.get("fhir_token", "")
    patient_id = tool_context.state.get("patient_id", "")

    missing = [
        name for name, val in [
            ("fhir_url",   fhir_url),
            ("fhir_token", fhir_token),
            ("patient_id", patient_id),
        ]
        if not val
    ]
    if missing:
        return {
            "status": "error",
            "error_message": (
                f"FHIR context is not available — missing: {', '.join(missing)}. "
                "Ensure the caller includes 'fhir-context' in the A2A message metadata."
            ),
        }
    return fhir_url, fhir_token, patient_id


def _fhir_get(fhir_url: str, token: str, path: str, params: dict | None = None) -> dict:
    """Perform an authenticated FHIR GET and return the parsed JSON response."""
    response = httpx.get(
        f"{fhir_url}/{path}",
        params=params,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept":        "application/fhir+json",
        },
        timeout=_FHIR_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def _http_error_result(exc: httpx.HTTPStatusError) -> dict:
    return {
        "status":        "error",
        "http_status":   exc.response.status_code,
        "error_message": f"FHIR server returned HTTP {exc.response.status_code}: {exc.response.text[:200]}",
    }


def _connection_error_result(exc: Exception) -> dict:
    return {
        "status":        "error",
        "error_message": f"Could not reach FHIR server: {exc}",
    }


def _coding_display(codings: list) -> str:
    """Return the first human-readable display text from a list of FHIR codings."""
    for c in codings:
        if c.get("display"):
            return c["display"]
    return "Unknown"


# ── Tool: patient demographics ─────────────────────────────────────────────────

def get_patient_demographics(tool_context: ToolContext) -> dict:
    """
    Fetches the demographic information for the current patient from the FHIR server.

    Returns name, date of birth, gender, and primary contact details.
    No arguments required — the patient identity comes from the session context.
    """
    ctx = _get_fhir_context(tool_context)
    if isinstance(ctx, dict):
        return ctx
    fhir_url, fhir_token, patient_id = ctx

    logger.info("tool_get_patient_demographics patient_id=%s", patient_id)
    try:
        patient = _fhir_get(fhir_url, fhir_token, f"Patient/{patient_id}")
    except httpx.HTTPStatusError as e:
        return _http_error_result(e)
    except Exception as e:
        return _connection_error_result(e)

    names    = patient.get("name", [])
    official = next((n for n in names if n.get("use") == "official"), names[0] if names else {})
    given    = " ".join(official.get("given", []))
    family   = official.get("family", "")
    full_name = f"{given} {family}".strip() or "Unknown"

    contacts = [
        {"system": t.get("system"), "value": t.get("value"), "use": t.get("use")}
        for t in patient.get("telecom", [])
    ]

    addrs   = patient.get("address", [])
    address = None
    if addrs:
        a = addrs[0]
        address = ", ".join(filter(None, [
            " ".join(a.get("line", [])),
            a.get("city"), a.get("state"), a.get("postalCode"), a.get("country"),
        ]))

    return {
        "status":         "success",
        "patient_id":     patient_id,
        "name":           full_name,
        "birth_date":     patient.get("birthDate"),
        "gender":         patient.get("gender"),
        "active":         patient.get("active"),
        "contacts":       contacts,
        "address":        address,
        "marital_status": (patient.get("maritalStatus") or {}).get("text"),
    }


# ── Tool: active medications ───────────────────────────────────────────────────

def get_active_medications(tool_context: ToolContext) -> dict:
    """
    Retrieves the patient's current active medication list from the FHIR server.

    Queries MedicationRequest resources with status=active and returns medication
    names, dosage instructions, and prescribing dates.
    No arguments required.
    """
    ctx = _get_fhir_context(tool_context)
    if isinstance(ctx, dict):
        return ctx
    fhir_url, fhir_token, patient_id = ctx

    logger.info("tool_get_active_medications patient_id=%s", patient_id)
    try:
        bundle = _fhir_get(
            fhir_url, fhir_token, "MedicationRequest",
            params={"patient": patient_id, "status": "active", "_count": "50"},
        )
    except httpx.HTTPStatusError as e:
        return _http_error_result(e)
    except Exception as e:
        return _connection_error_result(e)

    medications = []
    for entry in bundle.get("entry", []):
        res         = entry.get("resource", {})
        med_concept = res.get("medicationCodeableConcept", {})
        med_name    = (
            med_concept.get("text")
            or _coding_display(med_concept.get("coding", []))
            or res.get("medicationReference", {}).get("display", "Unknown")
        )
        dosage_list = [d.get("text", "No dosage text") for d in res.get("dosageInstruction", [])]
        medications.append({
            "medication":  med_name,
            "status":      res.get("status"),
            "dosage":      dosage_list[0] if dosage_list else "Not specified",
            "authored_on": res.get("authoredOn"),
            "requester":   (res.get("requester") or {}).get("display"),
        })

    return {
        "status":      "success",
        "patient_id":  patient_id,
        "count":       len(medications),
        "medications": medications,
    }


# ── Tool: active conditions (problem list) ─────────────────────────────────────

def get_active_conditions(tool_context: ToolContext) -> dict:
    """
    Retrieves the patient's active conditions and diagnoses from the FHIR server.

    Queries Condition resources with clinical-status=active and returns the
    problem list with condition names, severity, and onset dates.
    No arguments required.
    """
    ctx = _get_fhir_context(tool_context)
    if isinstance(ctx, dict):
        return ctx
    fhir_url, fhir_token, patient_id = ctx

    logger.info("tool_get_active_conditions patient_id=%s", patient_id)
    try:
        bundle = _fhir_get(
            fhir_url, fhir_token, "Condition",
            params={"patient": patient_id, "clinical-status": "active", "_count": "50"},
        )
    except httpx.HTTPStatusError as e:
        return _http_error_result(e)
    except Exception as e:
        return _connection_error_result(e)

    conditions = []
    for entry in bundle.get("entry", []):
        res   = entry.get("resource", {})
        code  = res.get("code", {})
        onset = res.get("onsetDateTime") or (res.get("onsetPeriod") or {}).get("start")
        conditions.append({
            "condition":       code.get("text") or _coding_display(code.get("coding", [])),
            "clinical_status": (
                (res.get("clinicalStatus") or {}).get("coding", [{}])[0].get("code")
            ),
            "severity":        (res.get("severity") or {}).get("text"),
            "onset":           onset,
            "recorded_date":   res.get("recordedDate"),
        })

    return {
        "status":     "success",
        "patient_id": patient_id,
        "count":      len(conditions),
        "conditions": conditions,
    }


# ── Tool: recent observations (vitals / labs) ──────────────────────────────────

def get_recent_observations(category: str, tool_context: ToolContext) -> dict:
    """
    Retrieves recent clinical observations for the patient from the FHIR server.

    Args:
        category: FHIR observation category. Common values:
                    'vital-signs'    — blood pressure, heart rate, temperature, SpO2
                    'laboratory'     — lab results (CBC, HbA1c, metabolic panel, etc.)
                    'social-history' — smoking status, alcohol use, etc.
                  Defaults to 'vital-signs' if not specified.

    Returns the 20 most recent observations in the category, newest first.
    """
    ctx = _get_fhir_context(tool_context)
    if isinstance(ctx, dict):
        return ctx
    fhir_url, fhir_token, patient_id = ctx

    category = (category or "vital-signs").strip().lower()
    logger.info("tool_get_recent_observations patient_id=%s category=%s", patient_id, category)
    try:
        bundle = _fhir_get(
            fhir_url, fhir_token, "Observation",
            params={"patient": patient_id, "category": category, "_sort": "-date", "_count": "20"},
        )
    except httpx.HTTPStatusError as e:
        return _http_error_result(e)
    except Exception as e:
        return _connection_error_result(e)

    observations = []
    for entry in bundle.get("entry", []):
        res  = entry.get("resource", {})
        code = res.get("code", {})
        obs_name = code.get("text") or _coding_display(code.get("coding", []))

        value, unit = None, None
        if "valueQuantity" in res:
            vq    = res["valueQuantity"]
            value = vq.get("value")
            unit  = vq.get("unit") or vq.get("code")
        elif "valueCodeableConcept" in res:
            value = (res["valueCodeableConcept"].get("text")
                     or _coding_display(res["valueCodeableConcept"].get("coding", [])))
        elif "valueString" in res:
            value = res["valueString"]

        components = []
        for comp in res.get("component", []):
            comp_code = (comp.get("code") or {})
            comp_name = comp_code.get("text") or _coding_display(comp_code.get("coding", []))
            comp_vq   = comp.get("valueQuantity", {})
            components.append({
                "name":  comp_name,
                "value": comp_vq.get("value"),
                "unit":  comp_vq.get("unit") or comp_vq.get("code"),
            })

        observations.append({
            "observation":    obs_name,
            "value":          value,
            "unit":           unit,
            "components":     components or None,
            "effective_date": res.get("effectiveDateTime") or (res.get("effectivePeriod") or {}).get("start"),
            "status":         res.get("status"),
            "interpretation": (
                (res.get("interpretation") or [{}])[0].get("text")
                or _coding_display((res.get("interpretation") or [{}])[0].get("coding", []))
            ),
        })

    return {
        "status":       "success",
        "patient_id":   patient_id,
        "category":     category,
        "count":        len(observations),
        "observations": observations,
    }


# ── Full-resource tools: balanced clinical expansion ──────────────────────────
# These tools return raw resource JSON for clinically meaningful resources that
# were confirmed against the Prompt Opinion FHIR server.  Keeping them separate
# from the summary tools above gives the agent access to richer chart data
# without replacing the existing clinician-friendly summaries.


def _extract_bundle_resources(bundle: dict) -> list[dict]:
    """Extract full resource objects from a FHIR searchset bundle."""
    resources: list[dict] = []
    for entry in bundle.get("entry", []):
        if isinstance(entry, dict):
            resource = entry.get("resource")
            if isinstance(resource, dict):
                resources.append(resource)
    return resources


def _fetch_full_resource_bundle(
    resource_type: str,
    tool_context: ToolContext,
    *,
    search_params: dict | None = None,
    patient_param: str = "patient",
    count: int = 50,
) -> dict:
    """
    Fetch a patient-scoped FHIR searchset and return full resource payloads.

    The `resources` list preserves all fields returned by the upstream FHIR
    server so downstream logic can inspect the full chart data when needed.
    """
    ctx = _get_fhir_context(tool_context)
    if isinstance(ctx, dict):
        return ctx
    fhir_url, fhir_token, patient_id = ctx

    params = {patient_param: patient_id, "_count": str(count)}
    if search_params:
        params.update({k: v for k, v in search_params.items() if v not in (None, "")})

    logger.info(
        "tool_fetch_full_resource_bundle resource_type=%s patient_id=%s patient_param=%s",
        resource_type, patient_id, patient_param,
    )
    try:
        bundle = _fhir_get(fhir_url, fhir_token, resource_type, params=params)
    except httpx.HTTPStatusError as e:
        return _http_error_result(e)
    except Exception as e:
        return _connection_error_result(e)

    resources = _extract_bundle_resources(bundle)
    return {
        "status":        "success",
        "patient_id":    patient_id,
        "resource_type": resource_type,
        "count":         len(resources),
        "bundle":        bundle,
        "resources":     resources,
    }


def get_allergy_intolerance_resources_full(tool_context: ToolContext) -> dict:
    """
    Returns full AllergyIntolerance resources for the patient.

    Typical fields include clinicalStatus, verificationStatus, category,
    criticality, code, onset[x], reaction, recorder, and note.
    """
    return _fetch_full_resource_bundle(
        "AllergyIntolerance",
        tool_context,
        search_params={"_sort": "-date"},
    )


def get_encounter_resources_full(tool_context: ToolContext) -> dict:
    """
    Returns full Encounter resources for the patient.

    Typical fields include status, class, type, period, reasonCode,
    hospitalization, serviceProvider, participant, and location.
    """
    return _fetch_full_resource_bundle(
        "Encounter",
        tool_context,
        search_params={"_sort": "-date"},
    )


def get_procedure_resources_full(tool_context: ToolContext) -> dict:
    """
    Returns full Procedure resources for the patient.

    Typical fields include status, category, code, performed[x], performer,
    reasonCode, bodySite, outcome, complication, and note.
    """
    return _fetch_full_resource_bundle(
        "Procedure",
        tool_context,
        search_params={"_sort": "-date"},
    )


def get_diagnostic_report_resources_full(tool_context: ToolContext) -> dict:
    """
    Returns full DiagnosticReport resources for the patient.

    Typical fields include status, category, code, effective[x], issued,
    performer, result, conclusion, media, and presentedForm.
    """
    return _fetch_full_resource_bundle(
        "DiagnosticReport",
        tool_context,
        search_params={"_sort": "-date"},
    )


def get_document_reference_resources_full(tool_context: ToolContext) -> dict:
    """
    Returns full DocumentReference resources for the patient.

    Typical fields include status, type, category, date, author, custodian,
    context, description, securityLabel, and content attachments.
    """
    return _fetch_full_resource_bundle(
        "DocumentReference",
        tool_context,
        search_params={"_sort": "-date"},
    )


def get_immunization_resources_full(tool_context: ToolContext) -> dict:
    """
    Returns full Immunization resources for the patient.

    Typical fields include status, vaccineCode, occurrence[x], primarySource,
    manufacturer, lotNumber, site, route, doseQuantity, performer, and note.
    """
    return _fetch_full_resource_bundle(
        "Immunization",
        tool_context,
        search_params={"_sort": "-date"},
    )


def get_care_plan_resources_full(tool_context: ToolContext) -> dict:
    """
    Returns full CarePlan resources for the patient.

    Typical fields include status, intent, category, title, description, period,
    careTeam, addresses, goal, activity, and note.
    """
    return _fetch_full_resource_bundle(
        "CarePlan",
        tool_context,
        search_params={"_sort": "-date"},
    )


def get_medication_statement_resources_full(tool_context: ToolContext) -> dict:
    """
    Returns full MedicationStatement resources for the patient.

    Typical fields include status, medication[x], effective[x], dateAsserted,
    informationSource, reasonCode, dosage, and note.
    """
    return _fetch_full_resource_bundle(
        "MedicationStatement",
        tool_context,
        search_params={"_sort": "-date"},
    )


def get_service_request_resources_full(tool_context: ToolContext) -> dict:
    """
    Returns full ServiceRequest resources for the patient.

    Typical fields include status, intent, category, code, orderDetail,
    occurrence[x], requester, performer, reasonCode, and supportingInfo.
    """
    return _fetch_full_resource_bundle(
        "ServiceRequest",
        tool_context,
        search_params={"_sort": "-date"},
    )


def get_imaging_study_resources_full(tool_context: ToolContext) -> dict:
    """
    Returns full ImagingStudy resources for the patient.

    Typical fields include status, started, procedureCode, numberOfSeries,
    numberOfInstances, series, encounter, and location.
    """
    return _fetch_full_resource_bundle(
        "ImagingStudy",
        tool_context,
        search_params={"_sort": "-date"},
    )
