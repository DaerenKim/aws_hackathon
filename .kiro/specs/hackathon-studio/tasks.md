# Implementation Plan: Hackathon Studio

## Overview

This implementation plan breaks down the Hackathon Studio multi-agent AI system into incremental coding tasks. The system uses FastAPI + LangGraph (Python) for the backend orchestration, Next.js + TypeScript for the frontend dashboard, and Ollama for local LLM inference. Tasks are ordered by dependency: shared infrastructure → base agent → specialized agents → orchestrator → API layer → frontend → validators → tests.

## Tasks

- [x] 1. Project scaffolding and shared infrastructure
  - [x] 1.1 Create backend project structure and dependencies
    - Create `backend/` directory with `app/`, `app/api/routes/`, `app/orchestrator/`, `app/agents/`, `app/services/`, `app/models/`, and `tests/` subdirectories
    - Create `backend/requirements.txt` with: fastapi, uvicorn, langgraph, langchain-ollama, pydantic, python-pptx, playwright, pygithub, httpx, pytest, hypothesis, python-multipart, aiofiles
    - Create `backend/app/__init__.py` and all subpackage `__init__.py` files
    - _Requirements: 14.1_

  - [x] 1.2 Create Pydantic data models for project state, inputs, and artifacts
    - Implement `backend/app/models/project_state.py` with `AgentStatus` enum (pending, in_progress, completed, failed), `PhaseStatus` enum, `AgentPhase` model, `ApprovalGateState` model, and `ProjectState` model
    - Implement `backend/app/models/inputs.py` with `UploadedFile`, `InputPackage`, `ValidationResult`, and `ValidationError` models
    - Implement `backend/app/models/artifacts.py` with `AgentResult`, `OrchestratorEvent`, and `OllamaConfig` models
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 14.1_

  - [x] 1.3 Implement Ollama client service
    - Create `backend/app/services/ollama_client.py` with `OllamaClient` class
    - Implement `generate()` with exponential backoff retry (3 retries, 2s/4s/8s delays)
    - Implement `chat()` with retry logic
    - Implement `health_check()` endpoint verification
    - Configure 120s per-call timeout
    - _Requirements: 6.3, 6.6_

  - [x] 1.4 Implement State Manager service
    - Create `backend/app/services/state_manager.py` with `StateManager` class
    - Implement atomic `read_state()` and `update_agent_status()` with file locking
    - Implement `set_phase()`, `get_agent_status()`, `is_artifact_ready()` methods
    - Ensure atomic file writes to prevent partial state corruption
    - _Requirements: 14.1, 14.4, 14.5_

  - [x] 1.5 Implement Workspace service
    - Create `backend/app/services/workspace.py` with `WorkspaceService` class
    - Implement `write_file()`, `read_file()`, `file_exists()`, `list_files()` async methods
    - Implement path validation to enforce agent write boundaries
    - Implement `validate_artifact()` method that accepts an `ArtifactValidator`
    - _Requirements: 14.4, 14.6, 16.1_

- [x] 2. Base agent class
  - [x] 2.1 Implement BaseAgent abstract class
    - Create `backend/app/agents/base.py` with `BaseAgent` ABC
    - Constructor accepts `agent_name`, `ollama_client`, `workspace`, `state_manager`
    - Implement abstract `execute(context: dict) -> AgentResult` method
    - Implement `read_artifact()` with state validation (checks producing agent is "completed")
    - Implement `write_artifact()` with path boundary enforcement
    - Implement `llm_generate()` wrapper with agent-specific system prompt
    - Implement `update_status()` to update project_state.json
    - Add 600s execution timeout wrapper
    - _Requirements: 14.1, 14.4, 14.5, 14.6, 14.7_

- [x] 3. Implement Planning phase agents
  - [x] 3.1 Implement Project Planner Agent
    - Create `backend/app/agents/project_planner.py`
    - Read input package from workspace, generate project_spec.md with required sections: refined idea, elevator pitch (≤3 sentences), target users, MVP scope, stretch goals, timeline
    - Constrain MVP scope to hackathon time/team/theme constraints from brief
    - Save to `project_spec.md` in workspace, update state on completion
    - Handle missing inputs by marking state as "failed" with reason
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [x] 3.2 Implement Judge Optimizer Agent
    - Create `backend/app/agents/judge_optimizer.py`
    - Extract scoring criteria from rubric, score plan against each criterion (1-10)
    - Generate improvement suggestions for criteria scoring below 8
    - Produce `judge_analysis.md` with: criteria list, scores, suggestions, predicted total, tradeoffs
    - Update state on completion; mark failed if rubric is unparseable
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

- [x] 4. Implement Development phase agents
  - [x] 4.1 Implement Backend Engineer Agent
    - Create `backend/app/agents/backend_engineer.py`
    - Read architecture.md, implement FastAPI endpoints, data models, migrations
    - Integrate AI service calls with 30s timeout and 3 retries with fallback
    - Write unit tests (one per endpoint, success + error case)
    - Save to `backend/` directory, update state on completion
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

  - [x] 4.2 Implement Frontend Engineer Agent
    - Create `backend/app/agents/frontend_engineer.py`
    - Read architecture.md, build Next.js + TypeScript + TailwindCSS + shadcn/ui pages
    - Implement responsive layouts (360px, 768px, 1280px)
    - Implement client-side state management and API integration with loading/error states
    - Save to `frontend/` directory, update state on completion
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 4.3 Implement Integration Agent
    - Create `backend/app/agents/integration.py`
    - Configure frontend API base URL, verify each endpoint is callable
    - Resolve dependency conflicts between frontend/backend packages
    - Execute end-to-end verification per API endpoint
    - Document resolutions in logs/, update state on completion
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 4.4 Implement QA Agent
    - Create `backend/app/agents/qa.py`
    - Run pytest (backend), vitest (frontend), playwright UI tests
    - Produce `testing_report.md` with pass/fail counts, bug descriptions, severity ratings
    - Route critical/major bugs to responsible agents for fixing
    - Halt after 3 fix cycles if unresolved; trigger approval gate 2 on success
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7_

- [x] 5. Implement Delivery phase agents
  - [x] 5.1 Implement Documentation Agent
    - Create `backend/app/agents/documentation.py`
    - Generate README.md (overview, setup, usage, tech stack), developer_guide.md, api_docs.md
    - Source content from project_spec.md, architecture.md, and generated code
    - Handle missing source artifacts gracefully with notes about incomplete sections
    - Save to workspace root, update state (require ≥200 chars per file)
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_

  - [x] 5.2 Implement PowerPoint Agent
    - Create `backend/app/agents/powerpoint.py`
    - Generate 6-15 slides using python-pptx: problem, solution, architecture, demo screenshots, team/tooling, roadmap
    - Add speaker notes (≥50 chars per slide)
    - Use placeholder slides if screenshots unavailable
    - Save to `ppt/` directory, update state on completion
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7_

  - [x] 5.3 Implement Demo Video Agent
    - Create `backend/app/agents/demo_video.py`
    - Record automated demo with Playwright (60-300s duration)
    - Generate voiceover narration synchronized with screen recording
    - Burn captions into video, encode with FFmpeg (MP4, ≥1280x720)
    - Save to `video/` directory, handle app start failures gracefully
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_

  - [x] 5.4 Implement GitHub Agent
    - Create `backend/app/agents/github.py`
    - Create public repo via PyGithub, structured commits (setup, backend, frontend, integration, docs, presentation)
    - Configure .gitignore, MIT LICENSE, branch protection
    - Push workspace contents, trigger approval gate 3
    - Retry up to 3 times with 5s delay on API errors
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6_

- [x] 6. Checkpoint - Planning and agent implementations
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. LangGraph orchestrator
  - [x] 7.1 Define orchestrator state schema
    - Create `backend/app/orchestrator/state.py`
    - Define `OrchestratorState` TypedDict with: phase, agents_status, approval_pending, approval_gate, error, revision_count
    - _Requirements: 14.1_

  - [x] 7.2 Implement graph node functions
    - Create `backend/app/orchestrator/nodes.py`
    - Implement node functions: `run_project_planner`, `run_judge_optimizer`, `run_architecture_design`, `handle_approval_gate`, `run_parallel_development`, `run_integration`, `run_qa`, `run_parallel_delivery`
    - Each node instantiates its agent(s), executes, and returns updated state
    - Parallel nodes use asyncio.gather for Backend+Frontend and Delivery agents
    - _Requirements: 14.1, 14.2, 14.3_

  - [x] 7.3 Implement conditional edge functions
    - Create `backend/app/orchestrator/edges.py`
    - Implement `route_after_approval` (approve → next phase, reject → revision loop)
    - Implement `route_after_qa` (all pass → gate 2, failures → bug fix loop)
    - Enforce max 5 revision cycles per gate with escalation
    - _Requirements: 5.1, 5.3, 5.4, 9.5, 9.6, 9.7_

  - [x] 7.4 Build and compile the LangGraph state graph
    - Create `backend/app/orchestrator/graph.py`
    - Wire all nodes and conditional edges as defined in design
    - Set entry point to `project_planning`
    - Compile graph and export for use by API layer
    - _Requirements: 5.5, 14.1, 14.2, 14.3_

- [x] 8. FastAPI API layer
  - [x] 8.1 Implement input collection endpoints
    - Create `backend/app/api/routes/inputs.py`
    - `POST /api/inputs/upload` — accept multipart file uploads (PDF, DOCX, TXT, ≤10MB)
    - `POST /api/inputs/submit` — accept project idea + tech stack text
    - `GET /api/inputs/status` — return validation status
    - Implement input validation with specific error reporting (field + reason)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8_

  - [x] 8.2 Implement workflow control endpoints
    - Create `backend/app/api/routes/workflow.py`
    - `POST /api/workflow/start` — start orchestration pipeline
    - `GET /api/workflow/state` — return current project state
    - _Requirements: 5.1, 14.1_

  - [x] 8.3 Implement approval gate endpoints
    - Create `backend/app/api/routes/approval.py`
    - `POST /api/workflow/approve` — approve at gate, resume within 5s
    - `POST /api/workflow/request-change` — route feedback, track revision count
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 8.4 Implement SSE streaming endpoints
    - Create `backend/app/api/routes/stream.py`
    - `GET /api/stream/status` — SSE for real-time state changes (poll ≤3s)
    - `GET /api/stream/logs/{agent}` — SSE for agent log entries
    - Emit events within 10s of state changes
    - _Requirements: 15.2, 15.3, 15.4_

  - [x] 8.5 Implement deliverables endpoints and FastAPI main entry point
    - Add `GET /api/deliverables` and `GET /api/deliverables/{path}` to serve artifacts
    - Create `backend/app/main.py` with FastAPI app, CORS config, router includes
    - Create `backend/app/api/deps.py` with shared dependency injection
    - _Requirements: 15.5_

- [x] 9. Checkpoint - Backend complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Next.js frontend
  - [x] 10.1 Create frontend project structure and dependencies
    - Initialize Next.js project in `frontend/` with TypeScript, TailwindCSS, shadcn/ui
    - Create `frontend/src/lib/types.ts` with TypeScript types matching backend models
    - Create `frontend/src/lib/api.ts` with API client (fetch wrapper for all endpoints)
    - _Requirements: 15.1_

  - [x] 10.2 Implement SSE hook and project state hook
    - Create `frontend/src/hooks/use-sse.ts` — connect to SSE endpoints, parse events, reconnect on failure
    - Create `frontend/src/hooks/use-project-state.ts` — manage project state from SSE stream
    - _Requirements: 15.2, 15.3, 15.4_

  - [x] 10.3 Implement shared UI components
    - Create `frontend/src/components/agent-status-card.tsx` — display agent name, status badge, failure reason
    - Create `frontend/src/components/phase-indicator.tsx` — current phase header/progress
    - Create `frontend/src/components/log-viewer.tsx` — real-time log display
    - Create `frontend/src/components/file-upload.tsx` — drag-and-drop file upload with validation
    - Create `frontend/src/components/approval-dialog.tsx` — approve/request-change dialog
    - _Requirements: 15.1, 15.2, 15.6_

  - [x] 10.4 Implement input collection page
    - Create `frontend/src/app/input/page.tsx`
    - File upload for hackathon brief and judging rubric (PDF/DOCX/TXT, ≤10MB)
    - Text inputs for project idea (1-5000 chars) and tech stack (optional, ≤2000 chars)
    - Client-side validation with error display, submit to backend
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [x] 10.5 Implement monitoring dashboard page
    - Create `frontend/src/app/monitor/page.tsx`
    - Display current phase, all 10 agent status cards updated via SSE
    - Show agent logs in real-time log viewer
    - Display failure reasons for failed agents
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.6_

  - [x] 10.6 Implement approval gate page
    - Create `frontend/src/app/approval/page.tsx`
    - Display relevant artifacts for review (architecture, testing report, or deliverables)
    - Summary with completed phases, artifact descriptions, next actions
    - Approve and request-change buttons with feedback text area
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 10.7 Implement deliverables page and main dashboard
    - Create `frontend/src/app/deliverables/page.tsx` — list artifacts with download links
    - Create `frontend/src/app/page.tsx` — main landing/navigation page
    - _Requirements: 15.5_

- [x] 11. Checkpoint - Frontend complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Artifact validators
  - [x] 12.1 Implement artifact validator base and format-specific validators
    - Create `backend/app/services/validators.py`
    - Implement `ArtifactValidator` ABC with `validate(file_path) -> ValidationResult`
    - Implement `PythonSyntaxValidator` — checks .py files for valid syntax, verifies requirements.txt has fastapi
    - Implement `PackageJsonValidator` — checks valid JSON, has "build" script, "next" dependency, name and dependencies fields
    - Implement `PptxValidator` — checks ZIP/OOXML structure, ≥6 slides
    - Implement `Mp4Validator` — checks decodable, has video stream, ≥5s duration
    - Implement `MarkdownNonEmptyValidator` — checks non-empty, ≥200 chars
    - Wire validators into orchestrator node completion checks
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6_

- [x] 13. Checkpoint - All implementation complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 14. Property-based tests
  - [ ]* 14.1 Write property test for input validation correctness
    - **Property 1: Input Validation Correctness**
    - Test with Hypothesis strategies for file formats (PDF/DOCX/TXT + invalid), sizes (0 to >10MB), text lengths (0-5001 for idea, 0-2001 for tech stack)
    - Verify accept iff format valid AND 0 < size ≤ 10MB AND text extractable AND length constraints met
    - **Validates: Requirements 1.1, 1.2, 1.3, 1.4, 1.5**

  - [ ]* 14.2 Write property test for validation error reporting completeness
    - **Property 2: Validation Error Reporting Completeness**
    - For any failing input, verify error contains field name AND reason (unsupported_format | empty_content | unextractable_text | size_exceeded | length_constraint)
    - **Validates: Requirements 1.6**

  - [ ]* 14.3 Write property test for agent state transition on success
    - **Property 3: Agent State Transition on Success**
    - For any agent completing with valid artifacts, verify status transitions from "in_progress" → "completed" with completion timestamp recorded
    - **Validates: Requirements 2.4, 3.5, 14.1**

  - [ ]* 14.4 Write property test for agent state transition on failure
    - **Property 4: Agent State Transition on Failure**
    - For any agent that fails, verify status → "failed", error message non-empty, failure logged to logs/failures.log with timestamp
    - **Validates: Requirements 2.5, 3.6, 4.6, 14.5, 16.6**

  - [ ]* 14.5 Write property test for score threshold improvement suggestions
    - **Property 5: Score Threshold Improvement Suggestions**
    - For any set of criterion scores, verify suggestions generated for exactly those with score < 8, zero suggestions for score ≥ 8
    - **Validates: Requirements 3.3**

  - [ ]* 14.6 Write property test for document structure validation
    - **Property 6: Document Structure Validation**
    - For any markdown document, verify validator passes iff all required sections present and each contains ≥1 non-whitespace char
    - **Validates: Requirements 2.1, 3.4, 4.2, 4.3, 10.1, 10.2, 10.3**

  - [ ]* 14.7 Write property test for technology reference containment
    - **Property 7: Technology Reference Containment**
    - For any architecture doc and allowed tech set, verify rejection if any tech not in allowed set, acceptance if all within set
    - **Validates: Requirements 4.4**

  - [ ]* 14.8 Write property test for approval gate execution blocking
    - **Property 8: Approval Gate Execution Blocking**
    - For any state with approval_pending=true, verify no agent transitions from "pending" → "in_progress"
    - **Validates: Requirements 5.1**

  - [ ]* 14.9 Write property test for revision counter bounds
    - **Property 9: Revision Counter Bounds**
    - For any revision request sequence, verify counter increments by exactly 1, never exceeds 5, escalates at 5
    - **Validates: Requirements 5.4**

  - [ ]* 14.10 Write property test for parallel execution fault isolation
    - **Property 10: Parallel Execution Fault Isolation**
    - For any parallel agent set where one fails, verify all others remain unaffected (status unchanged)
    - **Validates: Requirements 14.2, 14.3**

  - [ ]* 14.11 Write property test for artifact access control
    - **Property 11: Artifact Access Control**
    - For any read attempt, verify success iff producing agent status is "completed"; denied otherwise
    - **Validates: Requirements 14.4**

  - [ ]* 14.12 Write property test for agent write protection
    - **Property 12: Agent Write Protection**
    - For any write operation, verify permitted only if target path within agent's designated directory; rejected otherwise
    - **Validates: Requirements 14.6**

  - [ ]* 14.13 Write property test for artifact format validation dispatch
    - **Property 13: Artifact Format Validation Dispatch**
    - For any completed agent, verify correct validator applied: Python syntax for backend, package.json for frontend, OOXML+≥6 slides for PPTX, video stream+≥5s for MP4, size > 0 for all
    - **Validates: Requirements 16.1, 16.2, 16.3, 16.4, 16.5**

- [ ] 15. Integration tests
  - [ ]* 15.1 Write integration tests for API endpoints
    - Create `backend/tests/integration/test_api_endpoints.py`
    - Test input upload/submit/validation flow with httpx async client
    - Test workflow start, state retrieval, approval, and request-change endpoints
    - Test deliverables listing and download
    - _Requirements: 1.1-1.8, 5.1-5.4, 15.5_

  - [ ]* 15.2 Write integration tests for workflow sequence
    - Create `backend/tests/integration/test_workflow_sequence.py`
    - Test full pipeline with mocked Ollama responses
    - Verify phase transitions: planning → approval → development → approval → delivery → approval
    - Verify parallel agent execution and fault isolation
    - _Requirements: 14.1, 14.2, 14.3, 5.5_

  - [ ]* 15.3 Write integration tests for SSE streaming
    - Create `backend/tests/integration/test_sse_streaming.py`
    - Test SSE connection, event format, reconnection
    - Verify status change events emitted within expected timeframe
    - _Requirements: 15.2, 15.3, 15.4_

- [ ] 16. End-to-end tests with Playwright
  - [ ]* 16.1 Write Playwright tests for input collection flow
    - Create `frontend/e2e/input-collection.spec.ts`
    - Test file upload (valid and invalid formats/sizes), text input validation, form submission
    - _Requirements: 1.1-1.6_

  - [ ]* 16.2 Write Playwright tests for monitoring dashboard
    - Create `frontend/e2e/monitoring.spec.ts`
    - Test phase display, agent status card updates, log viewer, failure display
    - _Requirements: 15.1-15.4, 15.6_

  - [ ]* 16.3 Write Playwright tests for approval gates
    - Create `frontend/e2e/approval-gates.spec.ts`
    - Test artifact review display, approve action, request-change with feedback
    - _Requirements: 5.1-5.4_

- [x] 17. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- Backend agents (tasks 3-5) each produce their own module file and can be developed incrementally
- The LangGraph orchestrator (task 7) wires all agents together - ensure agent interfaces are stable before wiring
- Frontend tasks (task 10) depend on the API layer being complete for integration
- Validators (task 12) must be wired into orchestrator completion checks

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["1.3", "1.4", "1.5"] },
    { "id": 2, "tasks": ["2.1"] },
    { "id": 3, "tasks": ["3.1", "3.2"] },
    { "id": 4, "tasks": ["4.1", "4.2", "4.3", "4.4"] },
    { "id": 5, "tasks": ["5.1", "5.2", "5.3", "5.4"] },
    { "id": 6, "tasks": ["7.1", "12.1"] },
    { "id": 7, "tasks": ["7.2", "7.3"] },
    { "id": 8, "tasks": ["7.4"] },
    { "id": 9, "tasks": ["8.1", "8.2", "8.3", "8.4", "8.5"] },
    { "id": 10, "tasks": ["10.1"] },
    { "id": 11, "tasks": ["10.2", "10.3"] },
    { "id": 12, "tasks": ["10.4", "10.5", "10.6", "10.7"] },
    { "id": 13, "tasks": ["14.1", "14.2", "14.3", "14.4", "14.5", "14.6", "14.7", "14.8", "14.9", "14.10", "14.11", "14.12", "14.13"] },
    { "id": 14, "tasks": ["15.1", "15.2", "15.3"] },
    { "id": 15, "tasks": ["16.1", "16.2", "16.3"] }
  ]
}
```
