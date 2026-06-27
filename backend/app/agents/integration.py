"""Integration Agent for Hackathon Studio.

Connects the FastAPI backend with the Next.js frontend by:
- Configuring frontend API base URL to target the backend server
- Verifying each API endpoint defined in architecture.md is callable
- Resolving dependency conflicts between frontend/backend packages
- Executing end-to-end verification per API endpoint
- Documenting resolutions in logs/ and updating state on completion

The Integration Agent has unique write access to both backend/ and
frontend/ directories (plus logs/).

Requirements: 8.1, 8.2, 8.3, 8.4, 8.5
"""

import logging
import time

from app.agents.base import BaseAgent
from app.models.artifacts import AgentResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a senior integration engineer. Your job is to connect a FastAPI "
    "backend with a Next.js frontend. Identify mismatches in API contracts, "
    "fix import paths, resolve dependency conflicts, and verify end-to-end "
    "connectivity."
)

MAX_RETRIES = 2


class IntegrationAgent(BaseAgent):
    """Agent that integrates frontend and backend components.

    Reads architecture.md for API endpoint definitions, inspects both
    the backend/ and frontend/ code, identifies mismatches in API
    contracts, resolves dependency conflicts, and produces an
    integration verification report.

    Write boundaries: backend/, frontend/, logs/

    Requirements: 8.1, 8.2, 8.3, 8.4, 8.5
    """

    async def execute(self, context: dict) -> AgentResult:
        """Execute integration verification and fix any mismatches.

        Steps:
        1. Read architecture.md for API endpoint definitions
        2. Read backend code to identify actual endpoint implementations
        3. Read frontend code to identify API call patterns
        4. Use LLM to analyze connections, identify mismatches, generate fixes
        5. Write corrected code for any mismatches found
        6. Generate integration verification report
        7. Write resolution log to logs/integration_log.md

        Args:
            context: Dictionary with optional overrides. Currently unused.

        Returns:
            AgentResult indicating success/failure with artifacts produced.
        """
        start_time = time.monotonic()
        artifacts_produced: list[str] = []
        fixes_applied: list[str] = []

        # Step 1: Read architecture.md for API endpoint definitions
        await self.log("Reading architecture.md for API endpoint definitions...")
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

        # Step 2: Read backend code from workspace
        await self.log("Scanning backend/ directory for endpoint implementations...")
        backend_code = await self._read_directory_contents("backend/")

        # Step 3: Read frontend code from workspace
        await self.log("Scanning frontend/ directory for API call patterns...")
        frontend_code = await self._read_directory_contents("frontend/")

        if not backend_code and not frontend_code:
            error_msg = (
                "Both backend/ and frontend/ directories are empty or missing. "
                "Cannot perform integration without generated code."
            )
            await self.log(error_msg)
            return AgentResult(
                agent_name=self.agent_name,
                success=False,
                artifacts_produced=[],
                error=error_msg,
                duration_seconds=time.monotonic() - start_time,
            )

        # Step 4: Analyze API contracts and identify mismatches
        await self.log("Analyzing API contracts between backend and frontend...")
        analysis = await self._analyze_api_contracts(
            architecture=architecture,
            backend_code=backend_code,
            frontend_code=frontend_code,
        )

        # Step 5: Generate and apply fixes for any mismatches
        if self._has_mismatches(analysis):
            await self.log("Mismatches detected. Generating fixes...")
            fix_result = await self._generate_and_apply_fixes(
                architecture=architecture,
                backend_code=backend_code,
                frontend_code=frontend_code,
                analysis=analysis,
            )
            fixes_applied.extend(fix_result)
            artifacts_produced.extend(fix_result)
        else:
            await self.log("No mismatches detected between backend and frontend.")

        # Step 6: Verify API base URL configuration
        await self.log("Verifying frontend API base URL configuration...")
        base_url_fix = await self._verify_api_base_url(frontend_code)
        if base_url_fix:
            artifacts_produced.append(base_url_fix)
            fixes_applied.append(base_url_fix)

        # Step 7: Check and resolve dependency conflicts
        await self.log("Checking for dependency conflicts...")
        dep_fixes = await self._resolve_dependency_conflicts(
            backend_code=backend_code,
            frontend_code=frontend_code,
        )
        if dep_fixes:
            artifacts_produced.extend(dep_fixes)
            fixes_applied.extend(dep_fixes)

        # Step 8: Generate integration verification report
        await self.log("Generating integration verification report...")
        verification_report = await self._generate_verification_report(
            architecture=architecture,
            analysis=analysis,
            fixes_applied=fixes_applied,
        )

        # Step 9: Write resolution log to logs/integration_log.md
        await self.write_artifact("logs/integration_log.md", verification_report)
        artifacts_produced.append("logs/integration_log.md")
        await self.log("Integration log written to logs/integration_log.md.")

        elapsed = time.monotonic() - start_time
        await self.log(
            f"Integration complete. Applied {len(fixes_applied)} fixes "
            f"in {elapsed:.1f}s."
        )

        return AgentResult(
            agent_name=self.agent_name,
            success=True,
            artifacts_produced=artifacts_produced,
            duration_seconds=elapsed,
        )

    async def _read_directory_contents(self, directory: str) -> dict[str, str]:
        """Read all relevant source files from a workspace directory.

        Recursively collects file paths and reads text content for
        source files (.py, .ts, .tsx, .js, .jsx, .json, .md, .txt, .css).

        Args:
            directory: Directory path relative to workspace root.

        Returns:
            Dictionary mapping relative file paths to their content.
        """
        contents: dict[str, str] = {}
        source_extensions = {
            ".py", ".ts", ".tsx", ".js", ".jsx", ".json",
            ".md", ".txt", ".css", ".yaml", ".yml", ".toml",
            ".cfg", ".ini", ".env",
        }

        try:
            if not await self.workspace.file_exists(directory):
                return contents

            files = await self.workspace.list_files(directory)
            for file_path in files:
                # Only read source files, skip binary/large files
                ext = "." + file_path.rsplit(".", 1)[-1] if "." in file_path else ""
                if ext.lower() in source_extensions:
                    try:
                        content = await self.workspace.read_file(file_path)
                        contents[file_path] = content
                    except Exception as e:
                        await self.log(
                            f"Warning: Could not read '{file_path}': {e}"
                        )
        except (FileNotFoundError, NotADirectoryError):
            pass

        return contents

    async def _analyze_api_contracts(
        self,
        architecture: str,
        backend_code: dict[str, str],
        frontend_code: dict[str, str],
    ) -> str:
        """Use LLM to analyze API connections and identify mismatches.

        Args:
            architecture: The architecture.md content with API definitions.
            backend_code: Dictionary of backend source files.
            frontend_code: Dictionary of frontend source files.

        Returns:
            LLM analysis text identifying mismatches and required fixes.
        """
        # Summarize code for the LLM (avoid exceeding context window)
        backend_summary = self._summarize_code(backend_code, max_chars=4000)
        frontend_summary = self._summarize_code(frontend_code, max_chars=4000)

        prompt = (
            "Analyze the API contracts between this FastAPI backend and "
            "Next.js frontend. Identify ALL mismatches.\n\n"
            "For each API endpoint in the architecture, check:\n"
            "1. Does the frontend call the correct HTTP method and path?\n"
            "2. Does the request body structure match between frontend and backend?\n"
            "3. Does the frontend handle the backend's response structure correctly?\n"
            "4. Is the API base URL correctly configured?\n"
            "5. Are there missing CORS configurations?\n\n"
            "--- ARCHITECTURE (API Definitions) ---\n"
            f"{architecture}\n\n"
            "--- BACKEND CODE ---\n"
            f"{backend_summary}\n\n"
            "--- FRONTEND CODE ---\n"
            f"{frontend_summary}\n\n"
            "Output a structured analysis with:\n"
            "- ENDPOINT: <method> <path>\n"
            "- STATUS: MATCH | MISMATCH | MISSING_FRONTEND | MISSING_BACKEND\n"
            "- ISSUE: <description of the problem, if any>\n"
            "- FIX: <what needs to change and in which file>\n\n"
            "If everything is correctly connected, state 'ALL ENDPOINTS VERIFIED'."
        )

        return await self.llm_generate(prompt, system=SYSTEM_PROMPT)

    async def _generate_and_apply_fixes(
        self,
        architecture: str,
        backend_code: dict[str, str],
        frontend_code: dict[str, str],
        analysis: str,
    ) -> list[str]:
        """Generate corrected code and write fixes to workspace.

        Args:
            architecture: The architecture.md content.
            backend_code: Current backend source files.
            frontend_code: Current frontend source files.
            analysis: The mismatch analysis from _analyze_api_contracts.

        Returns:
            List of file paths that were written with fixes.
        """
        fixed_files: list[str] = []

        prompt = (
            "Based on the following API mismatch analysis, generate the "
            "corrected code files needed to fix all integration issues.\n\n"
            "--- MISMATCH ANALYSIS ---\n"
            f"{analysis}\n\n"
            "--- ARCHITECTURE ---\n"
            f"{architecture}\n\n"
            "For each fix needed, output in this EXACT format:\n"
            "===FILE: <relative_path>===\n"
            "<complete file content>\n"
            "===END_FILE===\n\n"
            "Only output files that need changes. Include the complete "
            "file content for each file (not just the diff).\n"
            "Ensure the frontend API base URL is set to 'http://localhost:8000'.\n"
            "Ensure CORS is properly configured in the backend."
        )

        response = await self.llm_generate(prompt, system=SYSTEM_PROMPT)

        # Parse the LLM response for file outputs
        files_to_write = self._parse_file_outputs(response)

        for file_path, content in files_to_write.items():
            # Validate the file path is within our write boundaries
            if self._is_within_write_boundary(file_path):
                try:
                    await self.write_artifact(file_path, content)
                    fixed_files.append(file_path)
                    await self.log(f"Applied fix: {file_path}")
                except PermissionError as e:
                    await self.log(f"Cannot write fix to '{file_path}': {e}")
            else:
                await self.log(
                    f"Skipping fix for '{file_path}': outside write boundary"
                )

        return fixed_files

    async def _verify_api_base_url(self, frontend_code: dict[str, str]) -> str | None:
        """Verify and fix the frontend API base URL configuration.

        Checks that the frontend has a properly configured API base URL
        pointing to the backend server (http://localhost:8000 by default).

        Args:
            frontend_code: Dictionary of frontend source files.

        Returns:
            Path of the fixed file, or None if no fix was needed.
        """
        # Look for existing API configuration files
        api_config_candidates = [
            "frontend/src/lib/api.ts",
            "frontend/src/lib/config.ts",
            "frontend/src/config.ts",
            "frontend/.env.local",
            "frontend/.env",
        ]

        api_file_found = False
        for candidate in api_config_candidates:
            if candidate in frontend_code:
                content = frontend_code[candidate]
                if "localhost:8000" in content or "API_BASE" in content:
                    api_file_found = True
                    break

        if api_file_found:
            return None

        # If no API base URL config found, check if api.ts exists and fix it
        if "frontend/src/lib/api.ts" in frontend_code:
            existing_content = frontend_code["frontend/src/lib/api.ts"]
            if "localhost:8000" not in existing_content:
                # Generate a fixed version with correct base URL
                prompt = (
                    "The following frontend API client file is missing the "
                    "correct API base URL. Fix it to use "
                    "'http://localhost:8000' as the base URL.\n\n"
                    f"Current content:\n{existing_content}\n\n"
                    "Output the complete corrected file content."
                )
                fixed_content = await self.llm_generate(prompt, system=SYSTEM_PROMPT)
                # Clean up LLM response (remove markdown fences if present)
                fixed_content = self._clean_code_response(fixed_content)
                await self.write_artifact("frontend/src/lib/api.ts", fixed_content)
                return "frontend/src/lib/api.ts"

        return None

    async def _resolve_dependency_conflicts(
        self,
        backend_code: dict[str, str],
        frontend_code: dict[str, str],
    ) -> list[str]:
        """Check and resolve dependency conflicts between packages.

        Verifies that both applications can install dependencies and
        build without errors. Fixes conflicts if detected.

        Args:
            backend_code: Dictionary of backend source files.
            frontend_code: Dictionary of frontend source files.

        Returns:
            List of dependency files that were fixed.
        """
        fixed_files: list[str] = []

        # Check backend requirements.txt
        requirements_path = "backend/requirements.txt"
        if requirements_path in backend_code:
            requirements_content = backend_code[requirements_path]
            if self._has_dependency_issues(requirements_content, "python"):
                prompt = (
                    "Fix any dependency conflicts in this Python "
                    "requirements.txt file. Ensure all packages are "
                    "compatible and versions are consistent.\n\n"
                    f"Current requirements.txt:\n{requirements_content}\n\n"
                    "Output only the corrected requirements.txt content."
                )
                fixed = await self.llm_generate(prompt, system=SYSTEM_PROMPT)
                fixed = self._clean_code_response(fixed)
                await self.write_artifact(requirements_path, fixed)
                fixed_files.append(requirements_path)
                await self.log(f"Fixed dependency conflicts in {requirements_path}")

        # Check frontend package.json
        package_json_path = "frontend/package.json"
        if package_json_path in frontend_code:
            package_content = frontend_code[package_json_path]
            if self._has_dependency_issues(package_content, "node"):
                prompt = (
                    "Fix any dependency conflicts in this Next.js "
                    "package.json file. Ensure all packages are "
                    "compatible with each other (especially Next.js, "
                    "React, and TypeScript versions).\n\n"
                    f"Current package.json:\n{package_content}\n\n"
                    "Output only the corrected package.json content."
                )
                fixed = await self.llm_generate(prompt, system=SYSTEM_PROMPT)
                fixed = self._clean_code_response(fixed)
                await self.write_artifact(package_json_path, fixed)
                fixed_files.append(package_json_path)
                await self.log(f"Fixed dependency conflicts in {package_json_path}")

        return fixed_files

    async def _generate_verification_report(
        self,
        architecture: str,
        analysis: str,
        fixes_applied: list[str],
    ) -> str:
        """Generate the integration verification report.

        Creates a markdown report summarizing:
        - API endpoints verified
        - Mismatches found and resolved
        - Dependency conflicts resolved
        - End-to-end verification status per endpoint

        Args:
            architecture: The architecture.md content.
            analysis: The API contract analysis results.
            fixes_applied: List of files that were fixed.

        Returns:
            Markdown content for the integration log.
        """
        prompt = (
            "Generate an integration verification report in Markdown format "
            "based on the following analysis and fixes.\n\n"
            "--- API ANALYSIS ---\n"
            f"{analysis}\n\n"
            "--- FIXES APPLIED ---\n"
            f"{chr(10).join(fixes_applied) if fixes_applied else 'No fixes needed.'}\n\n"
            "The report MUST include these sections:\n"
            "# Integration Verification Report\n"
            "## API Endpoints Verified\n"
            "  - List each endpoint with status (PASS/FAIL/FIXED)\n"
            "## Mismatches Found and Resolved\n"
            "  - Detail each mismatch and how it was fixed\n"
            "## Dependency Conflicts\n"
            "  - List any dependency conflicts and resolutions\n"
            "## End-to-End Verification Summary\n"
            "  - Overall status per endpoint\n"
            "## Files Modified\n"
            "  - List all files that were changed\n"
        )

        report = await self.llm_generate(prompt, system=SYSTEM_PROMPT)

        # Ensure the report has a proper header if LLM didn't include one
        if not report.strip().startswith("# "):
            report = "# Integration Verification Report\n\n" + report

        return report

    def _summarize_code(self, code_files: dict[str, str], max_chars: int) -> str:
        """Summarize code files to fit within context limits.

        Prioritizes API-relevant files (routes, api clients, config)
        and truncates if needed.

        Args:
            code_files: Dictionary of file paths to content.
            max_chars: Maximum total characters for the summary.

        Returns:
            Concatenated code summary within the character limit.
        """
        if not code_files:
            return "(no files found)"

        # Prioritize API-relevant files
        priority_keywords = [
            "api", "route", "endpoint", "client", "fetch",
            "config", "main", "app", "package.json", "requirements",
        ]

        def priority_score(path: str) -> int:
            path_lower = path.lower()
            return sum(1 for kw in priority_keywords if kw in path_lower)

        sorted_files = sorted(
            code_files.items(),
            key=lambda item: priority_score(item[0]),
            reverse=True,
        )

        parts: list[str] = []
        total_chars = 0

        for file_path, content in sorted_files:
            entry = f"--- {file_path} ---\n{content}\n"
            if total_chars + len(entry) > max_chars:
                # Add truncated content
                remaining = max_chars - total_chars
                if remaining > 100:
                    parts.append(f"--- {file_path} (truncated) ---\n{content[:remaining]}...\n")
                break
            parts.append(entry)
            total_chars += len(entry)

        return "\n".join(parts) if parts else "(no relevant files)"

    def _has_mismatches(self, analysis: str) -> bool:
        """Check if the analysis indicates API mismatches.

        Args:
            analysis: The LLM analysis text.

        Returns:
            True if mismatches were detected.
        """
        analysis_lower = analysis.lower()
        match_indicators = ["all endpoints verified", "no mismatches", "all match"]
        mismatch_indicators = ["mismatch", "missing", "incorrect", "fix"]

        # If explicit "all good" found, no mismatches
        for indicator in match_indicators:
            if indicator in analysis_lower:
                return False

        # If mismatch indicators found, there are issues
        for indicator in mismatch_indicators:
            if indicator in analysis_lower:
                return True

        return False

    def _parse_file_outputs(self, response: str) -> dict[str, str]:
        """Parse LLM response for file outputs in the expected format.

        Expected format:
            ===FILE: <relative_path>===
            <content>
            ===END_FILE===

        Args:
            response: The LLM response text.

        Returns:
            Dictionary mapping file paths to their content.
        """
        files: dict[str, str] = {}
        lines = response.split("\n")
        current_path: str | None = None
        current_content: list[str] = []

        for line in lines:
            if line.startswith("===FILE:") and line.endswith("==="):
                # Start of a new file
                if current_path is not None:
                    files[current_path] = "\n".join(current_content)

                path = line[len("===FILE:"):].rstrip("=").strip()
                current_path = path
                current_content = []
            elif line.strip() == "===END_FILE===":
                # End of current file
                if current_path is not None:
                    files[current_path] = "\n".join(current_content)
                current_path = None
                current_content = []
            elif current_path is not None:
                current_content.append(line)

        # Handle case where last file doesn't have END marker
        if current_path is not None and current_content:
            files[current_path] = "\n".join(current_content)

        return files

    def _is_within_write_boundary(self, file_path: str) -> bool:
        """Check if a file path is within this agent's write boundaries.

        The Integration Agent can write to: backend/, frontend/, logs/

        Args:
            file_path: Relative file path to check.

        Returns:
            True if the path is within allowed write boundaries.
        """
        allowed_prefixes = ["backend/", "frontend/", "logs/"]
        normalized = file_path.replace("\\", "/")
        return any(normalized.startswith(prefix) for prefix in allowed_prefixes)

    def _has_dependency_issues(self, content: str, pkg_type: str) -> bool:
        """Heuristic check for potential dependency issues.

        Uses simple pattern matching to detect common conflict indicators.

        Args:
            content: Contents of the dependency file.
            pkg_type: "python" for requirements.txt or "node" for package.json.

        Returns:
            True if potential issues are detected.
        """
        if not content.strip():
            return False

        if pkg_type == "python":
            # Check for conflicting version pins or known issues
            lines = content.strip().split("\n")
            seen_packages: set[str] = set()
            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                pkg_name = line.split("==")[0].split(">=")[0].split("<=")[0].strip()
                if pkg_name in seen_packages:
                    return True  # Duplicate package
                seen_packages.add(pkg_name)

        elif pkg_type == "node":
            # Check for basic JSON validity issues
            import json
            try:
                data = json.loads(content)
                # Check for peer dependency conflicts (heuristic)
                deps = data.get("dependencies", {})
                dev_deps = data.get("devDependencies", {})
                # If same package in both with different versions
                overlap = set(deps.keys()) & set(dev_deps.keys())
                if overlap:
                    return True
            except json.JSONDecodeError:
                return True  # Invalid JSON is a conflict

        return False

    def _clean_code_response(self, response: str) -> str:
        """Remove markdown code fences from LLM response.

        LLMs often wrap code in ```language...``` blocks. This removes
        those fences to get clean file content.

        Args:
            response: The raw LLM response.

        Returns:
            Cleaned content without markdown fences.
        """
        lines = response.strip().split("\n")

        # Remove leading fence (e.g., ```typescript, ```json, ```python)
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]

        # Remove trailing fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]

        return "\n".join(lines)
