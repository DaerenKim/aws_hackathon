# Requirements Document

## Introduction

Hackathon Studio is an autonomous multi-agent AI software studio that transforms a hackathon brief, judging rubric, and project idea into a complete hackathon-ready MVP. The system behaves like an AI software company where 10 specialized agents collaborate through three phases (Planning, Development, Delivery) with human approval gates at critical milestones. The frontend provides an interactive dashboard for uploading inputs, reviewing blueprints, monitoring agent progress, and downloading final deliverables.

## Glossary

- **Orchestrator**: The central coordination engine that manages agent sequencing, parallel execution, shared state, and human approval gates across all workflow phases
- **Agent**: A specialized autonomous AI worker that performs a distinct role (e.g., planning, coding, testing) within the multi-agent system
- **Project_Planner_Agent**: The agent responsible for transforming a raw project idea into an implementation-ready project specification including MVP scope, target users, and technical decisions
- **Judge_Optimizer_Agent**: The agent that analyzes the judging rubric, scores the project plan against criteria, and suggests improvements to maximize the judging score
- **Backend_Engineer_Agent**: The agent that implements the FastAPI backend including API endpoints, data models, AI integrations, and unit tests
- **Frontend_Engineer_Agent**: The agent that builds the Next.js frontend with TypeScript, TailwindCSS, and shadcn/ui components
- **Integration_Agent**: The agent that connects frontend and backend components, resolves dependency conflicts, and ensures end-to-end functionality
- **QA_Agent**: The agent that runs unit, integration, and UI tests, reports bugs, and validates application quality
- **Documentation_Agent**: The agent that generates README, developer guide, architecture guide, and API documentation
- **PowerPoint_Agent**: The agent that creates hackathon presentation slides with speaker notes using python-pptx
- **Demo_Video_Agent**: The agent that records an automated demo video with voiceover and captions using Playwright and FFmpeg
- **GitHub_Agent**: The agent that sets up the repository, commits code, and pushes the finished project to GitHub
- **Shared_Workspace**: The unified file system directory where all agents read from and write their artifacts
- **Project_State**: A JSON file (project_state.json) tracking the completion status of each agent phase
- **Blueprint**: The generated project plan including refined idea, elevator pitch, MVP scope, architecture, APIs, database schema, timeline, and judge score prediction
- **Approval_Gate**: A checkpoint where the system pauses execution and requires explicit human approval before proceeding to the next phase
- **Input_Package**: The collection of user-provided documents including hackathon brief, judging rubric, project idea, and preferred technology stack
- **Deliverables**: The complete set of final outputs including MVP source code, documentation, presentation slides, demo video, and GitHub repository

## Requirements

### Requirement 1: Input Collection

**User Story:** As a hackathon participant, I want to upload my hackathon brief, judging rubric, project idea, and preferred tech stack, so that the system has all necessary context to generate my MVP.

#### Acceptance Criteria

1. THE Input_Collector SHALL accept a hackathon brief document in PDF, DOCX, or plain text format with a maximum file size of 10 MB
2. THE Input_Collector SHALL accept a judging rubric document in PDF, DOCX, or plain text format with a maximum file size of 10 MB
3. THE Input_Collector SHALL accept a project idea as free-form text input between 1 and 5000 characters
4. THE Input_Collector SHALL accept a preferred technology stack as a structured selection or free-form text input up to 2000 characters, where providing a technology stack is optional
5. WHEN all required inputs (hackathon brief, judging rubric, and project idea) are provided, THE Input_Collector SHALL validate that each uploaded document is non-empty and that text content can be successfully extracted from it, and that each text input meets its specified length constraints
6. IF any uploaded document fails validation, THEN THE Input_Collector SHALL display an error message identifying the invalid document name and the specific reason for failure (unsupported format, empty content, or unextractable text)
7. WHEN validation succeeds, THE Input_Collector SHALL store all inputs in the Shared_Workspace and transition to the Blueprint Generation phase
8. IF the user does not provide a preferred technology stack, THEN THE Input_Collector SHALL proceed with validation of the remaining required inputs and store a flag in the Shared_Workspace indicating that the system should select a default technology stack during planning

### Requirement 2: Project Planning

**User Story:** As a hackathon participant, I want the system to transform my raw idea into a structured project plan, so that I have a clear implementation-ready specification.

#### Acceptance Criteria

1. WHEN the Input_Package is available in the Shared_Workspace, THE Project_Planner_Agent SHALL generate a project specification containing the following non-empty sections: refined idea (clarified problem statement and proposed solution), elevator pitch (maximum 3 sentences), target users, MVP scope (list of core features limited to what is buildable within the hackathon time constraint), stretch goals, and timeline (broken into phases that fit within the hackathon duration extracted from the brief)
2. THE Project_Planner_Agent SHALL save the project specification as project_spec.md in the Shared_Workspace
3. THE Project_Planner_Agent SHALL constrain the MVP scope to features achievable within the hackathon time limit, team size, and theme requirements as stated in the hackathon brief, and SHALL explicitly state in the project specification which hackathon constraints were applied
4. WHEN all required sections in the project specification are populated and saved to the Shared_Workspace, THE Project_Planner_Agent SHALL update the Project_State to reflect planning completion
5. IF the Input_Package in the Shared_Workspace is missing the hackathon brief or project idea, THEN THE Project_Planner_Agent SHALL update the Project_State to "failed" for the planning phase and report which required input is missing

### Requirement 3: Judge Optimization

**User Story:** As a hackathon participant, I want the system to optimize my project for the judging criteria, so that I maximize my chances of winning.

#### Acceptance Criteria

1. WHEN the project specification is complete, THE Judge_Optimizer_Agent SHALL extract all scoring criteria from the judging rubric and list each criterion with its maximum possible score
2. THE Judge_Optimizer_Agent SHALL score the current project plan against each extracted criterion on a scale of 1 to 10, where 1 represents minimal alignment and 10 represents full alignment with the criterion
3. THE Judge_Optimizer_Agent SHALL generate specific, actionable improvement suggestions for each criterion scoring below 8 out of 10, where each suggestion identifies the target criterion, the proposed change, and the expected score improvement
4. THE Judge_Optimizer_Agent SHALL produce a judge_analysis.md file in the Shared_Workspace containing: criteria list with maximum scores, current scores per criterion, improvement suggestions, predicted total score as a percentage of maximum, and identified tradeoffs and risks
5. WHEN optimization is complete, THE Judge_Optimizer_Agent SHALL update the Project_State to reflect judge optimization completion
6. IF the judging rubric cannot be parsed or contains no extractable scoring criteria, THEN THE Judge_Optimizer_Agent SHALL update the Project_State to "failed" for the optimization phase and notify the user with the parsing error details

### Requirement 4: Architecture Design

**User Story:** As a hackathon participant, I want the system to design a complete technical architecture, so that the development agents have a clear blueprint to follow.

#### Acceptance Criteria

1. WHEN judge optimization is complete, THE Orchestrator SHALL generate an architecture specification based on the optimized project plan and preferred technology stack within 120 seconds
2. THE Orchestrator SHALL produce an architecture.md file containing: system diagram description in text-based diagram notation, folder structure with directory names and purpose annotations, API endpoint definitions each specifying HTTP method and path and request/response structure, database schema listing tables and columns and relationships, component hierarchy mapping UI components to pages, and integration points listing service-to-service connections with protocols
3. THE Orchestrator SHALL produce a roadmap.md file containing: ordered task breakdown with each task assigned to exactly one of the defined agents, a dependency graph specifying which tasks must complete before others can begin, and completion phases where each phase lists its included tasks and the Approval_Gate that follows it
4. THE Orchestrator SHALL validate that architecture.md references only technologies present in the user-provided preferred technology stack or explicitly documented in the project specification
5. WHEN both architecture.md and roadmap.md are saved to the Shared_Workspace, THE Orchestrator SHALL update the Project_State to reflect architecture design completion and trigger the first Approval_Gate, pausing execution until human approval is received
6. IF architecture generation fails or produces an empty file, THEN THE Orchestrator SHALL update the Project_State to "failed" for the architecture phase and notify the user with the failure reason

### Requirement 5: Human Approval Gates

**User Story:** As a hackathon participant, I want to review and approve the system's plan before it starts building, so that I maintain control over the project direction.

#### Acceptance Criteria

1. WHEN an Approval_Gate is triggered, THE Orchestrator SHALL pause all agent execution and present the relevant artifacts to the user for review: architecture.md and roadmap.md for Gate 1, testing_report.md for Gate 2, and the repository URL plus all Deliverables for Gate 3
2. THE Orchestrator SHALL display a summary containing: the list of completed phases, a one-paragraph description of each artifact produced, and the specific next actions that will execute upon approval
3. WHEN the user approves, THE Orchestrator SHALL resume execution from the next workflow phase within 5 seconds
4. WHEN the user requests changes at an Approval_Gate, THE Orchestrator SHALL route the feedback to the appropriate agent for revision and re-trigger the same Approval_Gate after revision, allowing a maximum of 5 revision cycles per gate before escalating to the user with a prompt to either approve the current state or provide alternative direction
5. THE Orchestrator SHALL enforce three Approval_Gates: after architecture generation, after QA testing passes, and before final delivery

### Requirement 6: Backend Development

**User Story:** As a hackathon participant, I want the system to build a complete FastAPI backend, so that my MVP has a functional server-side application.

#### Acceptance Criteria

1. WHEN the first Approval_Gate is passed, THE Backend_Engineer_Agent SHALL implement FastAPI endpoints as defined in architecture.md
2. WHEN the first Approval_Gate is passed, THE Backend_Engineer_Agent SHALL create data models, database schemas, and migration files as specified in architecture.md
3. IF architecture.md specifies AI service integration points, THEN THE Backend_Engineer_Agent SHALL integrate AI service calls (Claude or GPT) with a timeout of 30 seconds per call and a maximum of 3 retry attempts per failed call
4. THE Backend_Engineer_Agent SHALL write at least one unit test per API endpoint using Pytest, covering the nominal success response and one error response
5. THE Backend_Engineer_Agent SHALL save all backend code to the backend/ directory in the Shared_Workspace
6. IF an integrated AI service call fails after all retry attempts are exhausted, THEN THE Backend_Engineer_Agent SHALL implement a fallback response that returns an error indication to the caller without crashing the application
7. WHEN all endpoints are implemented, all unit tests pass, and the FastAPI application starts without errors, THE Backend_Engineer_Agent SHALL update the Project_State to reflect backend completion

### Requirement 7: Frontend Development

**User Story:** As a hackathon participant, I want the system to build a complete Next.js frontend, so that my MVP has a polished user interface.

#### Acceptance Criteria

1. WHEN the first Approval_Gate is passed, THE Frontend_Engineer_Agent SHALL implement the UI using Next.js, TypeScript, TailwindCSS, and shadcn/ui components
2. THE Frontend_Engineer_Agent SHALL build responsive page layouts that render correctly at mobile (360px), tablet (768px), and desktop (1280px) viewport widths as defined in architecture.md
3. THE Frontend_Engineer_Agent SHALL implement client-side state management and API integration with the backend endpoints, including loading states for async operations and error states for failed API calls
4. THE Frontend_Engineer_Agent SHALL save all frontend code to the frontend/ directory in the Shared_Workspace
5. WHEN the frontend application builds without errors and all pages render at the three specified viewport widths, THE Frontend_Engineer_Agent SHALL update the Project_State to reflect frontend completion

### Requirement 8: Integration

**User Story:** As a hackathon participant, I want the system to connect all components together, so that the frontend and backend work as a unified application.

#### Acceptance Criteria

1. WHEN both Backend_Engineer_Agent and Frontend_Engineer_Agent report completion, THE Integration_Agent SHALL configure the frontend API base URL to target the backend server and verify that each API endpoint defined in architecture.md is callable from the frontend and returns a valid response
2. IF the Integration_Agent detects dependency conflicts between frontend and backend packages, THEN THE Integration_Agent SHALL resolve the conflicts such that both applications install dependencies and build without errors
3. THE Integration_Agent SHALL execute at least one end-to-end verification per API endpoint defined in architecture.md, confirming that a UI interaction triggers the correct API call and the backend returns the expected response data
4. IF the Integration_Agent detects an incompatibility during integration, THEN THE Integration_Agent SHALL fix the incompatibility, verify that both applications build and pass integration checks after the fix, and document the resolution in the logs/ directory
5. WHEN integration is complete, THE Integration_Agent SHALL verify that both the frontend and backend applications build successfully, then update the Project_State to reflect integration completion

### Requirement 9: Quality Assurance

**User Story:** As a hackathon participant, I want the system to test the integrated application, so that I can be confident the MVP works correctly.

#### Acceptance Criteria

1. WHEN integration is complete, THE QA_Agent SHALL run all existing unit tests (Pytest for backend, Vitest for frontend)
2. WHEN integration is complete, THE QA_Agent SHALL execute integration tests that verify each API endpoint defined in architecture.md is callable from the frontend and returns a valid response
3. WHEN integration is complete, THE QA_Agent SHALL run UI tests using Playwright to validate user paths defined in the MVP scope section of project_spec.md
4. THE QA_Agent SHALL produce a testing_report.md containing: tests run, pass/fail counts, bug descriptions, and a severity rating for each bug classified as critical (application crash or data loss), major (feature broken but workaround exists), or minor (cosmetic or non-functional issue)
5. IF any bugs with severity "critical" or "major" are detected, THEN THE QA_Agent SHALL route bug reports to the responsible agent (Backend_Engineer_Agent or Frontend_Engineer_Agent) for fixing
6. WHEN all critical and major bugs are resolved and all tests pass, THE QA_Agent SHALL trigger the second Approval_Gate
7. IF bug-fix and re-test iterations reach 3 cycles without resolving all critical and major bugs, THEN THE QA_Agent SHALL halt execution, document the unresolved bugs in testing_report.md, and notify the user with remaining failure details

### Requirement 10: Documentation Generation

**User Story:** As a hackathon participant, I want the system to generate comprehensive documentation, so that judges and developers can understand the project.

#### Acceptance Criteria

1. WHEN the second Approval_Gate is passed, THE Documentation_Agent SHALL generate a README.md containing: project overview sourced from project_spec.md, setup instructions derived from backend/requirements.txt and frontend/package.json, usage guide describing the primary user flow, and technology stack listing all frameworks and tools from architecture.md
2. THE Documentation_Agent SHALL generate a developer_guide.md explaining code organization based on the folder structure in architecture.md, contribution guidelines, and local development setup steps
3. THE Documentation_Agent SHALL generate an api_docs.md listing all endpoints from architecture.md with their HTTP methods, paths, request parameters, and response schemas
4. THE Documentation_Agent SHALL save README.md, developer_guide.md, and api_docs.md to the Shared_Workspace root directory
5. WHEN all three documentation files are saved and each contains at least 200 characters of content, THE Documentation_Agent SHALL update the Project_State to reflect documentation completion
6. IF any required source artifact (project_spec.md, architecture.md, or backend/frontend code) is missing from the Shared_Workspace, THEN THE Documentation_Agent SHALL generate documentation using available artifacts and note in each document which sections are incomplete due to missing sources

### Requirement 11: Presentation Generation

**User Story:** As a hackathon participant, I want the system to create a polished presentation, so that I have professional slides ready for the hackathon demo.

#### Acceptance Criteria

1. WHEN the second Approval_Gate is passed, THE PowerPoint_Agent SHALL generate a hackathon presentation using python-pptx containing between 6 and 15 slides total
2. THE PowerPoint_Agent SHALL include at minimum one slide for each of the following topics: problem statement, solution overview, technical architecture, demo screenshots, team/tooling, and future roadmap
3. THE PowerPoint_Agent SHALL source demo screenshots from image files in the Shared_Workspace that were captured during QA testing, and SHALL use placeholder slides with descriptive text if no screenshot files are available
4. THE PowerPoint_Agent SHALL generate speaker notes of at least 50 characters for each slide summarizing the key talking points for that slide
5. THE PowerPoint_Agent SHALL save the presentation file to the ppt/ directory in the Shared_Workspace
6. IF any required source artifact (project_spec.md, architecture.md) is missing from the Shared_Workspace, THEN THE PowerPoint_Agent SHALL report the missing artifact in the Project_State and skip the corresponding slide topic with a placeholder indicating content is unavailable
7. WHEN presentation generation is complete, THE PowerPoint_Agent SHALL update the Project_State to reflect presentation completion

### Requirement 12: Demo Video Production

**User Story:** As a hackathon participant, I want the system to produce a demo video, so that I have a recorded walkthrough of the working application.

#### Acceptance Criteria

1. WHEN the second Approval_Gate is passed, THE Demo_Video_Agent SHALL record an automated demo of the running application using Playwright, covering each critical user path defined in architecture.md, with a total video duration between 60 and 300 seconds
2. THE Demo_Video_Agent SHALL generate voiceover narration describing each demonstrated feature, synchronized with the corresponding screen recording segment
3. THE Demo_Video_Agent SHALL add burned-in captions to the video that display the narration text synchronized with the voiceover audio
4. THE Demo_Video_Agent SHALL encode the final video using FFmpeg in MP4 format at a minimum resolution of 1280x720 pixels
5. THE Demo_Video_Agent SHALL save the demo video to the video/ directory in the Shared_Workspace
6. WHEN video production is complete, THE Demo_Video_Agent SHALL update the Project_State to reflect video completion
7. IF the application fails to start or Playwright recording fails, THEN THE Demo_Video_Agent SHALL log the failure reason, update the Project_State to "failed" for the video phase, and notify the user with an error message indicating the cause of failure

### Requirement 13: GitHub Repository Setup and Push

**User Story:** As a hackathon participant, I want the system to push the complete project to GitHub, so that I have a public repository ready for submission.

#### Acceptance Criteria

1. WHEN the second Approval_Gate is passed, THE GitHub_Agent SHALL create a new public GitHub repository using the GitHub API, with the repository name derived from the project name in project_spec.md
2. THE GitHub_Agent SHALL create separate commits in the following order: initial setup, backend, frontend, integration, docs, presentation
3. THE GitHub_Agent SHALL configure the repository with a .gitignore matching the project's technology stack (Python and Node.js patterns), an MIT LICENSE file, and branch protection on the main branch requiring at least one approval for pull requests
4. THE GitHub_Agent SHALL push all Shared_Workspace contents to the repository's main branch
5. WHEN the push is complete, THE GitHub_Agent SHALL trigger the third Approval_Gate presenting the repository URL and all final Deliverables for user review
6. IF the GitHub API returns an error during repository creation or push (including authentication failure, name conflict, or rate limiting), THEN THE GitHub_Agent SHALL retry the operation up to 3 times with a 5-second delay between attempts, and if all retries fail, update the Project_State to "failed" and notify the user with the specific error reason

### Requirement 14: Agent Coordination and Shared State

**User Story:** As a hackathon participant, I want all agents to work together without conflicts, so that the system produces a coherent and complete MVP.

#### Acceptance Criteria

1. THE Orchestrator SHALL maintain Project_State as a JSON file tracking each agent phase with statuses: pending, in_progress, completed, or failed, and SHALL update the status atomically before and after each agent execution
2. THE Orchestrator SHALL execute Backend_Engineer_Agent and Frontend_Engineer_Agent in parallel during the Development phase, where failure of one agent does not block the other from completing
3. THE Orchestrator SHALL execute Documentation_Agent, PowerPoint_Agent, Demo_Video_Agent, and GitHub_Agent in parallel during the Delivery phase, where failure of one agent does not block the others from completing
4. WHEN an agent attempts to read an artifact from the Shared_Workspace, THE Orchestrator SHALL verify that the artifact file exists and that the producing agent's phase is marked as "completed" in Project_State before allowing the read to proceed
5. IF an agent fails during execution, THEN THE Orchestrator SHALL log the failure with timestamp and error details to logs/failures.log, update the Project_State to "failed" for that phase, and notify the user with the agent name and failure reason within 10 seconds
6. THE Orchestrator SHALL enforce that no agent overwrites another agent's output file without explicit dependency justification documented in the logs/ directory
7. IF an agent does not complete within 600 seconds of starting, THEN THE Orchestrator SHALL terminate the agent, mark its phase as "failed" in Project_State, and notify the user with a timeout error

### Requirement 15: Development Dashboard

**User Story:** As a hackathon participant, I want to monitor the progress of each agent in real time, so that I can see what the system is doing and how far along the project is.

#### Acceptance Criteria

1. THE Dashboard SHALL display the current workflow phase (Planning, Development, or Delivery) as a labeled header or indicator
2. THE Dashboard SHALL display each of the 10 agents' statuses (pending, in_progress, completed, or failed) by polling the Project_State file at intervals no greater than 3 seconds
3. THE Dashboard SHALL display log entries from each agent within 5 seconds of the log entry being written to the logs/ directory
4. WHEN an agent's status changes in Project_State, THE Dashboard SHALL update the corresponding agent's visual status indicator within 5 seconds of the change
5. THE Dashboard SHALL provide a final deliverables view listing all generated artifacts with download links upon all Delivery phase agents reaching "completed" status
6. IF an agent's status is "failed", THEN THE Dashboard SHALL display the failure reason from Project_State alongside the agent's status indicator

### Requirement 16: Artifact Integrity

**User Story:** As a hackathon participant, I want all generated artifacts to be valid and reusable, so that I can confidently submit the project.

#### Acceptance Criteria

1. THE Orchestrator SHALL validate that each agent's output files have a file size greater than 0 bytes and conform to their agent-specific format checks (as defined in criteria 2-5) before marking the phase as completed
2. WHEN the Backend_Engineer_Agent completes, THE Orchestrator SHALL verify that the backend/ directory contains a main application entry point, that all Python files pass syntax validation, that a requirements.txt exists listing fastapi as a dependency, and that the requirements.txt is parseable by pip
3. WHEN the Frontend_Engineer_Agent completes, THE Orchestrator SHALL verify that the frontend/ directory contains a package.json with a "build" script defined, that "next" is listed as a dependency, and that the package.json is valid parseable JSON containing name and dependencies fields
4. WHEN the PowerPoint_Agent completes, THE Orchestrator SHALL verify that the generated .pptx file is a well-formed ZIP archive conforming to OOXML structure and contains at least 6 slides
5. WHEN the Demo_Video_Agent completes, THE Orchestrator SHALL verify that the generated .mp4 file is decodable, contains at least one video stream, and has a duration of at least 5 seconds
6. IF any artifact fails validation, THEN THE Orchestrator SHALL mark the corresponding agent phase as "failed" in the Project_State, log the specific validation error, and notify the user with the artifact name and reason for failure
