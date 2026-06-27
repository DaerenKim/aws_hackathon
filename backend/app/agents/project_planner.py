"""Project Planner Agent for Hackathon Studio.

Transforms raw hackathon inputs (brief, rubric, idea) into an
implementation-ready project specification (project_spec.md).
Constrains MVP scope to hackathon time/team/theme constraints.
"""

import logging
import time

from app.agents.base import BaseAgent
from app.models.artifacts import AgentResult

logger = logging.getLogger(__name__)

# Required input files in the workspace
REQUIRED_INPUTS = [
    "inputs/hackathon_brief.txt",
    "inputs/project_idea.txt",
]

# Optional inputs
OPTIONAL_INPUTS = [
    "inputs/judging_rubric.txt",
    "inputs/tech_stack.txt",
]

# Required sections in the generated project spec
REQUIRED_SECTIONS = [
    "## Refined Idea",
    "## Elevator Pitch",
    "## Target Users",
    "## MVP Scope",
    "## Stretch Goals",
    "## Timeline",
    "## Constraints Applied",
]

SYSTEM_PROMPT = (
    "You are a senior product manager. Given a hackathon brief and project idea, "
    "produce a concise, implementation-ready project specification. "
    "Focus on achievable MVP features that maximize judging scores."
)

MAX_RETRIES = 2


class ProjectPlannerAgent(BaseAgent):
    """Agent that generates a structured project specification from hackathon inputs.

    Reads the hackathon brief, judging rubric, and project idea from the
    shared workspace. Generates project_spec.md with required sections
    including refined idea, elevator pitch, target users, MVP scope,
    stretch goals, timeline, and constraints applied.

    Requirements: 2.1, 2.2, 2.3, 2.4, 2.5
    """

    async def execute(self, context: dict) -> AgentResult:
        """Execute project planning to produce project_spec.md.

        Args:
            context: Dictionary with optional overrides. Currently unused.

        Returns:
            AgentResult indicating success/failure with artifacts produced.
        """
        start_time = time.monotonic()

        # Step 1: Validate required inputs exist
        missing_inputs = []
        for input_path in REQUIRED_INPUTS:
            if not await self.workspace.file_exists(input_path):
                missing_inputs.append(input_path)

        if missing_inputs:
            error_msg = (
                f"Required input(s) missing from workspace: {missing_inputs}"
            )
            await self.log(error_msg)
            return AgentResult(
                agent_name=self.agent_name,
                success=False,
                artifacts_produced=[],
                error=error_msg,
                duration_seconds=time.monotonic() - start_time,
            )

        # Step 2: Read all inputs
        hackathon_brief = await self.workspace.read_file("inputs/hackathon_brief.txt")
        project_idea = await self.workspace.read_file("inputs/project_idea.txt")

        judging_rubric = ""
        if await self.workspace.file_exists("inputs/judging_rubric.txt"):
            judging_rubric = await self.workspace.read_file("inputs/judging_rubric.txt")

        tech_stack = ""
        if await self.workspace.file_exists("inputs/tech_stack.txt"):
            tech_stack = await self.workspace.read_file("inputs/tech_stack.txt")

        await self.log("All inputs loaded. Generating project specification...")

        # Step 3: Build the LLM prompt
        prompt = self._build_prompt(
            hackathon_brief=hackathon_brief,
            project_idea=project_idea,
            judging_rubric=judging_rubric,
            tech_stack=tech_stack,
        )

        # Step 4: Generate with retries for completeness
        project_spec = ""
        for attempt in range(1, MAX_RETRIES + 2):  # up to MAX_RETRIES + 1 attempts
            await self.log(f"LLM generation attempt {attempt}...")

            project_spec = await self.llm_generate(prompt, system=SYSTEM_PROMPT)

            missing_sections = self._find_missing_sections(project_spec)
            if not missing_sections:
                break

            if attempt <= MAX_RETRIES:
                await self.log(
                    f"Missing sections detected: {missing_sections}. Retrying..."
                )
                prompt = self._build_retry_prompt(
                    original_prompt=prompt,
                    previous_output=project_spec,
                    missing_sections=missing_sections,
                )
            else:
                # Final attempt still has missing sections — log warning but proceed
                await self.log(
                    f"WARNING: After {MAX_RETRIES + 1} attempts, still missing "
                    f"sections: {missing_sections}. Proceeding with available content."
                )

        # Step 5: If tech stack was not provided, ask LLM to recommend one
        if not tech_stack:
            await self.log("No tech stack provided. Requesting LLM recommendation...")
            tech_recommendation = await self._recommend_tech_stack(
                hackathon_brief=hackathon_brief,
                project_idea=project_idea,
                project_spec=project_spec,
            )
            # Append tech stack recommendation if not already in spec
            if "## Recommended Tech Stack" not in project_spec:
                project_spec += f"\n\n## Recommended Tech Stack\n\n{tech_recommendation}\n"

        # Step 6: Write project_spec.md to workspace
        await self.write_artifact("project_spec.md", project_spec)
        await self.log("project_spec.md written to workspace.")

        elapsed = time.monotonic() - start_time
        return AgentResult(
            agent_name=self.agent_name,
            success=True,
            artifacts_produced=["project_spec.md"],
            duration_seconds=elapsed,
        )

    def _build_prompt(
        self,
        hackathon_brief: str,
        project_idea: str,
        judging_rubric: str,
        tech_stack: str,
    ) -> str:
        """Build the LLM prompt for project specification generation.

        Args:
            hackathon_brief: Contents of the hackathon brief document.
            project_idea: The user's project idea text.
            judging_rubric: Contents of the judging rubric (may be empty).
            tech_stack: Preferred tech stack (may be empty).

        Returns:
            Formatted prompt string.
        """
        parts = [
            "Generate a complete project specification in Markdown format.",
            "",
            "The specification MUST contain ALL of the following sections with these exact headers:",
            "- ## Refined Idea",
            "- ## Elevator Pitch (max 3 sentences)",
            "- ## Target Users",
            "- ## MVP Scope",
            "- ## Stretch Goals",
            "- ## Timeline",
            "- ## Constraints Applied",
            "",
            "IMPORTANT RULES:",
            "- The Elevator Pitch section MUST be no more than 3 sentences.",
            "- The MVP Scope MUST be limited to features achievable within the "
            "hackathon time limit, team size, and theme constraints stated in the brief.",
            "- The Timeline MUST be broken into phases that fit within the hackathon duration.",
            "- The Constraints Applied section MUST explicitly state which hackathon "
            "constraints (time, team size, theme) were applied to scope the MVP.",
            "",
            "--- HACKATHON BRIEF ---",
            hackathon_brief,
            "",
        ]

        if judging_rubric:
            parts.extend([
                "--- JUDGING RUBRIC ---",
                judging_rubric,
                "",
            ])

        parts.extend([
            "--- PROJECT IDEA ---",
            project_idea,
            "",
        ])

        if tech_stack:
            parts.extend([
                "--- PREFERRED TECH STACK ---",
                tech_stack,
                "",
            ])

        parts.extend([
            "Generate the project specification now. "
            "Use the exact section headers listed above.",
        ])

        return "\n".join(parts)

    def _build_retry_prompt(
        self,
        original_prompt: str,
        previous_output: str,
        missing_sections: list[str],
    ) -> str:
        """Build a retry prompt that explicitly requests missing sections.

        Args:
            original_prompt: The original generation prompt.
            previous_output: The LLM's previous output.
            missing_sections: List of section headers that were not found.

        Returns:
            A more explicit prompt requesting the missing sections.
        """
        return (
            f"{original_prompt}\n\n"
            f"Your previous output was missing these required sections: "
            f"{missing_sections}\n\n"
            f"Previous output for reference:\n"
            f"{previous_output}\n\n"
            f"Please regenerate the COMPLETE specification with ALL required "
            f"sections. Every section header must appear exactly as listed above."
        )

    def _find_missing_sections(self, content: str) -> list[str]:
        """Check which required sections are missing from the output.

        Performs case-insensitive matching on section headers.

        Args:
            content: The generated markdown content.

        Returns:
            List of missing section header strings.
        """
        content_lower = content.lower()
        missing = []
        for section in REQUIRED_SECTIONS:
            # Check for the section header (case-insensitive)
            if section.lower() not in content_lower:
                missing.append(section)
        return missing

    async def _recommend_tech_stack(
        self,
        hackathon_brief: str,
        project_idea: str,
        project_spec: str,
    ) -> str:
        """Ask the LLM to recommend a tech stack when none was provided.

        Args:
            hackathon_brief: The hackathon brief content.
            project_idea: The user's project idea.
            project_spec: The generated project specification so far.

        Returns:
            Tech stack recommendation text.
        """
        prompt = (
            "Based on the following hackathon project specification, "
            "recommend a technology stack that would be most effective "
            "for building the MVP within the hackathon time constraints.\n\n"
            "Consider: rapid development speed, team familiarity (assume "
            "a general-purpose team), library ecosystem, and demo-ability.\n\n"
            f"--- PROJECT SPEC ---\n{project_spec}\n\n"
            "Provide a concise recommendation listing:\n"
            "- Frontend framework\n"
            "- Backend framework\n"
            "- Database\n"
            "- Key libraries/services\n"
            "- Justification (1-2 sentences per choice)"
        )

        system = (
            "You are a senior technical architect. Recommend practical, "
            "well-supported technologies optimized for hackathon speed."
        )

        return await self.llm_generate(prompt, system=system)
