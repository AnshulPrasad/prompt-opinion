import json
from collections import defaultdict
import os
import requests

FHIR_URL = "https://app.promptopinion.ai/api/workspaces/019d53be-4431-707b-a430-c4255d94b500/fhir"
PATIENT_ID = os.getenv("PATIENT_ID")
FHIR_TOKEN = os.getenv("FHIR_TOKEN")

RESOURCE_TYPES = [
    "Account", "ActivityDefinition", "AdverseEvent", "AllergyIntolerance", "Appointment",
    "AppointmentResponse", "AuditEvent", "Basic", "Binary", "BiologicallyDerivedProduct",
    "BodyStructure", "Bundle", "CapabilityStatement", "CarePlan", "CareTeam",
    "CatalogEntry", "ChargeItem", "ChargeItemDefinition", "Claim", "ClaimResponse",
    "ClinicalImpression", "CodeSystem", "Communication", "CommunicationRequest",
    "CompartmentDefinition", "Composition", "ConceptMap", "Condition", "Consent",
    "Contract", "Coverage", "CoverageEligibilityRequest", "CoverageEligibilityResponse",
    "DetectedIssue", "Device", "DeviceDefinition", "DeviceMetric", "DeviceRequest",
    "DeviceUseStatement", "DiagnosticReport", "DocumentManifest", "DocumentReference",
    "Encounter", "Endpoint", "EnrollmentRequest", "EnrollmentResponse", "EpisodeOfCare",
    "EventDefinition", "Evidence", "EvidenceVariable", "ExampleScenario", "ExplanationOfBenefit",
    "FamilyMemberHistory", "Flag", "Goal", "GraphDefinition", "Group", "GuidanceResponse",
    "HealthcareService", "ImagingStudy", "Immunization", "ImmunizationEvaluation",
    "ImmunizationRecommendation", "ImplementationGuide", "InsurancePlan", "Invoice",
    "Library", "Linkage", "List", "Location", "Measure", "MeasureReport", "Media",
    "Medication", "MedicationAdministration", "MedicationDispense", "MedicationKnowledge",
    "MedicationRequest", "MedicationStatement", "MedicinalProduct", "MedicinalProductAuthorization",
    "MedicinalProductContraindication", "MedicinalProductIndication", "MedicinalProductIngredient",
    "MedicinalProductInteraction", "MedicinalProductManufactured", "MedicinalProductPackaged",
    "MedicinalProductPharmaceutical", "MedicinalProductUndesirableEffect", "MessageDefinition",
    "MessageHeader", "MolecularSequence", "NamingSystem", "NutritionOrder", "Observation",
    "ObservationDefinition", "OperationDefinition", "OperationOutcome", "Organization",
    "OrganizationAffiliation", "Parameters", "Patient", "PaymentNotice", "PaymentReconciliation",
    "Person", "PlanDefinition", "Practitioner", "PractitionerRole", "Procedure", "Provenance",
    "Questionnaire", "QuestionnaireResponse", "RelatedPerson", "RequestGroup", "ResearchDefinition",
    "ResearchElementDefinition", "ResearchStudy", "ResearchSubject", "RiskAssessment",
    "RiskEvidenceSynthesis", "Schedule", "SearchParameter", "ServiceRequest", "Slot",
    "Specimen", "SpecimenDefinition", "StructureDefinition", "StructureMap",
    "Subscription", "Substance", "SubstanceNucleicAcid", "SubstancePolymer",
    "SubstanceProtein", "SubstanceReferenceInformation", "SubstanceSourceMaterial",
    "SubstanceSpecification", "SupplyDelivery", "SupplyRequest", "Task", "TerminologyCapabilities",
    "TestReport", "TestScript", "ValueSet", "VerificationResult", "VisionPrescription",
]

HEADERS = {
    "Authorization": f"Bearer {FHIR_TOKEN}",
    "Accept": "application/fhir+json",
}

PATIENT_PARAM_CANDIDATES = ["patient", "subject", "individual", "beneficiary"]


def get_json(response):
    try:
        return response.json()
    except Exception:
        return None


def extract_reference_strings(obj):
    refs = set()

    def walk(value):
        if isinstance(value, dict):
            ref = value.get("reference")
            if isinstance(ref, str) and "/" in ref:
                refs.add(ref)
            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(obj)
    return refs


def try_patient_search(resource_type):
    for patient_param in PATIENT_PARAM_CANDIDATES:
        url = f"{FHIR_URL}/{resource_type}"
        params = {patient_param: PATIENT_ID, "_count": 1}

        try:
            response = requests.get(url, headers=HEADERS, params=params, timeout=20)
        except requests.RequestException as exc:
            return {
                "resource": resource_type,
                "category": "not_confirmed",
                "status_code": None,
                "patient_param": patient_param,
                "error": str(exc),
            }

        payload = get_json(response)
        content_type = response.headers.get("Content-Type", "")

        if response.status_code == 200 and isinstance(payload, dict):
            if payload.get("resourceType") == "Bundle":
                entries = payload.get("entry") or []
                first = entries[0].get("resource", {}) if entries else {}
                return {
                    "resource": resource_type,
                    "category": "patient_search_supported",
                    "status_code": 200,
                    "patient_param": patient_param,
                    "bundle_total": payload.get("total"),
                    "has_data": bool(entries),
                    "returned_type": first.get("resourceType") if first else None,
                    "sample_fields": sorted(first.keys()) if first else [],
                    "references": sorted(extract_reference_strings(first)) if first else [],
                    "content_type": content_type,
                }

        if response.status_code in (400, 404, 422):
            continue

        return {
            "resource": resource_type,
            "category": "not_confirmed",
            "status_code": response.status_code,
            "patient_param": patient_param,
            "content_type": content_type,
            "error": payload if isinstance(payload, dict) else response.text[:500],
        }

    return {
        "resource": resource_type,
        "category": "not_confirmed",
        "status_code": None,
        "patient_param": None,
        "error": "No tested patient-scoped search parameter worked",
    }


def try_direct_patient_read():
    url = f"{FHIR_URL}/Patient/{PATIENT_ID}"
    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
    except requests.RequestException as exc:
        return {
            "resource": "Patient",
            "category": "not_confirmed",
            "status_code": None,
            "error": str(exc),
        }

    payload = get_json(response)
    if response.status_code == 200 and isinstance(payload, dict) and payload.get("resourceType") == "Patient":
        return {
            "resource": "Patient",
            "category": "direct_read_supported",
            "status_code": 200,
            "sample_fields": sorted(payload.keys()),
            "references": sorted(extract_reference_strings(payload)),
        }

    return {
        "resource": "Patient",
        "category": "not_confirmed",
        "status_code": response.status_code,
        "error": payload if isinstance(payload, dict) else response.text[:500],
    }


def try_reference_read(reference):
    resource_type, resource_id = reference.split("/", 1)
    url = f"{FHIR_URL}/{resource_type}/{resource_id}"

    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
    except requests.RequestException as exc:
        return {
            "resource": resource_type,
            "reference": reference,
            "category": "not_confirmed",
            "status_code": None,
            "error": str(exc),
        }

    payload = get_json(response)
    if response.status_code == 200 and isinstance(payload, dict) and payload.get("resourceType") == resource_type:
        return {
            "resource": resource_type,
            "reference": reference,
            "category": "referenced_resource_supported",
            "status_code": 200,
            "sample_fields": sorted(payload.keys()),
            "references": sorted(extract_reference_strings(payload)),
        }

    return {
        "resource": resource_type,
        "reference": reference,
        "category": "not_confirmed",
        "status_code": response.status_code,
        "error": payload if isinstance(payload, dict) else response.text[:500],
    }


def main():
    results = []
    summary = defaultdict(list)
    collected_references = set()

    patient_result = try_direct_patient_read()
    results.append(patient_result)
    summary[patient_result["category"]].append("Patient")
    for ref in patient_result.get("references", []):
        collected_references.add(ref)

    for resource_type in RESOURCE_TYPES:
        if resource_type == "Patient":
            continue

        result = try_patient_search(resource_type)
        results.append(result)
        summary[result["category"]].append(resource_type)

        for ref in result.get("references", []):
            collected_references.add(ref)

        print(f"{resource_type}: {json.dumps(result, ensure_ascii=False)}")

    reference_results = []
    seen_reference_types = set()

    for reference in sorted(collected_references):
        resource_type = reference.split("/", 1)[0]
        if resource_type in seen_reference_types:
            continue
        seen_reference_types.add(resource_type)

        result = try_reference_read(reference)
        reference_results.append(result)
        summary[result["category"]].append(f"{resource_type} (via reference)")
        print(f"REFERENCE {resource_type}: {json.dumps(result, ensure_ascii=False)}")

    output = {
        "summary": summary,
        "results": results,
        "reference_results": reference_results,
    }

    print("\n=== SUMMARY ===")
    print(json.dumps(output["summary"], indent=2, ensure_ascii=False))

    with open("fhir_resource_probe_results_v2.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=list)


if __name__ == "__main__":
    main()