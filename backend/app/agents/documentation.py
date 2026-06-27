"""Documentation Agent for Hackathon Studio.

Generates comprehensive project documentation sourced from workspace
artifacts: README.md, developer_guide.md, and api_docs.md.
Handles missing source artifacts gracefully by noting incomplete sections.

Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6
"""

import logging
import time

from app.agents.base import BaseAgent
from app.models.artifacts import AgentResult

logger = logging.getLogger(__name__)

# Minimum character count for each generated document
MIN_DOC_LENGTH = 200

# Source artifacts and their descriptions
SOURCE_ARTIFACTS = {
    "project_spec.md": "project specification (overview, MVP scope, target users)",
    "architecture.md": "architecture design (tech stack, API endpoints, folder structure)",
    "backend/requirements.txt": "Python backend dependencies",
    "frontend/package.json": "frontend Node.js dependencies and scripts",
}

# Output files this agent produces
OUTPUT_FILES = ["README.md", "developer_guide.md", "api_docs.md"]

SYSTEM_PROMPT = (
    "You are a technical writer specializing in developer documentation. "
    "Generate comprehensive, well-structured documentation in Markdown format. "
    "Use clear headings, code blocks where appropriate, and concise but "
    "informative descriptions. If certain source information is unavailable, "
    "clearly note which sections are incomplete and why."
)

MAX_RETRIES = 2


class DocumentationAgent(BaseAgent):
    """Agent that generates README, developer guide, and API documentation.

    Sources content from project_spec.md, architecture.md, and dependency
    files (requirements.txt, package.json). Gracefully handles missing
    artifacts by noting incomplete sections in the generated docs.

    Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6
    """

    async def execute(self, context: dict) -> AgentResult:
        """Execute documentation generation.

        Reads available source artifacts, generates three documentation
        files using the LLM, validates minimum length, and writes them
        to the workspace root.

        Args:
            context: Dictionary with optional overrides. Currently unused.

        Returns:
            AgentResult with artifacts_produced listing the generated docs.
        """
        start_time = time.monotonic()

        # Step 1: Read available source artifacts
        sources, missing_sources = await self._read_sources()

        if missing_sources:
            await self.log(
                f"Missing source artifacts: {list(missing_sources.keys())}. "
                f"Documentation will note incomplete sections."
            )

        await self.log(
            f"Loaded {len(sources)} source artifact(s). "
            f"Generating documentation..."
        )

        # Step 2: Generate README.md
        readme_content = await self._generate_readme(sources, missing_sources)
        if not self._validate_length(readme_content):
            await self.log("README.md below minimum length. Retrying with expanded prompt...")
            readme_content = await self._retry_generation(
                "README.md", readme_content, sources, missing_sources, "readme"
            )

        # Step 3: Generate developer_guide.md
        dev_guide_content = await self._generate_developer_guide(sources, missing_sources)
        if not self._validate_length(dev_guide_content):
            await self.log("developer_guide.md below minimum length. Retrying...")
            dev_guide_content = await self._retry_generation(
                "developer_guide.md", dev_guide_content, sources, missing_sources, "dev_guide"
            )

        # Step 4: Generate api_docs.md
        api_docs_content = await self._generate_api_docs(sources, missing_sources)
        if not self._validate_length(api_docs_content):
            await self.log("api_docs.md below minimum length. Retrying...")
            api_docs_content = await self._retry_generation(
                "api_docs.md", api_docs_content, sources, missing_sources, "api_docs"
            )

        # Step 5: Final validation — all docs must be ≥200 chars
        docs = {
            "README.md": readme_content,
            "developer_guide.md": dev_guide_content,
            "api_docs.md": api_docs_content,
        }

        for filename, content in docs.items():
            if not self._validate_length(content):
                error_msg = (
                    f"Generated {filename} has only {len(content)} characters, "
                    f"which is below the required minimum of {MIN_DOC_LENGTH}."
                )
                await self.log(error_msg)
                return AgentResult(
                    agent_name=self.agent_name,
                    success=False,
                    artifacts_produced=[],
                    error=error_msg,
                    duration_seconds=time.monotonic() - start_time,
                )

        # Step 6: Write all docs to workspace root
        artifacts_produced: list[str] = []
        for filename, content in docs.items():
            await self.write_artifact(filename, content)
            artifacts_produced.append(filename)
            await self.log(f"Written {filename} ({len(content)} chars)")

        elapsed = time.monotonic() - start_time
        await self.log(
            f"Documentation generation complete. "
            f"Produced {len(artifacts_produced)} files in {elapsed:.1f}s."
        )

        return AgentResult(
            agent_name=self.agent_name,
            success=True,
            artifacts_produced=artifacts_produced,
            duration_seconds=elapsed,
        )

    async def _read_sources(self) -> tuple[dict[str, str], dict[str, str]]:
        """Read available source artifacts from the workspace.

        Returns:
            A tuple of (loaded_sources, missing_sources) where each is a
            dict mapping artifact path to either content or description
            of what was expected.
        """
        sources: dict[str, str] = {}
        missing: dict[str, str] = {}

        for path, description in SOURCE_ARTIFACTS.items():
            try:
                if await self.workspace.file_exists(path):
                    content = await self.workspace.read_file(path)
                    if content.strip():
                        sources[path] = content
                    else:
                        missing[path] = f"{description} (file exists but is empty)"
                else:
                    missing[path] = f"{description} (file not found)"
            except Exception as e:
                missing[path] = f"{description} (read error: {e})"

        return sources, missing

    async def _generate_readme(
        self,
        sources: dict[str, str],
        missing: dict[str, str],
    ) -> str:
        """Generate README.md content via LLM.

        Args:
            sources: Available source artifact contents.
            missing: Missing artifacts with descriptions.

        Returns:
            Generated README markdown content.
        """
        prompt_parts = [
            "Generate a comprehensive README.md for a hackathon project.",
            "",
            "The README MUST include ALL of these sections:",
            "- # Project Name (derived from the project spec)",
            "- ## Overview (project description sourced from project_spec.md)",
            "- ## Setup Instructions (derived from requirements.txt and package.json)",
            "- ## Usage (primary user flow description)",
            "- ## Technology Stack (all frameworks and tools from architecture.md)",
            "",
        ]

        self._append_source_context(prompt_parts, sources, missing)

        prompt_parts.extend([
            "",
            "IMPORTANT:",
            "- The document MUST be at least 200 characters long.",
            "- If source information for a section is unavailable, include the "
            "section header and note: '[Section incomplete: source artifact not available]'",
            "- Use proper Markdown formatting with headers, lists, and code blocks.",
            "- For Setup Instructions, provide step-by-step commands for both "
            "backend (Python/pip) and frontend (Node.js/npm) if dependency info is available.",
        ])

        return await self.llm_generate("\n".join(prompt_parts), system=SYSTEM_PROMPT)

    async def _generate_developer_guide(
        self,
        sources: dict[str, str],
        missing: dict[str, str],
    ) -> str:
        """Generate developer_guide.md content via LLM.

        Args:
            sources: Available source artifact contents.
            missing: Missing artifacts with descriptions.

        Returns:
            Generated developer guide markdown content.
        """
        prompt_parts = [
            "Generate a comprehensive developer_guide.md for a hackathon project.",
            "",
            "The guide MUST include ALL of these sections:",
            "- # Developer Guide",
            "- ## Code Organization (folder structure and purpose of each directory)",
            "- ## Local Development Setup (step-by-step environment setup)",
            "- ## Contribution Guidelines (how to contribute, coding standards)",
            "- ## Architecture Overview (high-level component relationships)",
            "",
        ]

        self._append_source_context(prompt_parts, sources, missing)

        prompt_parts.extend([
            "",
            "IMPORTANT:",
            "- The document MUST be at least 200 characters long.",
            "- If source information for a section is unavailable, include the "
            "section header and note: '[Section incomplete: source artifact not available]'",
            "- Use proper Markdown formatting.",
            "- Include code blocks for any commands or configuration examples.",
            "- Base the code organization on architecture.md folder structure if available.",
        ])

        return await self.llm_generate("\n".join(prompt_parts), system=SYSTEM_PROMPT)

    async def _generate_api_docs(
        self,
        sources: dict[str, str],
        missing: dict[str, str],
    ) -> str:
        """Generate api_docs.md content via LLM.

        Args:
            sources: Available source artifact contents.
            missing: Missing artifacts with descriptions.

        Returns:
            Generated API documentation markdown content.
        """
        prompt_parts = [
            "Generate comprehensive api_docs.md for a hackathon project.",
            "",
            "The API documentation MUST include ALL of these sections:",
            "- # API Documentation",
            "- ## Overview (base URL, authentication if any)",
            "- ## Endpoints (each endpoint with HTTP method, path, "
            "request parameters, response schema)",
            "- ## Error Handling (common error codes and formats)",
            "- ## Examples (example request/response for key endpoints)",
            "",
        ]

        self._append_source_context(prompt_parts, sources, missing)

        prompt_parts.extend([
            "",
            "IMPORTANT:",
            "- The document MUST be at least 200 characters long.",
            "- If architecture.md is unavailable, note which endpoint sections "
            "are incomplete due to missing source.",
            "- List ALL endpoints defined in architecture.md if available.",
            "- For each endpoint, include: HTTP method, path, description, "
            "request parameters/body, and response schema.",
            "- Use code blocks for request/response examples.",
        ])

        return await self.llm_generate("\n".join(prompt_parts), system=SYSTEM_PROMPT)

    async def _retry_generation(
        self,
        filename: str,
        previous_content: str,
        sources: dict[str, str],
        missing: dict[str, str],
        doc_type: str,
    ) -> str:
        """Retry document generation with an explicit length requirement.

        Args:
            filename: Name of the document being generated.
            previous_content: The previously generated content that was too short.
            sources: Available source artifact contents.
            missing: Missing artifacts with descriptions.
            doc_type: Type identifier ("readme", "dev_guide", or "api_docs").

        Returns:
            Regenerated content (may still be below minimum if LLM cannot comply).
        """
        retry_prompt = (
            f"The following {filename} document is too short "
            f"(only {len(previous_content)} characters). "
            f"It must be at least {MIN_DOC_LENGTH} characters.\n\n"
            f"Previous content:\n{previous_content}\n\n"
            f"Please expand this document significantly. Add more detail, "
            f"examples, and explanations to each section. "
            f"The result MUST be at least {MIN_DOC_LENGTH} characters total.\n\n"
        )

        if missing:
            retry_prompt += (
                "Note: The following source artifacts were unavailable:\n"
            )
            for path, desc in missing.items():
                retry_prompt += f"- {path}: {desc}\n"
            retry_prompt += (
                "\nFor sections depending on missing artifacts, include a note "
                "explaining that the section is incomplete.\n"
            )

        return await self.llm_generate(retry_prompt, system=SYSTEM_PROMPT)

    def _append_source_context(
        self,
        prompt_parts: list[str],
        sources: dict[str, str],
        missing: dict[str, str],
    ) -> None:
        """Append available source context and missing artifact notes to prompt.

        Args:
            prompt_parts: List of prompt lines to extend.
            sources: Available source artifact contents.
            missing: Missing artifacts with descriptions.
        """
        if sources:
            prompt_parts.append("--- AVAILABLE SOURCE ARTIFACTS ---")
            for path, content in sources.items():
                # Truncate very long artifacts to avoid exceeding context window
                truncated = content[:8000] if len(content) > 8000 else content
                prompt_parts.extend([
                    f"\n### {path}:",
                    truncated,
                    "",
                ])

        if missing:
            prompt_parts.append("--- MISSING SOURCE ARTIFACTS ---")
            prompt_parts.append(
                "The following artifacts are NOT available. "
                "Note their absence in relevant documentation sections:"
            )
            for path, description in missing.items():
                prompt_parts.append(f"- {path}: {description}")

    @staticmethod
    def _validate_length(content: str) -> bool:
        """Check if content meets the minimum length requirement.

        Args:
            content: The generated document content.

        Returns:
            True if content has at least MIN_DOC_LENGTH characters.
        """
        return len(content) >= MIN_DOC_LENGTH
