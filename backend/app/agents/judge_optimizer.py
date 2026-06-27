"""Judge Optimizer Agent for Hackathon Studio.

Analyzes the judging rubric, scores the project plan against each criterion,
generates improvement suggestions for low-scoring criteria, and produces
a judge_analysis.md artifact with detailed scoring analysis.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
"""

import logging
import re
import time

from app.agents.base import BaseAgent
from app.models.artifacts import AgentResult

logger = logging.getLogger(__name__)

# System prompt for the judge optimizer LLM calls
JUDGE_OPTIMIZER_SYSTEM_PROMPT = (
    "You are a hackathon judge optimizer. Analyze the judging rubric, "
    "score the project against each criterion, and provide specific improvements. "
    "Be precise with scores (1-10 scale)."
)

# Prompt template for extracting criteria and scoring the project
SCORING_PROMPT_TEMPLATE = """Given the following judging rubric and project specification, perform these tasks:

1. Extract ALL scoring criteria from the judging rubric. For each criterion, identify:
   - The criterion name
   - The maximum possible score (if stated; otherwise assume 10)

2. Score the current project plan against each criterion on a scale of 1-10, where:
   - 1 = minimal alignment with the criterion
   - 10 = full alignment with the criterion

3. For each criterion scoring BELOW 8, provide a specific, actionable improvement suggestion that includes:
   - The target criterion name
   - The proposed change
   - The expected score improvement (e.g., "+2 points")

4. Identify any tradeoffs or risks in the current project plan.

## JUDGING RUBRIC:
{rubric}

## PROJECT SPECIFICATION:
{project_spec}

## REQUIRED OUTPUT FORMAT:
Respond in EXACTLY this format (do not deviate):

CRITERIA:
- [Criterion Name] | Max: [max_score] | Score: [current_score]/10
- [Criterion Name] | Max: [max_score] | Score: [current_score]/10
...

SUGGESTIONS:
- [Criterion Name]: [Proposed change]. Expected improvement: [+N points]
- [Criterion Name]: [Proposed change]. Expected improvement: [+N points]
...

TRADEOFFS:
- [Tradeoff or risk description]
- [Tradeoff or risk description]
...
"""


def parse_criteria(response: str) -> list[dict]:
    """Parse scoring criteria from the LLM response.

    Args:
        response: Raw LLM response text.

    Returns:
        List of dicts with keys: name, max_score, current_score.
        Returns empty list if no criteria could be parsed.
    """
    criteria: list[dict] = []

    # Find the CRITERIA section
    criteria_match = re.search(
        r"CRITERIA:\s*\n(.*?)(?=\n(?:SUGGESTIONS|TRADEOFFS):|$)",
        response,
        re.DOTALL | re.IGNORECASE,
    )
    if not criteria_match:
        return criteria

    criteria_text = criteria_match.group(1)

    # Parse each criterion line: "- [Name] | Max: [N] | Score: [N]/10"
    pattern = re.compile(
        r"-\s*(.+?)\s*\|\s*Max:\s*(\d+)\s*\|\s*Score:\s*(\d+)/10"
    )
    for match in pattern.finditer(criteria_text):
        name = match.group(1).strip()
        max_score = int(match.group(2))
        current_score = int(match.group(3))
        # Clamp scores to valid range
        current_score = max(1, min(10, current_score))
        max_score = max(1, max_score)
        criteria.append({
            "name": name,
            "max_score": max_score,
            "current_score": current_score,
        })

    return criteria


def parse_suggestions(response: str) -> list[dict]:
    """Parse improvement suggestions from the LLM response.

    Args:
        response: Raw LLM response text.

    Returns:
        List of dicts with keys: criterion, suggestion, expected_improvement.
    """
    suggestions: list[dict] = []

    suggestions_match = re.search(
        r"SUGGESTIONS:\s*\n(.*?)(?=\n(?:TRADEOFFS):|$)",
        response,
        re.DOTALL | re.IGNORECASE,
    )
    if not suggestions_match:
        return suggestions

    suggestions_text = suggestions_match.group(1)

    # Parse: "- [Criterion]: [Suggestion]. Expected improvement: [+N points]"
    pattern = re.compile(
        r"-\s*(.+?):\s*(.+?)\.?\s*Expected improvement:\s*(.+?)$",
        re.MULTILINE,
    )
    for match in pattern.finditer(suggestions_text):
        criterion = match.group(1).strip()
        suggestion = match.group(2).strip()
        improvement = match.group(3).strip()
        suggestions.append({
            "criterion": criterion,
            "suggestion": suggestion,
            "expected_improvement": improvement,
        })

    return suggestions


def parse_tradeoffs(response: str) -> list[str]:
    """Parse tradeoffs and risks from the LLM response.

    Args:
        response: Raw LLM response text.

    Returns:
        List of tradeoff/risk description strings.
    """
    tradeoffs: list[str] = []

    tradeoffs_match = re.search(
        r"TRADEOFFS:\s*\n(.*?)$",
        response,
        re.DOTALL | re.IGNORECASE,
    )
    if not tradeoffs_match:
        return tradeoffs

    tradeoffs_text = tradeoffs_match.group(1)

    for line in tradeoffs_text.strip().split("\n"):
        line = line.strip()
        if line.startswith("-"):
            tradeoffs.append(line[1:].strip())
        elif line:
            tradeoffs.append(line)

    return tradeoffs


def generate_judge_analysis_md(
    criteria: list[dict],
    suggestions: list[dict],
    tradeoffs: list[str],
) -> str:
    """Generate the judge_analysis.md content with proper markdown formatting.

    Sections:
    - Scoring Criteria (table format)
    - Improvement Suggestions (only for scores < 8)
    - Predicted Total Score (percentage of maximum)
    - Tradeoffs and Risks

    Args:
        criteria: Parsed criteria with scores.
        suggestions: Parsed improvement suggestions.
        tradeoffs: Parsed tradeoff descriptions.

    Returns:
        Formatted markdown string.
    """
    lines: list[str] = []
    lines.append("# Judge Analysis Report\n")

    # Scoring Criteria section
    lines.append("## Scoring Criteria\n")
    lines.append("| Criterion | Max Score | Current Score |")
    lines.append("|-----------|-----------|---------------|")
    for c in criteria:
        lines.append(f"| {c['name']} | {c['max_score']} | {c['current_score']}/10 |")
    lines.append("")

    # Improvement Suggestions section (only for scores < 8)
    lines.append("## Improvement Suggestions\n")
    low_score_criteria = [c for c in criteria if c["current_score"] < 8]
    if suggestions:
        for s in suggestions:
            lines.append(
                f"- **{s['criterion']}**: {s['suggestion']} "
                f"(Expected improvement: {s['expected_improvement']})"
            )
    elif low_score_criteria:
        # If parsing didn't capture suggestions but we have low-scoring criteria
        for c in low_score_criteria:
            lines.append(
                f"- **{c['name']}** (Score: {c['current_score']}/10): "
                f"Consider improvements to increase alignment with this criterion."
            )
    else:
        lines.append("All criteria scored 8 or above. No improvements needed.")
    lines.append("")

    # Predicted Total Score
    lines.append("## Predicted Total Score\n")
    if criteria:
        total_current = sum(c["current_score"] for c in criteria)
        total_max = sum(c["max_score"] for c in criteria)
        if total_max > 0:
            percentage = (total_current / total_max) * 100
        else:
            percentage = 0.0
        lines.append(f"- **Total Score**: {total_current}/{total_max}")
        lines.append(f"- **Percentage**: {percentage:.1f}%")
        lines.append(f"- **Criteria Count**: {len(criteria)}")
    else:
        lines.append("Unable to calculate predicted score.")
    lines.append("")

    # Tradeoffs and Risks
    lines.append("## Tradeoffs and Risks\n")
    if tradeoffs:
        for t in tradeoffs:
            lines.append(f"- {t}")
    else:
        lines.append("No significant tradeoffs or risks identified.")
    lines.append("")

    return "\n".join(lines)


class JudgeOptimizerAgent(BaseAgent):
    """Agent that analyzes judging rubric and optimizes project for scoring.

    Reads the judging rubric and project specification, extracts scoring
    criteria, scores the project against each criterion, and produces
    actionable improvement suggestions.

    Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
    """

    def __init__(self, ollama_client, workspace, state_manager):
        """Initialize the Judge Optimizer Agent.

        Args:
            ollama_client: Client for Ollama LLM interaction.
            workspace: Shared workspace service.
            state_manager: Project state manager.
        """
        super().__init__(
            agent_name="judge_optimizer",
            ollama_client=ollama_client,
            workspace=workspace,
            state_manager=state_manager,
        )

    async def execute(self, context: dict) -> AgentResult:
        """Execute judge optimization analysis.

        Steps:
        1. Read judging rubric from inputs/judging_rubric.txt
        2. Read project_spec.md from workspace (produced by project_planner)
        3. Score project against each rubric criterion via LLM
        4. Generate improvement suggestions for scores < 8
        5. Write judge_analysis.md to workspace

        Args:
            context: Execution context (currently unused for this agent).

        Returns:
            AgentResult with success status and artifacts produced.

        Raises:
            PermissionError: If project_spec.md is not yet available
                (project_planner not completed).
        """
        start_time = time.monotonic()

        # Step 1: Read judging rubric from workspace inputs
        await self.log("Reading judging rubric from workspace...")
        rubric_content = await self._read_rubric()
        if rubric_content is None:
            elapsed = time.monotonic() - start_time
            return AgentResult(
                agent_name=self.agent_name,
                success=False,
                artifacts_produced=[],
                error="Judging rubric is empty or not found at inputs/judging_rubric.txt",
                duration_seconds=elapsed,
            )

        # Step 2: Read project specification (requires project_planner completed)
        await self.log("Reading project specification...")
        project_spec = await self.read_artifact(
            "project_spec.md", "project_planner"
        )

        # Step 3: Generate scoring analysis via LLM
        await self.log("Generating scoring analysis via LLM...")
        prompt = SCORING_PROMPT_TEMPLATE.format(
            rubric=rubric_content,
            project_spec=project_spec,
        )
        response = await self.llm_generate(
            prompt=prompt,
            system=JUDGE_OPTIMIZER_SYSTEM_PROMPT,
        )

        # Step 4: Parse the LLM response
        await self.log("Parsing LLM scoring response...")
        criteria = parse_criteria(response)
        suggestions = parse_suggestions(response)
        tradeoffs = parse_tradeoffs(response)

        # Validate that we extracted at least one criterion
        if not criteria:
            elapsed = time.monotonic() - start_time
            return AgentResult(
                agent_name=self.agent_name,
                success=False,
                artifacts_produced=[],
                error=(
                    "Failed to parse scoring criteria from judging rubric. "
                    "The rubric may be unparseable or contain no extractable "
                    "scoring criteria."
                ),
                duration_seconds=elapsed,
            )

        # Filter suggestions to only include those for criteria scoring < 8
        suggestions = self._filter_suggestions_by_threshold(criteria, suggestions)

        # Step 5: Generate and write judge_analysis.md
        await self.log("Generating judge_analysis.md...")
        analysis_md = generate_judge_analysis_md(criteria, suggestions, tradeoffs)
        await self.write_artifact("judge_analysis.md", analysis_md)

        elapsed = time.monotonic() - start_time
        total_score = sum(c["current_score"] for c in criteria)
        total_max = sum(c["max_score"] for c in criteria)
        await self.log(
            f"Judge optimization complete. "
            f"Scored {len(criteria)} criteria. "
            f"Predicted score: {total_score}/{total_max} "
            f"({(total_score/total_max*100):.1f}% of maximum)."
        )

        return AgentResult(
            agent_name=self.agent_name,
            success=True,
            artifacts_produced=["judge_analysis.md"],
            duration_seconds=elapsed,
        )

    async def _read_rubric(self) -> str | None:
        """Read the judging rubric from the workspace inputs directory.

        Returns:
            Rubric text content, or None if empty/missing.
        """
        rubric_path = "inputs/judging_rubric.txt"

        if not await self.workspace.file_exists(rubric_path):
            return None

        content = await self.workspace.read_file(rubric_path)
        if not content or not content.strip():
            return None

        return content.strip()

    def _filter_suggestions_by_threshold(
        self,
        criteria: list[dict],
        suggestions: list[dict],
    ) -> list[dict]:
        """Filter suggestions to only include those for criteria scoring below 8.

        Ensures Property 5: suggestions generated for exactly those criteria
        with score < 8, zero suggestions for score >= 8.

        Args:
            criteria: Parsed criteria list with scores.
            suggestions: Raw parsed suggestions from LLM.

        Returns:
            Filtered suggestions list.
        """
        low_score_names = {
            c["name"].lower() for c in criteria if c["current_score"] < 8
        }

        if not low_score_names:
            return []

        filtered = [
            s for s in suggestions
            if s["criterion"].lower() in low_score_names
        ]

        # If LLM didn't provide suggestions matching our criteria names,
        # generate placeholder suggestions for low-scoring criteria
        if not filtered and low_score_names:
            for c in criteria:
                if c["current_score"] < 8:
                    filtered.append({
                        "criterion": c["name"],
                        "suggestion": (
                            "Improve alignment with this criterion to "
                            "increase score"
                        ),
                        "expected_improvement": f"+{8 - c['current_score']} points",
                    })

        return filtered
