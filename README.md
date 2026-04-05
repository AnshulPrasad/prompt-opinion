# Prompt Opinion ADK Agents

Example external agents for [Prompt Opinion](https://promptopinion.ai), built with Google ADK and served over A2A JSON-RPC.

This repo currently contains three agents:

| Agent | Purpose | FHIR | Local port |
|---|---|---|---|
| `healthcare_agent` | Reads a patient's FHIR chart and answers clinical questions | Yes | `8001` |
| `general_agent` | Utility agent for timezone-aware date/time and ICD-10 lookup | No | `8002` |
| `orchestrator` | Routes questions to the right specialist agent | Optional | `8003` |

## Architecture

```text
Prompt Opinion
  -> A2A JSON-RPC request
  -> shared/middleware.py
     -> validates X-API-Key for authenticated agents
     -> bridges FHIR metadata into params.metadata
  -> agent app
     -> shared/fhir_hook.py extracts FHIR context into session state
     -> tools run against session state
        -> shared/tools/fhir.py
        -> general_agent/tools/general.py
```

Key rule:
- FHIR credentials stay in A2A metadata and session state. They are not embedded in the prompt text.

## Repo layout

```text
healthcare_agent/
general_agent/
orchestrator/
shared/
  app_factory.py
  fhir_hook.py
  logging_utils.py
  middleware.py
  model_config.py
  rate_limit.py
  tracing.py
  tools/
scripts/
Dockerfile
docker-compose.yml
Procfile
```

## Current agent behavior

### `healthcare_agent`

FHIR-backed clinical assistant with:

Summary tools:
- patient demographics
- active medications
- active conditions
- recent observations

Full-resource tools:
- allergy intolerances
- encounters
- procedures
- diagnostic reports
- document references / clinical notes
- immunizations
- care plans
- medication statements
- service requests
- imaging studies

The agent is tuned for:
- concise answers for focused questions
- structured chart reviews for broad prompts
- partial success when one resource section errors

### `general_agent`

Tools:
- `get_current_datetime(timezone)`
- `look_up_icd10(term)`

No patient context required.

### `orchestrator`

Delegates in-process to:
- `healthcare_fhir_agent`
- `general_agent`

It shares session state with the healthcare sub-agent, so extracted FHIR context is available downstream without extra HTTP calls.

## Requirements

- Python 3.11+
- virtual environment
- Google AI Studio API key for Gemini

Install:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Optional dev helper:

```bash
pip install -r requirements-dev.txt
```

## Environment

This repo expects a local `.env` file at the project root.

Typical values:

```env
GOOGLE_API_KEY=your-google-api-key
GOOGLE_GENAI_USE_VERTEXAI=FALSE

AGENT_API_KEYS=my-secret-key-123,another-valid-key

BASE_URL=https://your-public-base-url
PO_PLATFORM_BASE_URL=https://app.promptopinion.ai

LOG_FULL_PAYLOAD=true
LOG_HOOK_RAW_OBJECTS=false
```

Important variables:
- `GOOGLE_API_KEY`: Gemini API key used by ADK
- `GOOGLE_GENAI_USE_VERTEXAI=FALSE`: current setup uses Gemini API, not Vertex AI
- `AGENT_API_KEYS`: trusted `X-API-Key` values for authenticated agents
- `BASE_URL`: optional shared public URL base for agent cards
- `PO_PLATFORM_BASE_URL`: used to build the FHIR extension URI

Authenticated agents:
- `healthcare_agent`
- `orchestrator`

Public agent:
- `general_agent`

If no API keys are configured, authenticated agents return `503` for `POST /`.

## Running locally

### Separate terminals

```bash
# Terminal 1
uv run python -m uvicorn healthcare_agent.app:a2a_app --host 0.0.0.0 --port 8001

# Terminal 2
uv run python -m uvicorn general_agent.app:a2a_app --host 0.0.0.0 --port 8002

# Terminal 3
uv run python -m uvicorn orchestrator.app:a2a_app --host 0.0.0.0 --port 8003
```

### Honcho / Procfile

```bash
honcho start
```

### Docker Compose

```bash
docker compose up --build
```

## Agent cards

Each agent exposes:

```text
/.well-known/agent-card.json
```

Examples:

```bash
curl http://localhost:8001/.well-known/agent-card.json
curl http://localhost:8002/.well-known/agent-card.json
curl http://localhost:8003/.well-known/agent-card.json
```

## FHIR context

Prompt Opinion sends FHIR credentials in A2A metadata. Expected shape:

```json
{
  "params": {
    "metadata": {
      "https://your-workspace.promptopinion.ai/schemas/a2a/v1/fhir-context": {
        "fhirUrl": "https://your-fhir-server.example.org/r4",
        "fhirToken": "short-lived-bearer-token",
        "patientId": "patient-uuid"
      }
    }
  }
}
```

The hook stores:
- `fhir_url`
- `fhir_token`
- `patient_id`
- `task_id`
- `context_id`
- `message_id`

If FHIR context is missing:
- FHIR tools return a clear error
- the agent should not invent patient data

## API security

Authenticated agents require:

```text
X-API-Key: <one of AGENT_API_KEYS>
```

Middleware behavior:
- `/.well-known/agent-card.json` is always public
- missing key -> `401`
- invalid key -> `403`
- no server-side key config -> `503`

## Debugging

### FHIR hook script

```bash
bash scripts/test_fhir_hook.sh
```

The script sources `.env` automatically and uses the first key from `AGENT_API_KEYS` unless `API_KEY` is set explicitly.

### Useful logs

FHIR hook:
- `hook_called_enter`
- `hook_called_fhir_found`
- `hook_called_fhir_not_found`
- `hook_called_fhir_malformed`

FHIR and utility tools:
- `tool_start ...`
- `tool_finish ...`

Orchestrator sub-agent calls:
- `agent_tool_start ...`
- `agent_tool_finish ...`

Quota handling:
- Gemini `429 RESOURCE_EXHAUSTED` messages are sanitized before they are returned to the caller

## Rate limiting

All three agents use shared Gemini config from `shared/model_config.py`.

Current behavior:
- bounded retry/backoff for transient `429` and `5xx` failures
- short user-facing error text if retries still fail

## Prompt Opinion usage

Typical flow:
1. Run or deploy one of the agents.
2. Expose it publicly if needed.
3. Register the agent URL in Prompt Opinion.
4. Send requests with:
   - the correct `X-API-Key` for authenticated agents
   - FHIR metadata for healthcare/orchestrator flows

Broad chart-review prompts are supported through `healthcare_agent`.

## Cloud deployment

This repo includes:
- `Dockerfile`
- `docker-compose.yml`

You can deploy the same image multiple times with different `AGENT_MODULE` values:

```env
AGENT_MODULE=healthcare_agent.app:a2a_app
GOOGLE_API_KEY=...
GOOGLE_GENAI_USE_VERTEXAI=FALSE
AGENT_API_KEYS=...
PO_PLATFORM_BASE_URL=https://app.promptopinion.ai
```

Repeat with:
- `general_agent.app:a2a_app`
- `orchestrator.app:a2a_app`

## Current known gaps

Not blockers, but worth knowing:
- no committed automated tests are present right now
- local probe/debug artifacts may exist and are not part of runtime
- practitioner/organization/location reference-following is not expanded in runtime logic yet

## Development notes

When changing tools:
1. update `shared/tools/fhir.py` or `general_agent/tools/general.py`
2. re-export through the relevant `__init__.py`
3. register the tool in the target agent
4. keep the agent instruction aligned with the tool surface

When changing auth:
1. update `.env`
2. restart the servers so middleware reloads `AGENT_API_KEYS`

When debugging Prompt Opinion requests:
1. confirm `fhirUrl`, `fhirToken`, and `patientId` are being logged
2. confirm `tool_start` / `tool_finish` lines for the expected resources
3. distinguish FHIR failures from Gemini quota failures
