# Hackathon Studio

An autonomous multi-agent AI software studio that transforms a hackathon brief, judging rubric, and project idea into a complete hackathon-ready MVP.

## What It Does

Instead of simply generating code, Hackathon Studio behaves like an AI software company where 10 specialized agents collaborate to:

- Refine your idea and optimize for the judging rubric
- Design the technical architecture
- Build the backend (FastAPI) and frontend (Next.js)
- Integrate and test everything
- Generate presentation slides, a demo video, and push to GitHub

You only need to approve major milestones — everything else is automated.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Next.js Frontend                    │
│         (Dashboard, Input, Monitor, Approval)        │
└─────────────────────┬───────────────────────────────┘
                      │ REST + SSE
┌─────────────────────▼───────────────────────────────┐
│                  FastAPI Backend                      │
│              (API Layer + Orchestrator)               │
├──────────────────────────────────────────────────────┤
│              LangGraph State Machine                  │
│   Planning → Development → Delivery (with gates)     │
├──────────────────────────────────────────────────────┤
│                  10 AI Agents                         │
│  Planner │ Judge │ Backend │ Frontend │ Integration  │
│  QA │ Docs │ PowerPoint │ Demo Video │ GitHub        │
└─────────────────────┬───────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────┐
│              Ollama (Local LLM)                       │
│         No API keys needed — runs locally            │
└──────────────────────────────────────────────────────┘
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14, TypeScript, TailwindCSS, shadcn/ui |
| Backend | Python, FastAPI |
| Orchestration | LangGraph |
| LLM | Ollama (local — llama3, codellama, mistral, etc.) |
| Presentation | python-pptx |
| Demo Recording | Playwright + FFmpeg |
| Testing | Pytest, Vitest, Playwright |
| GitHub | PyGithub |

## Prerequisites

- **Python 3.11+**
- **Node.js 18+**
- **Ollama** installed and running (`ollama serve`)
- **FFmpeg** (optional, for demo video generation)
- A pulled Ollama model (e.g., `ollama pull llama3`)

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/daerenkim/aws_hackathon.git
cd aws_hackathon
```

### 2. Start the backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 3. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

### 4. Make sure Ollama is running

```bash
# Check if Ollama is already running
curl http://localhost:11434/api/tags

# If not running, start it
ollama serve
```

### 5. Open the dashboard

Navigate to [http://localhost:3000](http://localhost:3000) in your browser.

## How It Works

### Workflow Phases

1. **Input** — Upload your hackathon brief, judging rubric, project idea, and preferred tech stack
2. **Planning** — Project Planner refines the idea → Judge Optimizer scores against rubric → Architecture designed
3. **Approval Gate 1** — Review and approve the architecture
4. **Development** — Backend + Frontend agents build in parallel → Integration connects them → QA tests everything
5. **Approval Gate 2** — Review test results
6. **Delivery** — Docs, slides, demo video, and GitHub push run in parallel
7. **Approval Gate 3** — Final review of all deliverables

### The 10 Agents

| Agent | Role |
|-------|------|
| Project Planner | Transforms idea into implementation-ready spec |
| Judge Optimizer | Maximizes judging score |
| Backend Engineer | Builds FastAPI endpoints and tests |
| Frontend Engineer | Builds Next.js UI with responsive design |
| Integration | Connects frontend ↔ backend |
| QA | Runs tests, reports bugs, validates quality |
| Documentation | Generates README, dev guide, API docs |
| PowerPoint | Creates hackathon presentation slides |
| Demo Video | Records automated demo with voiceover |
| GitHub | Pushes project to a public repository |

## Configuration

Environment variables (all optional with sensible defaults):

```bash
# Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3
OLLAMA_TIMEOUT=120

# Workspace
WORKSPACE_PATH=./shared_workspace

# GitHub (required only for the GitHub agent)
GITHUB_TOKEN=ghp_your_token_here
```

## Project Structure

```
aws_hackathon/
├── backend/
│   ├── app/
│   │   ├── agents/          # 10 specialized AI agents
│   │   ├── api/routes/      # FastAPI endpoints
│   │   ├── orchestrator/    # LangGraph state machine
│   │   ├── services/        # Ollama client, state manager, workspace
│   │   └── models/          # Pydantic data models
│   ├── tests/               # Unit tests
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── app/             # Next.js pages
│   │   ├── components/      # Shared UI components
│   │   ├── hooks/           # SSE and state hooks
│   │   └── lib/             # API client and types
│   └── package.json
└── shared_workspace/        # Runtime artifact directory (created at runtime)
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/inputs/upload` | Upload hackathon brief or rubric |
| POST | `/api/inputs/submit` | Submit project idea and tech stack |
| GET | `/api/inputs/status` | Check input validation status |
| POST | `/api/workflow/start` | Start the orchestration pipeline |
| GET | `/api/workflow/state` | Get current project state |
| POST | `/api/workflow/approve` | Approve at an approval gate |
| POST | `/api/workflow/request-change` | Request revisions at a gate |
| GET | `/api/stream/status` | SSE stream for real-time state |
| GET | `/api/stream/logs/{agent}` | SSE stream for agent logs |
| GET | `/api/deliverables` | List all generated artifacts |
| GET | `/api/deliverables/{path}` | Download a specific artifact |

## License

MIT
