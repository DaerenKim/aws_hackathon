"""QA Agent for Hackathon Studio.

Runs unit tests (pytest for backend, vitest for frontend), UI tests (Playwright),
produces a testing_report.md with pass/fail counts, bug descriptions, and severity
ratings. Routes critical/major bugs to responsible agents for fixing and halts
after 3 fix cycles if unresolved.

Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7
"""

import logging
import time

from app.agents.base import BaseAgent
from app.models.artifacts import AgentResult

logger = logging.getLogger(__name__)

# Maximum number of bug-fix and re-test iterations before halting
MAX_FIX_CYCLES = 3

# System prompt for the QA agent's LLM calls
QA_SYSTEM_PROMPT = (
    "You are a QA engineer. Analyze the codebase for bugs, security issues, "
    "and quality problems. Classify severity strictly: "
    "critical = crash/data loss, major = broken feature, minor = cosmetic."
)

# Prompt for analyzing backend code and simulating pytest results
BACKEND_TEST_PROMPT = """Analyze the following backend code as a QA engineer running pytest.
Identify potential bugs, failing tests, and quality issues.

## Architecture Spec:
{architecture}

## Backend Code:
{backend_code}

## Response Format (respond EXACTLY in this format):
TESTS_RUN: [number]
TESTS_PASSED: [number]
TESTS_FAILED: [number]

BUGS:
- ID: BUG-[number] | Severity: [critical|major|minor] | Description: [description] | Agent: backend_engineer
...

If no bugs found, write:
BUGS:
NONE
"""

# Prompt for analyzing frontend code and simulating vitest results
FRONTEND_TEST_PROMPT = """Analyze the following frontend code as a QA engineer running vitest.
Identify potential bugs, failing tests, and quality issues.

## Architecture Spec:
{architecture}

## Frontend Code:
{frontend_code}

## Response Format (respond EXACTLY in this format):
TESTS_RUN: [number]
TESTS_PASSED: [number]
TESTS_FAILED: [number]

BUGS:
- ID: BUG-[number] | Severity: [critical|major|minor] | Description: [description] | Agent: frontend_engineer
...

If no bugs found, write:
BUGS:
NONE
"""

# Prompt for simulating Playwright UI tests
UI_TEST_PROMPT = """Analyze the following project code as a QA engineer running Playwright UI tests.
Consider the user paths defined in the MVP scope and check for UI/UX bugs.

## Project Spec (MVP Scope / User Paths):
{project_spec}

## Architecture:
{architecture}

## Frontend Code:
{frontend_code}

## Backend Code:
{backend_code}

## Response Format (respond EXACTLY in this format):
TESTS_RUN: [number]
TESTS_PASSED: [number]
TESTS_FAILED: [number]

BUGS:
- ID: BUG-[number] | Severity: [critical|major|minor] | Description: [description] | Agent: [backend_engineer|frontend_engineer|integration]
...

If no bugs found, write:
BUGS:
NONE
"""

# Prompt for generating fix suggestions for bugs
FIX_SUGGESTION_PROMPT = """Given the following bugs found during QA testing, provide specific fix suggestions
for each critical and major bug. Be concise and actionable.

## Bugs:
{bugs}

## Response Format:
- BUG-[id]: [Fix suggestion in one sentence]
...
"""


def parse_test_results(response: str) -> dict:
    """Parse test results from an LLM response.

    Args:
        response: Raw LLM response text containing test results.

    Returns:
        Dict with keys: tests_run, tests_passed, tests_failed, bugs.
        bugs is a list of dicts with: id, severity, description, agent.
    """
    import re

    results: dict = {
        "tests_run": 0,
        "tests_passed": 0,
        "tests_failed": 0,
        "bugs": [],
    }

    # Parse test counts
    run_match = re.search(r"TESTS_RUN:\s*(\d+)", response)
    passed_match = re.search(r"TESTS_PASSED:\s*(\d+)", response)
    failed_match = re.search(r"TESTS_FAILED:\s*(\d+)", response)

    if run_match:
        results["tests_run"] = int(run_match.group(1))
    if passed_match:
        results["tests_passed"] = int(passed_match.group(1))
    if failed_match:
        results["tests_failed"] = int(failed_match.group(1))

    # Parse bugs
    bugs_section = re.search(r"BUGS:\s*\n(.*?)$", response, re.DOTALL)
    if bugs_section:
        bugs_text = bugs_section.group(1).strip()
        if bugs_text.upper() != "NONE":
            bug_pattern = re.compile(
                r"-\s*ID:\s*(BUG-\d+)\s*\|\s*Severity:\s*(critical|major|minor)"
                r"\s*\|\s*Description:\s*(.+?)\s*\|\s*Agent:\s*(\w+)",
                re.IGNORECASE,
            )
            for match in bug_pattern.finditer(bugs_text):
                results["bugs"].append({
                    "id": match.group(1),
                    "severity": match.group(2).lower(),
                    "description": match.group(3).strip(),
                    "agent": match.group(4).strip(),
                })

    return results


def generate_testing_report(
    backend_results: dict,
    frontend_results: dict,
    ui_results: dict,
    fix_suggestions: dict[str, str] | None = None,
    fix_cycle: int = 0,
    unresolved_bugs: list[dict] | None = None,
) -> str:
    """Generate the testing_report.md content.

    Sections:
    - Test Summary (total, passed, failed)
    - Unit Tests (backend pytest results)
    - Frontend Tests (vitest results)
    - UI Tests (playwright results)
    - Bug Report (table: ID | Severity | Description | Responsible Agent | Status)
    - Recommendations

    Args:
        backend_results: Parsed backend test results.
        frontend_results: Parsed frontend test results.
        ui_results: Parsed UI test results.
        fix_suggestions: Optional dict mapping bug IDs to fix suggestions.
        fix_cycle: Current fix cycle number (0 = initial run).
        unresolved_bugs: List of bugs that remain unresolved after max cycles.

    Returns:
        Formatted markdown string for testing_report.md.
    """
    total_run = (
        backend_results["tests_run"]
        + frontend_results["tests_run"]
        + ui_results["tests_run"]
    )
    total_passed = (
        backend_results["tests_passed"]
        + frontend_results["tests_passed"]
        + ui_results["tests_passed"]
    )
    total_failed = (
        backend_results["tests_failed"]
        + frontend_results["tests_failed"]
        + ui_results["tests_failed"]
    )

    all_bugs = (
        backend_results["bugs"]
        + frontend_results["bugs"]
        + ui_results["bugs"]
    )

    lines: list[str] = []
    lines.append("# Testing Report\n")

    # Test Summary
    lines.append("## Test Summary\n")
    lines.append(f"- **Total Tests Run**: {total_run}")
    lines.append(f"- **Tests Passed**: {total_passed}")
    lines.append(f"- **Tests Failed**: {total_failed}")
    lines.append(f"- **Pass Rate**: {_pass_rate(total_passed, total_run)}")
    if fix_cycle > 0:
        lines.append(f"- **Fix Cycles Completed**: {fix_cycle}/{MAX_FIX_CYCLES}")
    lines.append("")

    # Unit Tests (Backend)
    lines.append("## Unit Tests (Backend - Pytest)\n")
    lines.append(f"- Tests Run: {backend_results['tests_run']}")
    lines.append(f"- Passed: {backend_results['tests_passed']}")
    lines.append(f"- Failed: {backend_results['tests_failed']}")
    if backend_results["bugs"]:
        lines.append(f"- Bugs Found: {len(backend_results['bugs'])}")
    else:
        lines.append("- Bugs Found: 0")
    lines.append("")

    # Frontend Tests
    lines.append("## Frontend Tests (Vitest)\n")
    lines.append(f"- Tests Run: {frontend_results['tests_run']}")
    lines.append(f"- Passed: {frontend_results['tests_passed']}")
    lines.append(f"- Failed: {frontend_results['tests_failed']}")
    if frontend_results["bugs"]:
        lines.append(f"- Bugs Found: {len(frontend_results['bugs'])}")
    else:
        lines.append("- Bugs Found: 0")
    lines.append("")

    # UI Tests
    lines.append("## UI Tests (Playwright)\n")
    lines.append(f"- Tests Run: {ui_results['tests_run']}")
    lines.append(f"- Passed: {ui_results['tests_passed']}")
    lines.append(f"- Failed: {ui_results['tests_failed']}")
    if ui_results["bugs"]:
        lines.append(f"- Bugs Found: {len(ui_results['bugs'])}")
    else:
        lines.append("- Bugs Found: 0")
    lines.append("")

    # Bug Report
    lines.append("## Bug Report\n")
    if all_bugs:
        lines.append(
            "| ID | Severity | Description | Responsible Agent | Status |"
        )
        lines.append(
            "|-----|----------|-------------|-------------------|--------|"
        )
        for bug in all_bugs:
            status = "Open"
            if unresolved_bugs and bug["id"] in [
                b["id"] for b in unresolved_bugs
            ]:
                status = "Unresolved"
            elif fix_cycle > 0 and bug["severity"] in ("critical", "major"):
                status = "Fix Attempted"
            lines.append(
                f"| {bug['id']} | {bug['severity'].capitalize()} | "
                f"{bug['description']} | {bug['agent']} | {status} |"
            )
        lines.append("")

        # Fix suggestions if available
        if fix_suggestions:
            lines.append("### Fix Suggestions\n")
            for bug_id, suggestion in fix_suggestions.items():
                lines.append(f"- **{bug_id}**: {suggestion}")
            lines.append("")
    else:
        lines.append("No bugs found. All tests passed successfully.\n")

    # Recommendations
    lines.append("## Recommendations\n")
    critical_bugs = [b for b in all_bugs if b["severity"] == "critical"]
    major_bugs = [b for b in all_bugs if b["severity"] == "major"]
    minor_bugs = [b for b in all_bugs if b["severity"] == "minor"]

    if not all_bugs:
        lines.append(
            "- All tests pass. The application is ready for approval gate 2."
        )
    else:
        if critical_bugs:
            lines.append(
                f"- **{len(critical_bugs)} critical bug(s)** must be fixed "
                f"before proceeding. These cause crashes or data loss."
            )
        if major_bugs:
            lines.append(
                f"- **{len(major_bugs)} major bug(s)** should be fixed. "
                f"These represent broken features."
            )
        if minor_bugs:
            lines.append(
                f"- {len(minor_bugs)} minor bug(s) are cosmetic and "
                f"non-blocking."
            )
        if unresolved_bugs:
            lines.append(
                f"\n**WARNING**: {len(unresolved_bugs)} bug(s) remain "
                f"unresolved after {MAX_FIX_CYCLES} fix cycles. "
                f"Manual intervention required."
            )
    lines.append("")

    return "\n".join(lines)


def _pass_rate(passed: int, total: int) -> str:
    """Calculate pass rate as a formatted percentage string.

    Args:
        passed: Number of tests passed.
        total: Total number of tests run.

    Returns:
        Formatted string like "95.5%" or "N/A" if total is 0.
    """
    if total == 0:
        return "N/A"
    return f"{(passed / total) * 100:.1f}%"


class QAAgent(BaseAgent):
    """Agent that runs tests and produces quality assurance reports.

    Simulates running pytest (backend), vitest (frontend), and Playwright
    (UI) tests by analyzing project code through the LLM. Produces a
    testing_report.md with pass/fail counts, bug descriptions, and severity
    ratings. Routes critical/major bugs to responsible agents and halts
    after 3 fix cycles if unresolved.

    Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7
    """

    def __init__(self, ollama_client, workspace, state_manager):
        """Initialize the QA Agent.

        Args:
            ollama_client: Client for Ollama LLM interaction.
            workspace: Shared workspace service.
            state_manager: Project state manager.
        """
        super().__init__(
            agent_name="qa",
            ollama_client=ollama_client,
            workspace=workspace,
            state_manager=state_manager,
        )

    async def execute(self, context: dict) -> AgentResult:
        """Execute QA testing and reporting.

        Steps:
        1. Read architecture.md and project_spec.md for test criteria
        2. Read backend and frontend code for analysis
        3. Simulate pytest (backend), vitest (frontend), Playwright (UI)
        4. Classify bugs by severity (critical/major/minor)
        5. Generate testing_report.md
        6. Route critical/major bugs to responsible agents
        7. Track fix cycles (max 3), halt if unresolved
        8. If all tests pass, set context flag for approval gate 2

        Args:
            context: Execution context dict. May contain:
                - fix_cycle (int): Current fix cycle count (default 0).

        Returns:
            AgentResult with success status and artifacts produced.
        """
        start_time = time.monotonic()
        fix_cycle = context.get("fix_cycle", 0)

        # Step 1: Read architecture and project spec
        await self.log("Reading architecture.md and project_spec.md...")
        architecture = await self._read_architecture()
        project_spec = await self._read_project_spec()

        if not architecture:
            elapsed = time.monotonic() - start_time
            return AgentResult(
                agent_name=self.agent_name,
                success=False,
                artifacts_produced=[],
                error="architecture.md not found or empty in workspace",
                duration_seconds=elapsed,
            )

        # Step 2: Read backend and frontend code
        await self.log("Reading backend and frontend code for analysis...")
        backend_code = await self._collect_code("backend/")
        frontend_code = await self._collect_code("frontend/")

        # Step 3: Run simulated tests via LLM analysis
        await self.log(
            f"Running test analysis (fix cycle {fix_cycle}/{MAX_FIX_CYCLES})..."
        )
        backend_results = await self._run_backend_tests(
            architecture, backend_code
        )
        frontend_results = await self._run_frontend_tests(
            architecture, frontend_code
        )
        ui_results = await self._run_ui_tests(
            architecture, project_spec, backend_code, frontend_code
        )

        # Step 4: Identify critical/major bugs
        all_bugs = (
            backend_results["bugs"]
            + frontend_results["bugs"]
            + ui_results["bugs"]
        )
        critical_major_bugs = [
            b for b in all_bugs if b["severity"] in ("critical", "major")
        ]

        # Step 5: Generate fix suggestions for critical/major bugs
        fix_suggestions: dict[str, str] = {}
        if critical_major_bugs:
            await self.log(
                f"Found {len(critical_major_bugs)} critical/major bugs. "
                f"Generating fix suggestions..."
            )
            fix_suggestions = await self._generate_fix_suggestions(
                critical_major_bugs
            )

        # Step 6: Determine if we should halt or succeed
        unresolved_bugs: list[dict] | None = None

        if critical_major_bugs and fix_cycle >= MAX_FIX_CYCLES:
            # Halt: max fix cycles reached with unresolved bugs
            unresolved_bugs = critical_major_bugs
            await self.log(
                f"HALTING: {len(critical_major_bugs)} critical/major bugs "
                f"remain unresolved after {MAX_FIX_CYCLES} fix cycles."
            )

        # Step 7: Generate testing_report.md
        report_content = generate_testing_report(
            backend_results=backend_results,
            frontend_results=frontend_results,
            ui_results=ui_results,
            fix_suggestions=fix_suggestions,
            fix_cycle=fix_cycle,
            unresolved_bugs=unresolved_bugs,
        )
        await self.write_artifact("testing_report.md", report_content)

        elapsed = time.monotonic() - start_time
        artifacts = ["testing_report.md"]

        # Step 8: Determine success/failure
        if unresolved_bugs:
            # Halted due to unresolved bugs after max cycles
            return AgentResult(
                agent_name=self.agent_name,
                success=False,
                artifacts_produced=artifacts,
                error=(
                    f"{len(unresolved_bugs)} critical/major bugs unresolved "
                    f"after {MAX_FIX_CYCLES} fix cycles. "
                    f"Bug IDs: {[b['id'] for b in unresolved_bugs]}"
                ),
                duration_seconds=elapsed,
            )

        if critical_major_bugs:
            # Bugs found but within fix cycle limit — route for fixing
            await self.log(
                f"Routing {len(critical_major_bugs)} bugs to responsible "
                f"agents for fixing. Fix cycle: {fix_cycle + 1}."
            )
            # Include routing info in the result for the orchestrator
            return AgentResult(
                agent_name=self.agent_name,
                success=False,
                artifacts_produced=artifacts,
                error=(
                    f"BUGS_FOUND: {len(critical_major_bugs)} critical/major "
                    f"bugs require fixing. Fix cycle: {fix_cycle + 1}/"
                    f"{MAX_FIX_CYCLES}. "
                    f"Routing to: {self._get_responsible_agents(critical_major_bugs)}"
                ),
                duration_seconds=elapsed,
            )

        # All tests pass — trigger approval gate 2
        await self.log(
            "All tests passed. No critical or major bugs found. "
            "Ready to trigger approval gate 2."
        )
        return AgentResult(
            agent_name=self.agent_name,
            success=True,
            artifacts_produced=artifacts,
            duration_seconds=elapsed,
        )

    async def _read_architecture(self) -> str:
        """Read architecture.md from workspace.

        Returns:
            Content of architecture.md, or empty string if not available.
        """
        try:
            if await self.workspace.file_exists("architecture.md"):
                return await self.workspace.read_file("architecture.md")
        except Exception as e:
            await self.log(f"Warning: Could not read architecture.md: {e}")
        return ""

    async def _read_project_spec(self) -> str:
        """Read project_spec.md from workspace.

        Returns:
            Content of project_spec.md, or empty string if not available.
        """
        try:
            if await self.workspace.file_exists("project_spec.md"):
                return await self.workspace.read_file("project_spec.md")
        except Exception as e:
            await self.log(f"Warning: Could not read project_spec.md: {e}")
        return ""

    async def _collect_code(self, directory: str) -> str:
        """Collect code file contents from a directory for LLM analysis.

        Reads available source files from the specified directory and
        concatenates them with filename headers for context.

        Args:
            directory: Relative directory path in the workspace.

        Returns:
            Concatenated source code with file headers, or a placeholder
            message if no code is found.
        """
        try:
            if not await self.workspace.file_exists(directory.rstrip("/")):
                return f"[No {directory} code found in workspace]"

            files = await self.workspace.list_files(directory)
            if not files:
                return f"[No files found in {directory}]"

            code_parts: list[str] = []
            total_chars = 0
            max_chars = 50000  # Limit total code context to avoid LLM overflow

            for filepath in sorted(files):
                if total_chars >= max_chars:
                    code_parts.append(
                        f"\n[... truncated, {len(files) - len(code_parts)} "
                        f"more files ...]"
                    )
                    break
                try:
                    content = await self.workspace.read_file(filepath)
                    code_parts.append(f"\n### {filepath}\n```\n{content}\n```")
                    total_chars += len(content)
                except Exception:
                    continue

            return "\n".join(code_parts) if code_parts else f"[Empty {directory}]"

        except Exception as e:
            await self.log(f"Warning: Could not collect code from {directory}: {e}")
            return f"[Error reading {directory}: {e}]"

    async def _run_backend_tests(
        self, architecture: str, backend_code: str
    ) -> dict:
        """Simulate running pytest on the backend code via LLM analysis.

        Args:
            architecture: Content of architecture.md.
            backend_code: Collected backend source code.

        Returns:
            Parsed test results dict.
        """
        prompt = BACKEND_TEST_PROMPT.format(
            architecture=architecture,
            backend_code=backend_code,
        )
        response = await self.llm_generate(
            prompt=prompt,
            system=QA_SYSTEM_PROMPT,
        )
        return parse_test_results(response)

    async def _run_frontend_tests(
        self, architecture: str, frontend_code: str
    ) -> dict:
        """Simulate running vitest on the frontend code via LLM analysis.

        Args:
            architecture: Content of architecture.md.
            frontend_code: Collected frontend source code.

        Returns:
            Parsed test results dict.
        """
        prompt = FRONTEND_TEST_PROMPT.format(
            architecture=architecture,
            frontend_code=frontend_code,
        )
        response = await self.llm_generate(
            prompt=prompt,
            system=QA_SYSTEM_PROMPT,
        )
        return parse_test_results(response)

    async def _run_ui_tests(
        self,
        architecture: str,
        project_spec: str,
        backend_code: str,
        frontend_code: str,
    ) -> dict:
        """Simulate running Playwright UI tests via LLM analysis.

        Args:
            architecture: Content of architecture.md.
            project_spec: Content of project_spec.md.
            backend_code: Collected backend source code.
            frontend_code: Collected frontend source code.

        Returns:
            Parsed test results dict.
        """
        prompt = UI_TEST_PROMPT.format(
            architecture=architecture,
            project_spec=project_spec,
            backend_code=backend_code,
            frontend_code=frontend_code,
        )
        response = await self.llm_generate(
            prompt=prompt,
            system=QA_SYSTEM_PROMPT,
        )
        return parse_test_results(response)

    async def _generate_fix_suggestions(
        self, bugs: list[dict]
    ) -> dict[str, str]:
        """Generate fix suggestions for critical/major bugs via LLM.

        Args:
            bugs: List of bug dicts with id, severity, description, agent.

        Returns:
            Dict mapping bug ID to fix suggestion string.
        """
        import re

        bugs_text = "\n".join(
            f"- {b['id']} ({b['severity']}): {b['description']} "
            f"[Agent: {b['agent']}]"
            for b in bugs
        )
        prompt = FIX_SUGGESTION_PROMPT.format(bugs=bugs_text)
        response = await self.llm_generate(
            prompt=prompt,
            system=QA_SYSTEM_PROMPT,
        )

        suggestions: dict[str, str] = {}
        pattern = re.compile(r"-\s*(BUG-\d+):\s*(.+?)$", re.MULTILINE)
        for match in pattern.finditer(response):
            bug_id = match.group(1)
            suggestion = match.group(2).strip()
            suggestions[bug_id] = suggestion

        return suggestions

    def _get_responsible_agents(self, bugs: list[dict]) -> list[str]:
        """Extract unique responsible agent names from bug list.

        Args:
            bugs: List of bug dicts containing 'agent' key.

        Returns:
            Sorted list of unique agent names responsible for bugs.
        """
        agents = set()
        for bug in bugs:
            agent = bug.get("agent", "")
            if agent:
                agents.add(agent)
        return sorted(agents)
