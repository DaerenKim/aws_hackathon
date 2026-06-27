"""Demo Video Agent for Hackathon Studio.

Records an automated demo of the running application using Playwright,
generates voiceover narration synchronized with screen recording,
burns captions into video, and encodes with FFmpeg (MP4, ≥1280x720).

Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7
"""

import asyncio
import logging
import shutil
import tempfile
import time
from pathlib import Path

from app.agents.base import BaseAgent
from app.models.artifacts import AgentResult

logger = logging.getLogger(__name__)

# System prompt for the Demo Video Agent's LLM calls
DEMO_VIDEO_SYSTEM_PROMPT = (
    "You are a demo video producer. Generate engaging demo scripts "
    "that showcase the application's key features clearly and concisely. "
    "Focus on user paths that demonstrate value to hackathon judges."
)

# Duration constraints (seconds)
MIN_DURATION_SECONDS = 60
MAX_DURATION_SECONDS = 300

# Minimum video resolution
MIN_WIDTH = 1280
MIN_HEIGHT = 720

# Prompt for generating a demo script from architecture
DEMO_SCRIPT_PROMPT = """Based on the following architecture document, generate a demo script
for a hackathon demo video. The video should be 60-300 seconds long.

## Architecture:
{architecture}

## Instructions:
Generate a JSON array of demo steps. Each step should have:
- "action": what the user does (e.g., "navigate to /dashboard", "click Submit button")
- "url": the URL to visit (if navigating)
- "duration_seconds": how long to stay on this step (5-30 seconds)
- "narration": what to say during this step (1-2 sentences)

Keep total duration between 60 and 300 seconds.
Cover each critical user path defined in the architecture.
Focus on the most impressive features first.

Respond with ONLY a valid JSON array, no other text.
"""

# Prompt for generating voiceover narration
VOICEOVER_PROMPT = """Generate a professional voiceover script for a hackathon demo video.
The demo walks through the following steps:

{demo_steps}

For each step, write a voiceover narration line (1-2 sentences) that:
- Describes what the user is seeing
- Highlights the value of the feature
- Maintains an engaging, professional tone

## Response Format:
For each step, output:
STEP [number]: [narration text]
TIMESTAMP: [start_time]-[end_time] (in seconds)

Total duration should be between 60 and 300 seconds.
"""

# Prompt for generating SRT captions
CAPTIONS_PROMPT = """Convert the following voiceover script into SRT subtitle format.

{voiceover_script}

## Rules:
- Each subtitle should be 1-2 lines, max 42 characters per line
- Duration per subtitle: 2-5 seconds
- Use standard SRT format with sequential numbering
- Timestamps in HH:MM:SS,mmm format

Respond with ONLY valid SRT content.
"""


def _check_ffmpeg_available() -> bool:
    """Check if FFmpeg is available on the system PATH.

    Returns:
        True if ffmpeg executable is found, False otherwise.
    """
    return shutil.which("ffmpeg") is not None


def _check_playwright_available() -> bool:
    """Check if Playwright is importable.

    Returns:
        True if playwright can be imported, False otherwise.
    """
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def generate_srt_from_steps(steps: list[dict]) -> str:
    """Generate SRT subtitle content from demo steps.

    Creates properly formatted SRT captions from the narration
    in each demo step, distributing time based on step durations.

    Args:
        steps: List of demo step dicts with 'narration' and
               'duration_seconds' keys.

    Returns:
        Formatted SRT subtitle string.
    """
    srt_lines: list[str] = []
    current_time = 0.0

    for i, step in enumerate(steps, start=1):
        narration = step.get("narration", "")
        duration = step.get("duration_seconds", 10)

        if not narration:
            current_time += duration
            continue

        start_time = current_time
        end_time = current_time + duration

        srt_lines.append(str(i))
        srt_lines.append(
            f"{_format_srt_time(start_time)} --> {_format_srt_time(end_time)}"
        )
        # Split narration into lines of max 42 chars
        wrapped = _wrap_text(narration, max_chars=42)
        srt_lines.append(wrapped)
        srt_lines.append("")  # Blank line between entries

        current_time = end_time

    return "\n".join(srt_lines)


def _format_srt_time(seconds: float) -> str:
    """Format seconds into SRT timestamp format HH:MM:SS,mmm.

    Args:
        seconds: Time in seconds.

    Returns:
        Formatted timestamp string.
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _wrap_text(text: str, max_chars: int = 42) -> str:
    """Wrap text to a maximum character width per line.

    Args:
        text: Text to wrap.
        max_chars: Maximum characters per line.

    Returns:
        Wrapped text with newlines.
    """
    words = text.split()
    lines: list[str] = []
    current_line = ""

    for word in words:
        if current_line and len(current_line) + 1 + len(word) > max_chars:
            lines.append(current_line)
            current_line = word
        else:
            current_line = f"{current_line} {word}".strip()

    if current_line:
        lines.append(current_line)

    return "\n".join(lines)


def generate_demo_script_md(steps: list[dict]) -> str:
    """Generate a markdown demo script document from steps.

    Args:
        steps: List of demo step dicts with action, url,
               duration_seconds, and narration keys.

    Returns:
        Formatted markdown string for video/script.md.
    """
    lines: list[str] = []
    lines.append("# Demo Video Script\n")
    lines.append("## Overview\n")

    total_duration = sum(s.get("duration_seconds", 10) for s in steps)
    lines.append(f"- **Total Duration**: {total_duration} seconds")
    lines.append(f"- **Number of Steps**: {len(steps)}")
    lines.append(f"- **Resolution**: {MIN_WIDTH}x{MIN_HEIGHT}")
    lines.append("")
    lines.append("## Steps\n")

    current_time = 0.0
    for i, step in enumerate(steps, start=1):
        duration = step.get("duration_seconds", 10)
        action = step.get("action", "No action specified")
        url = step.get("url", "")
        narration = step.get("narration", "")

        lines.append(f"### Step {i} ({current_time:.0f}s - {current_time + duration:.0f}s)")
        lines.append(f"- **Action**: {action}")
        if url:
            lines.append(f"- **URL**: {url}")
        lines.append(f"- **Duration**: {duration}s")
        if narration:
            lines.append(f"- **Narration**: \"{narration}\"")
        lines.append("")

        current_time += duration

    return "\n".join(lines)


class DemoVideoAgent(BaseAgent):
    """Agent that produces a demo video of the running application.

    Records an automated browser session using Playwright, generates
    voiceover narration via LLM, burns captions into the video, and
    encodes the final output using FFmpeg in MP4 format (≥1280x720).

    Handles failures gracefully:
    - If Playwright is not available: returns failure with descriptive error
    - If FFmpeg is not available: returns failure with descriptive error
    - If the application fails to start: logs failure and returns error

    Write boundaries: video/
    Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7
    """

    def __init__(self, ollama_client, workspace, state_manager):
        """Initialize the Demo Video Agent.

        Args:
            ollama_client: Client for Ollama LLM interaction.
            workspace: Shared workspace service.
            state_manager: Project state manager.
        """
        super().__init__(
            agent_name="demo_video",
            ollama_client=ollama_client,
            workspace=workspace,
            state_manager=state_manager,
        )

    async def execute(self, context: dict) -> AgentResult:
        """Execute demo video production.

        Steps:
        1. Check prerequisites (Playwright, FFmpeg)
        2. Read architecture.md for user paths to demo
        3. Generate demo script via LLM
        4. Attempt to start the application
        5. Record browser session with Playwright
        6. Generate voiceover narration via LLM
        7. Generate SRT captions
        8. Encode video with FFmpeg (burn-in captions, MP4, ≥1280x720)
        9. Save video/demo.mp4, video/script.md, video/captions.srt

        Args:
            context: Execution context dict. May contain:
                - app_url (str): URL where the app is running.
                - app_start_command (str): Command to start the app.

        Returns:
            AgentResult with success status and artifacts produced.
        """
        start_time = time.monotonic()

        # Step 1: Check prerequisites
        await self.log("Checking prerequisites (Playwright, FFmpeg)...")

        if not _check_playwright_available():
            elapsed = time.monotonic() - start_time
            error_msg = (
                "Playwright is not installed. Cannot record demo video. "
                "Install with: pip install playwright && playwright install"
            )
            await self.log(f"FAILURE: {error_msg}")
            return AgentResult(
                agent_name=self.agent_name,
                success=False,
                artifacts_produced=[],
                error=error_msg,
                duration_seconds=elapsed,
            )

        if not _check_ffmpeg_available():
            elapsed = time.monotonic() - start_time
            error_msg = (
                "FFmpeg is not installed or not found on PATH. "
                "Cannot encode demo video. Install FFmpeg to proceed."
            )
            await self.log(f"FAILURE: {error_msg}")
            return AgentResult(
                agent_name=self.agent_name,
                success=False,
                artifacts_produced=[],
                error=error_msg,
                duration_seconds=elapsed,
            )

        # Step 2: Read architecture.md for user paths
        await self.log("Reading architecture.md for demo user paths...")
        architecture = await self._read_architecture()
        if not architecture:
            elapsed = time.monotonic() - start_time
            error_msg = "architecture.md not found or empty in workspace"
            await self.log(f"FAILURE: {error_msg}")
            return AgentResult(
                agent_name=self.agent_name,
                success=False,
                artifacts_produced=[],
                error=error_msg,
                duration_seconds=elapsed,
            )

        # Step 3: Generate demo script via LLM
        await self.log("Generating demo script from architecture...")
        demo_steps = await self._generate_demo_script(architecture)

        if not demo_steps:
            elapsed = time.monotonic() - start_time
            error_msg = "Failed to generate demo script from architecture"
            await self.log(f"FAILURE: {error_msg}")
            return AgentResult(
                agent_name=self.agent_name,
                success=False,
                artifacts_produced=[],
                error=error_msg,
                duration_seconds=elapsed,
            )

        # Step 4: Attempt to start the application
        app_url = context.get("app_url", "http://localhost:3000")
        app_process = None

        await self.log(f"Attempting to connect to application at {app_url}...")
        app_running = await self._check_app_running(app_url)

        if not app_running:
            # Try to start the application
            app_start_command = context.get("app_start_command", "")
            if app_start_command:
                await self.log(
                    f"App not running. Attempting to start: {app_start_command}"
                )
                app_process = await self._start_app(app_start_command)
                if app_process is None:
                    elapsed = time.monotonic() - start_time
                    error_msg = (
                        f"Failed to start application with command: "
                        f"'{app_start_command}'. Cannot record demo video."
                    )
                    await self.log(f"FAILURE: {error_msg}")
                    return AgentResult(
                        agent_name=self.agent_name,
                        success=False,
                        artifacts_produced=[],
                        error=error_msg,
                        duration_seconds=elapsed,
                    )
            else:
                elapsed = time.monotonic() - start_time
                error_msg = (
                    f"Application is not running at {app_url} and no "
                    f"start command was provided. Cannot record demo video."
                )
                await self.log(f"FAILURE: {error_msg}")
                return AgentResult(
                    agent_name=self.agent_name,
                    success=False,
                    artifacts_produced=[],
                    error=error_msg,
                    duration_seconds=elapsed,
                )

        try:
            # Step 5: Record browser session with Playwright
            await self.log("Recording browser session with Playwright...")
            temp_dir = tempfile.mkdtemp(prefix="demo_video_")
            raw_video_path = Path(temp_dir) / "raw_recording.webm"

            recording_success = await self._record_browser_session(
                app_url=app_url,
                demo_steps=demo_steps,
                output_path=raw_video_path,
            )

            if not recording_success:
                elapsed = time.monotonic() - start_time
                error_msg = (
                    "Playwright recording failed. The browser session "
                    "could not be captured."
                )
                await self.log(f"FAILURE: {error_msg}")
                return AgentResult(
                    agent_name=self.agent_name,
                    success=False,
                    artifacts_produced=[],
                    error=error_msg,
                    duration_seconds=elapsed,
                )

            # Step 6: Generate voiceover script via LLM
            await self.log("Generating voiceover narration script...")
            voiceover_script = await self._generate_voiceover(demo_steps)

            # Step 7: Generate SRT captions
            await self.log("Generating SRT captions...")
            srt_content = generate_srt_from_steps(demo_steps)

            # Step 8: Encode video with FFmpeg
            await self.log(
                "Encoding video with FFmpeg (burning captions, MP4, "
                f"{MIN_WIDTH}x{MIN_HEIGHT})..."
            )
            srt_path = Path(temp_dir) / "captions.srt"
            srt_path.write_text(srt_content, encoding="utf-8")

            final_video_path = Path(temp_dir) / "demo.mp4"
            encode_success = await self._encode_video(
                input_path=raw_video_path,
                srt_path=srt_path,
                output_path=final_video_path,
            )

            if not encode_success:
                elapsed = time.monotonic() - start_time
                error_msg = (
                    "FFmpeg encoding failed. Could not produce final "
                    "MP4 video with burned-in captions."
                )
                await self.log(f"FAILURE: {error_msg}")
                return AgentResult(
                    agent_name=self.agent_name,
                    success=False,
                    artifacts_produced=[],
                    error=error_msg,
                    duration_seconds=elapsed,
                )

            # Step 9: Save artifacts to video/ directory
            await self.log("Saving video artifacts to workspace...")

            # Read the encoded video and save to workspace
            video_bytes = final_video_path.read_bytes()
            await self.write_artifact("video/demo.mp4", video_bytes)

            # Save demo script markdown
            script_md = generate_demo_script_md(demo_steps)
            await self.write_artifact("video/script.md", script_md)

            # Save SRT captions
            await self.write_artifact("video/captions.srt", srt_content)

            elapsed = time.monotonic() - start_time
            await self.log(
                f"Demo video production complete in {elapsed:.1f}s. "
                f"Artifacts: video/demo.mp4, video/script.md, video/captions.srt"
            )

            return AgentResult(
                agent_name=self.agent_name,
                success=True,
                artifacts_produced=[
                    "video/demo.mp4",
                    "video/script.md",
                    "video/captions.srt",
                ],
                duration_seconds=elapsed,
            )

        finally:
            # Cleanup: terminate app process if we started it
            if app_process is not None:
                await self._stop_app(app_process)

            # Cleanup temp directory
            try:
                import shutil as _shutil
                _shutil.rmtree(temp_dir, ignore_errors=True)
            except Exception:
                pass

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

    async def _generate_demo_script(self, architecture: str) -> list[dict]:
        """Generate a demo script from the architecture document via LLM.

        Asks the LLM to produce a structured list of demo steps
        including actions, URLs, durations, and narration.

        Args:
            architecture: Content of architecture.md.

        Returns:
            List of step dicts, or empty list on failure.
        """
        import json

        prompt = DEMO_SCRIPT_PROMPT.format(architecture=architecture)

        try:
            response = await self.llm_generate(
                prompt=prompt,
                system=DEMO_VIDEO_SYSTEM_PROMPT,
            )

            # Parse JSON from response (handle markdown code blocks)
            response_text = response.strip()
            if response_text.startswith("```"):
                # Remove markdown code fences
                lines = response_text.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                response_text = "\n".join(lines)

            steps = json.loads(response_text)

            if not isinstance(steps, list) or len(steps) == 0:
                await self.log("LLM returned empty or invalid demo steps")
                return []

            # Validate and normalize steps
            validated_steps = self._validate_demo_steps(steps)
            return validated_steps

        except (json.JSONDecodeError, ValueError) as e:
            await self.log(f"Failed to parse demo script from LLM: {e}")
            return []
        except Exception as e:
            await self.log(f"Error generating demo script: {e}")
            return []

    def _validate_demo_steps(self, steps: list[dict]) -> list[dict]:
        """Validate and normalize demo steps, ensuring total duration is 60-300s.

        Args:
            steps: Raw list of step dicts from LLM.

        Returns:
            Validated and normalized list of step dicts.
        """
        validated: list[dict] = []

        for step in steps:
            validated_step = {
                "action": str(step.get("action", "View page")),
                "url": str(step.get("url", "")),
                "duration_seconds": max(5, min(30, int(step.get("duration_seconds", 10)))),
                "narration": str(step.get("narration", "")),
            }
            validated.append(validated_step)

        # Adjust total duration to fit within 60-300 seconds
        total_duration = sum(s["duration_seconds"] for s in validated)

        if total_duration < MIN_DURATION_SECONDS and validated:
            # Scale up durations proportionally
            scale_factor = MIN_DURATION_SECONDS / total_duration
            for step in validated:
                step["duration_seconds"] = min(
                    30, int(step["duration_seconds"] * scale_factor)
                )

        elif total_duration > MAX_DURATION_SECONDS and validated:
            # Scale down durations proportionally
            scale_factor = MAX_DURATION_SECONDS / total_duration
            for step in validated:
                step["duration_seconds"] = max(
                    5, int(step["duration_seconds"] * scale_factor)
                )

        return validated

    async def _check_app_running(self, url: str) -> bool:
        """Check if the application is responding at the given URL.

        Args:
            url: The URL to check.

        Returns:
            True if the app responds with a 2xx/3xx status, False otherwise.
        """
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                return response.status_code < 400
        except Exception:
            return False

    async def _start_app(
        self, command: str
    ) -> asyncio.subprocess.Process | None:
        """Attempt to start the application with the given command.

        Waits up to 30 seconds for the app to become responsive.

        Args:
            command: Shell command to start the application.

        Returns:
            The subprocess.Process if started successfully, None otherwise.
        """
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            # Wait for app to become responsive (up to 30s)
            for _ in range(30):
                await asyncio.sleep(1)
                if process.returncode is not None:
                    # Process exited prematurely
                    await self.log(
                        f"App process exited with code {process.returncode}"
                    )
                    return None
                # Check if responsive (assume default URL)
                if await self._check_app_running("http://localhost:3000"):
                    await self.log("Application started successfully")
                    return process

            await self.log("Application did not become responsive within 30s")
            process.terminate()
            return None

        except Exception as e:
            await self.log(f"Failed to start application: {e}")
            return None

    async def _stop_app(self, process: asyncio.subprocess.Process) -> None:
        """Gracefully stop an application process.

        Sends SIGTERM, waits 5s, then SIGKILL if still running.

        Args:
            process: The subprocess to stop.
        """
        try:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=5.0)
            except TimeoutError:
                process.kill()
                await process.wait()
        except Exception as e:
            await self.log(f"Warning: Error stopping app process: {e}")

    async def _record_browser_session(
        self,
        app_url: str,
        demo_steps: list[dict],
        output_path: Path,
    ) -> bool:
        """Record a browser session using Playwright.

        Visits each URL in the demo steps, performs actions,
        and records the session as a video file.

        Args:
            app_url: Base URL of the application.
            demo_steps: List of demo step dicts with actions and URLs.
            output_path: Path to save the raw recording.

        Returns:
            True if recording succeeded, False otherwise.
        """
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    viewport={"width": MIN_WIDTH, "height": MIN_HEIGHT},
                    record_video_dir=str(output_path.parent),
                    record_video_size={
                        "width": MIN_WIDTH,
                        "height": MIN_HEIGHT,
                    },
                )
                page = await context.new_page()

                for step in demo_steps:
                    url = step.get("url", "")
                    duration = step.get("duration_seconds", 10)

                    if url:
                        # Construct full URL if relative
                        if url.startswith("/"):
                            full_url = f"{app_url.rstrip('/')}{url}"
                        elif url.startswith("http"):
                            full_url = url
                        else:
                            full_url = f"{app_url.rstrip('/')}/{url}"

                        try:
                            await page.goto(
                                full_url,
                                wait_until="networkidle",
                                timeout=15000,
                            )
                        except Exception as nav_err:
                            await self.log(
                                f"Navigation warning for {full_url}: {nav_err}"
                            )

                    # Wait for the step duration
                    await asyncio.sleep(duration)

                # Close context to finalize video
                await context.close()
                await browser.close()

            # Find the recorded video file
            video_files = list(output_path.parent.glob("*.webm"))
            if video_files:
                # Move the first video to our expected path
                video_files[0].rename(output_path)
                return True
            else:
                await self.log("No video file produced by Playwright")
                return False

        except Exception as e:
            await self.log(f"Playwright recording failed: {e}")
            return False

    async def _generate_voiceover(self, demo_steps: list[dict]) -> str:
        """Generate voiceover narration script from demo steps via LLM.

        Args:
            demo_steps: List of demo step dicts with narration hints.

        Returns:
            Generated voiceover script text.
        """
        steps_text = "\n".join(
            f"Step {i}: Action={s['action']}, "
            f"Duration={s['duration_seconds']}s, "
            f"Narration hint={s.get('narration', 'N/A')}"
            for i, s in enumerate(demo_steps, start=1)
        )

        prompt = VOICEOVER_PROMPT.format(demo_steps=steps_text)

        try:
            response = await self.llm_generate(
                prompt=prompt,
                system=DEMO_VIDEO_SYSTEM_PROMPT,
            )
            return response
        except Exception as e:
            await self.log(f"Warning: Voiceover generation failed: {e}")
            # Fall back to using step narrations directly
            return steps_text

    async def _encode_video(
        self,
        input_path: Path,
        srt_path: Path,
        output_path: Path,
    ) -> bool:
        """Encode video with FFmpeg, burning in captions.

        Encodes the raw recording to MP4 format at minimum 1280x720
        with burned-in SRT subtitles.

        Args:
            input_path: Path to the raw video recording.
            srt_path: Path to the SRT captions file.
            output_path: Path for the final encoded MP4.

        Returns:
            True if encoding succeeded, False otherwise.
        """
        try:
            # Build FFmpeg command:
            # - Scale to at least 1280x720
            # - Burn subtitles
            # - Encode as H.264 MP4
            srt_escaped = str(srt_path).replace("\\", "/").replace(":", "\\:")

            cmd = [
                "ffmpeg",
                "-y",  # Overwrite output
                "-i", str(input_path),
                "-vf", (
                    f"scale='max({MIN_WIDTH},iw)':'"
                    f"max({MIN_HEIGHT},ih)':"
                    f"force_original_aspect_ratio=increase,"
                    f"subtitles={srt_escaped}"
                ),
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-c:a", "aac",
                "-b:a", "128k",
                "-movflags", "+faststart",
                str(output_path),
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=120.0,
            )

            if process.returncode != 0:
                error_output = stderr.decode("utf-8", errors="replace")
                await self.log(
                    f"FFmpeg encoding failed (exit code {process.returncode}): "
                    f"{error_output[:500]}"
                )
                return False

            # Verify output file exists and has content
            if output_path.exists() and output_path.stat().st_size > 0:
                return True
            else:
                await self.log("FFmpeg produced empty or missing output file")
                return False

        except TimeoutError:
            await self.log("FFmpeg encoding timed out after 120 seconds")
            return False
        except Exception as e:
            await self.log(f"FFmpeg encoding error: {e}")
            return False
