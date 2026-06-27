"""Backend Engineer Agent for Hackathon Studio.

Reads architecture.md and generates a complete FastAPI backend including
API endpoints, Pydantic models, database schemas, unit tests, and a
main.py entry point. Integrates AI service calls with 30s timeout,
3 retries, and fallback responses.

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7
"""

import logging
import time

from app.agents.base import BaseAgent
from app.models.artifacts import AgentResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a senior backend engineer. Generate production-quality FastAPI code "
    "with type hints, error handling, input validation, logging, and comprehensive "
    "unit tests. Follow Python best practices: PEP 8 formatting, docstrings, "
    "proper HTTP status codes, and Pydantic models for request/response validation."
)

# AI service integration defaults
AI_SERVICE_TIMEOUT_SECONDS = 30
AI_SERVICE_MAX_RETRIES = 3

# Maximum LLM generation retries for malformed output
MAX_GENERATION_RETRIES = 2


class BackendEngineerAgent(BaseAgent):
    """Agent that generates a complete FastAPI backend from architecture.md.

    Reads the architecture specification from the workspace and uses the
    LLM to generate FastAPI route code, Pydantic models, database schemas,
    unit tests, and a main.py entry point. When architecture specifies AI
    integration, generates code with 30s timeout, 3 retries, and fallback.

    Write boundary: backend/

    Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7
    """

    async def execute(self, context: dict) -> AgentResult:
        """Execute backend code generation from architecture.md.

        Workflow:
        1. Read architecture.md from workspace (produced by project_planner)
        2. Parse architecture to identify endpoints, models, and integrations
        3. Generate FastAPI code for each endpoint with Pydantic models
        4. Generate AI service integration with timeout/retry/fallback if needed
        5. Generate unit tests (one per endpoint: success + error case)
        6. Generate requirements.txt and main.py entry point
        7. Write all files to backend/ directory

        Args:
            context: Dictionary with optional overrides. Currently unused.

        Returns:
            AgentResult indicating success/failure with list of artifacts.
        """
        start_time = time.monotonic()
        artifacts_produced: list[str] = []

        # Step 1: Read architecture.md
        await self.log("Reading architecture.md from workspace...")
        try:
            architecture = await self.read_artifact(
                "architecture.md", "project_planner"
            )
        except (PermissionError, FileNotFoundError) as e:
            error_msg = f"Cannot read architecture.md: {e}"
            await self.log(error_msg)
            return AgentResult(
                agent_name=self.agent_name,
                success=False,
                artifacts_produced=[],
                error=error_msg,
                duration_seconds=time.monotonic() - start_time,
            )

        # Step 2: Generate the backend implementation plan
        await self.log("Analyzing architecture and planning implementation...")
        implementation_plan = await self._generate_implementation_plan(architecture)

        # Step 3: Generate requirements.txt
        await self.log("Generating requirements.txt...")
        requirements_content = await self._generate_requirements(architecture)
        await self.write_artifact("backend/requirements.txt", requirements_content)
        artifacts_produced.append("backend/requirements.txt")

        # Step 4: Generate Pydantic models
        await self.log("Generating data models...")
        models_content = await self._generate_models(architecture)
        await self.write_artifact("backend/models.py", models_content)
        artifacts_produced.append("backend/models.py")

        # Step 5: Generate AI service integration if specified
        has_ai_integration = self._architecture_has_ai_integration(architecture)
        if has_ai_integration:
            await self.log(
                "Architecture specifies AI integration. Generating AI service "
                f"with {AI_SERVICE_TIMEOUT_SECONDS}s timeout and "
                f"{AI_SERVICE_MAX_RETRIES} retries..."
            )
            ai_service_content = await self._generate_ai_service(architecture)
            await self.write_artifact("backend/ai_service.py", ai_service_content)
            artifacts_produced.append("backend/ai_service.py")

        # Step 6: Generate FastAPI routes/endpoints
        await self.log("Generating FastAPI endpoints...")
        routes_content = await self._generate_routes(
            architecture, has_ai_integration
        )
        await self.write_artifact("backend/routes.py", routes_content)
        artifacts_produced.append("backend/routes.py")

        # Step 7: Generate main.py entry point
        await self.log("Generating main.py entry point...")
        main_content = await self._generate_main(architecture, has_ai_integration)
        await self.write_artifact("backend/main.py", main_content)
        artifacts_produced.append("backend/main.py")

        # Step 8: Generate unit tests
        await self.log("Generating unit tests...")
        tests_content = await self._generate_tests(
            architecture, has_ai_integration
        )
        await self.write_artifact("backend/test_main.py", tests_content)
        artifacts_produced.append("backend/test_main.py")

        elapsed = time.monotonic() - start_time
        await self.log(
            f"Backend generation complete. {len(artifacts_produced)} files produced "
            f"in {elapsed:.1f}s."
        )

        return AgentResult(
            agent_name=self.agent_name,
            success=True,
            artifacts_produced=artifacts_produced,
            duration_seconds=elapsed,
        )

    async def _generate_implementation_plan(self, architecture: str) -> str:
        """Ask LLM to break down architecture into implementation tasks.

        Args:
            architecture: Content of architecture.md.

        Returns:
            Implementation plan text from LLM.
        """
        prompt = (
            "Analyze the following architecture specification and produce a "
            "concise implementation plan listing:\n"
            "1. API endpoints to implement (method, path, purpose)\n"
            "2. Data models needed (Pydantic)\n"
            "3. Database tables/schemas if any\n"
            "4. AI service integrations if specified\n"
            "5. Key dependencies\n\n"
            "--- ARCHITECTURE ---\n"
            f"{architecture}\n\n"
            "Produce a structured plan. Be concise."
        )
        return await self.llm_generate(prompt, system=SYSTEM_PROMPT)

    async def _generate_requirements(self, architecture: str) -> str:
        """Generate requirements.txt with necessary dependencies.

        Args:
            architecture: Content of architecture.md.

        Returns:
            Contents for requirements.txt.
        """
        prompt = (
            "Based on the following architecture, generate a Python "
            "requirements.txt file. Always include:\n"
            "- fastapi\n"
            "- uvicorn[standard]\n"
            "- pydantic\n"
            "- pytest\n"
            "- httpx\n\n"
            "Add any other packages implied by the architecture (e.g., "
            "sqlalchemy for databases, openai/anthropic for AI services, "
            "python-multipart for file uploads, etc.).\n\n"
            "Output ONLY the requirements.txt content — one package per line, "
            "no comments, no explanations.\n\n"
            "--- ARCHITECTURE ---\n"
            f"{architecture}"
        )

        result = await self.llm_generate(prompt, system=SYSTEM_PROMPT)

        # Ensure minimum required packages are present
        required = ["fastapi", "uvicorn", "pydantic", "pytest", "httpx"]
        lines = [line.strip() for line in result.strip().split("\n") if line.strip()]

        for pkg in required:
            if not any(pkg in line.lower() for line in lines):
                lines.append(pkg)

        return "\n".join(lines) + "\n"

    async def _generate_models(self, architecture: str) -> str:
        """Generate Pydantic data models from architecture spec.

        Args:
            architecture: Content of architecture.md.

        Returns:
            Python source code with Pydantic model definitions.
        """
        prompt = (
            "Based on the following architecture specification, generate Python "
            "Pydantic models for all data structures mentioned (request bodies, "
            "response models, database schemas).\n\n"
            "Requirements:\n"
            "- Use Pydantic v2 BaseModel\n"
            "- Include type hints for all fields\n"
            "- Add Field() with descriptions where appropriate\n"
            "- Include validators where constraints are specified\n"
            "- Include docstrings for each model\n\n"
            "Output ONLY valid Python code. Start with imports.\n\n"
            "--- ARCHITECTURE ---\n"
            f"{architecture}"
        )
        return await self.llm_generate(prompt, system=SYSTEM_PROMPT)

    async def _generate_ai_service(self, architecture: str) -> str:
        """Generate AI service integration code with timeout/retry/fallback.

        Generates code that:
        - Calls AI service (Claude or GPT) with 30s timeout per call
        - Retries up to 3 times on failure with exponential backoff
        - Returns a fallback error response if all retries fail

        Args:
            architecture: Content of architecture.md.

        Returns:
            Python source code for the AI service module.
        """
        prompt = (
            "Generate a Python module for AI service integration based on the "
            "architecture below.\n\n"
            "REQUIREMENTS:\n"
            f"- Each AI service call MUST have a {AI_SERVICE_TIMEOUT_SECONDS}s timeout\n"
            f"- Failed calls MUST retry up to {AI_SERVICE_MAX_RETRIES} times "
            "with exponential backoff (2s, 4s, 8s delays)\n"
            "- If ALL retries fail, return a fallback error response that:\n"
            "  - Returns an error indication to the caller\n"
            "  - Does NOT crash the application\n"
            "  - Logs the failure details\n"
            "- Use httpx.AsyncClient for HTTP calls\n"
            "- Use environment variables for API keys (os.environ)\n"
            "- Include proper error handling and logging\n"
            "- Include a dataclass or model for the response\n\n"
            "Output ONLY valid Python code. Start with imports.\n\n"
            "--- ARCHITECTURE ---\n"
            f"{architecture}"
        )
        return await self.llm_generate(prompt, system=SYSTEM_PROMPT)

    async def _generate_routes(
        self, architecture: str, has_ai_integration: bool
    ) -> str:
        """Generate FastAPI route definitions from architecture spec.

        Args:
            architecture: Content of architecture.md.
            has_ai_integration: Whether AI service integration is needed.

        Returns:
            Python source code with FastAPI router and endpoint definitions.
        """
        ai_instruction = ""
        if has_ai_integration:
            ai_instruction = (
                "\n- For endpoints that use AI services, import and call the "
                "ai_service module. Handle AIServiceError gracefully by returning "
                "an appropriate HTTP error response (503 Service Unavailable) "
                "without crashing.\n"
            )

        prompt = (
            "Generate FastAPI route definitions for all API endpoints specified "
            "in the architecture below.\n\n"
            "REQUIREMENTS:\n"
            "- Use APIRouter for route grouping\n"
            "- Use Pydantic models from models.py for request/response validation\n"
            "- Include proper HTTP status codes\n"
            "- Use HTTPException for error responses\n"
            "- Include input validation\n"
            "- Use environment variables for configuration (os.environ)\n"
            "- Include logging for each endpoint\n"
            "- Add docstrings to each endpoint function\n"
            f"{ai_instruction}\n"
            "Output ONLY valid Python code. Start with imports. "
            "Import models from models.py.\n\n"
            "--- ARCHITECTURE ---\n"
            f"{architecture}"
        )
        return await self.llm_generate(prompt, system=SYSTEM_PROMPT)

    async def _generate_main(
        self, architecture: str, has_ai_integration: bool
    ) -> str:
        """Generate the main.py FastAPI application entry point.

        Args:
            architecture: Content of architecture.md.
            has_ai_integration: Whether AI service integration is needed.

        Returns:
            Python source code for main.py.
        """
        prompt = (
            "Generate a FastAPI main.py entry point that:\n"
            "- Creates the FastAPI application with title and description\n"
            "- Configures CORS middleware (allow all origins for dev)\n"
            "- Includes the router from routes.py\n"
            "- Adds a health check endpoint at /health\n"
            "- Configures uvicorn to run when executed directly\n"
            "- Uses environment variables for host/port configuration\n"
            "- Includes proper logging setup\n\n"
            "The routes are defined in routes.py using APIRouter.\n\n"
            "Output ONLY valid Python code. Start with imports.\n\n"
            "--- ARCHITECTURE ---\n"
            f"{architecture}"
        )
        return await self.llm_generate(prompt, system=SYSTEM_PROMPT)

    async def _generate_tests(
        self, architecture: str, has_ai_integration: bool
    ) -> str:
        """Generate pytest unit tests for the FastAPI endpoints.

        Generates at least one test per endpoint covering:
        - Success response (nominal path)
        - Error response (invalid input, service failure, etc.)

        Args:
            architecture: Content of architecture.md.
            has_ai_integration: Whether AI service integration is tested.

        Returns:
            Python source code with pytest test functions.
        """
        ai_test_instruction = ""
        if has_ai_integration:
            ai_test_instruction = (
                "\n- For AI-integrated endpoints, include a test that mocks "
                "AI service failure and verifies the fallback response "
                "(503 status code with error message).\n"
            )

        prompt = (
            "Generate pytest unit tests for the FastAPI application defined "
            "in the architecture below.\n\n"
            "REQUIREMENTS:\n"
            "- Use httpx.AsyncClient with ASGITransport for async testing\n"
            "- Test EACH endpoint with at least:\n"
            "  1. A success case (valid input → expected response)\n"
            "  2. An error case (invalid input → appropriate error)\n"
            "- Use pytest.mark.asyncio for async tests\n"
            "- Include a conftest-style fixture for the test client\n"
            "- Use descriptive test names (test_<endpoint>_<scenario>)\n"
            f"{ai_test_instruction}\n"
            "Output ONLY valid Python code. Start with imports.\n\n"
            "--- ARCHITECTURE ---\n"
            f"{architecture}"
        )
        return await self.llm_generate(prompt, system=SYSTEM_PROMPT)

    def _architecture_has_ai_integration(self, architecture: str) -> bool:
        """Check if the architecture specifies AI service integration points.

        Looks for common AI-related keywords that indicate the backend
        needs to integrate with external AI services.

        Args:
            architecture: Content of architecture.md.

        Returns:
            True if AI integration is specified, False otherwise.
        """
        ai_keywords = [
            "ai service",
            "ai integration",
            "openai",
            "claude",
            "gpt",
            "llm",
            "language model",
            "anthropic",
            "ai endpoint",
            "ai-powered",
            "ml service",
            "inference",
            "completion api",
            "chat api",
        ]
        architecture_lower = architecture.lower()
        return any(keyword in architecture_lower for keyword in ai_keywords)
