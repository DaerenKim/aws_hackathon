"""Frontend Engineer Agent for Hackathon Studio.

Reads architecture.md and generates a complete Next.js + TypeScript + TailwindCSS
+ shadcn/ui frontend application with responsive layouts, client-side state
management, and API integration including loading/error states.

Writes all output to the frontend/ directory in the shared workspace.
"""

import logging
import time

from app.agents.base import BaseAgent
from app.models.artifacts import AgentResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a senior frontend engineer. Generate production-quality "
    "Next.js TypeScript code with TailwindCSS and shadcn/ui. "
    "Every component must have loading, error, and empty states. "
    "Use responsive design (mobile-first) with breakpoints at "
    "360px (mobile), 768px (tablet), and 1280px (desktop)."
)

MAX_RETRIES = 2


# Files the agent generates in the frontend/ directory
GENERATED_FILES = [
    "frontend/package.json",
    "frontend/tsconfig.json",
    "frontend/tailwind.config.ts",
    "frontend/src/app/layout.tsx",
    "frontend/src/app/page.tsx",
    "frontend/src/lib/api.ts",
]


class FrontendEngineerAgent(BaseAgent):
    """Agent that generates a complete Next.js frontend application.

    Reads the architecture specification from the shared workspace and
    uses the LLM to generate a full Next.js + TypeScript + TailwindCSS
    + shadcn/ui frontend with responsive layouts, API integration,
    and proper loading/error states.

    Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
    """

    async def execute(self, context: dict) -> AgentResult:
        """Execute frontend generation to produce frontend/ directory.

        Args:
            context: Dictionary with optional overrides. Currently unused.

        Returns:
            AgentResult indicating success/failure with artifacts produced.
        """
        start_time = time.monotonic()
        artifacts_produced: list[str] = []

        # Step 1: Read architecture.md from workspace
        try:
            architecture = await self.read_artifact(
                "architecture.md", "project_planner"
            )
        except (PermissionError, FileNotFoundError) as e:
            error_msg = f"Failed to read architecture.md: {e}"
            await self.log(error_msg)
            return AgentResult(
                agent_name=self.agent_name,
                success=False,
                artifacts_produced=[],
                error=error_msg,
                duration_seconds=time.monotonic() - start_time,
            )

        await self.log("Architecture loaded. Generating frontend application...")

        # Step 2: Generate component hierarchy and page structure
        component_plan = await self._generate_component_plan(architecture)
        await self.log("Component plan generated.")

        # Step 3: Generate package.json
        package_json = await self._generate_package_json(architecture)
        await self.write_artifact("frontend/package.json", package_json)
        artifacts_produced.append("frontend/package.json")
        await self.log("Generated frontend/package.json")

        # Step 4: Generate tsconfig.json
        tsconfig = await self._generate_tsconfig()
        await self.write_artifact("frontend/tsconfig.json", tsconfig)
        artifacts_produced.append("frontend/tsconfig.json")
        await self.log("Generated frontend/tsconfig.json")

        # Step 5: Generate tailwind.config.ts
        tailwind_config = await self._generate_tailwind_config()
        await self.write_artifact("frontend/tailwind.config.ts", tailwind_config)
        artifacts_produced.append("frontend/tailwind.config.ts")
        await self.log("Generated frontend/tailwind.config.ts")

        # Step 6: Generate layout and pages
        layout = await self._generate_layout(architecture, component_plan)
        await self.write_artifact("frontend/src/app/layout.tsx", layout)
        artifacts_produced.append("frontend/src/app/layout.tsx")
        await self.log("Generated frontend/src/app/layout.tsx")

        page = await self._generate_main_page(architecture, component_plan)
        await self.write_artifact("frontend/src/app/page.tsx", page)
        artifacts_produced.append("frontend/src/app/page.tsx")
        await self.log("Generated frontend/src/app/page.tsx")

        # Step 7: Generate API client
        api_client = await self._generate_api_client(architecture)
        await self.write_artifact("frontend/src/lib/api.ts", api_client)
        artifacts_produced.append("frontend/src/lib/api.ts")
        await self.log("Generated frontend/src/lib/api.ts")

        # Step 8: Generate components from the plan
        components = await self._generate_components(
            architecture, component_plan
        )
        for comp_path, comp_content in components.items():
            full_path = f"frontend/src/components/{comp_path}"
            await self.write_artifact(full_path, comp_content)
            artifacts_produced.append(full_path)
            await self.log(f"Generated {full_path}")

        # Step 9: Generate additional pages based on architecture
        pages = await self._generate_additional_pages(
            architecture, component_plan
        )
        for page_path, page_content in pages.items():
            full_path = f"frontend/src/app/{page_path}"
            await self.write_artifact(full_path, page_content)
            artifacts_produced.append(full_path)
            await self.log(f"Generated {full_path}")

        # Step 10: Generate hooks
        hooks = await self._generate_hooks(architecture)
        for hook_path, hook_content in hooks.items():
            full_path = f"frontend/src/hooks/{hook_path}"
            await self.write_artifact(full_path, hook_content)
            artifacts_produced.append(full_path)
            await self.log(f"Generated {full_path}")

        # Step 11: Generate globals.css
        globals_css = self._generate_globals_css()
        await self.write_artifact(
            "frontend/src/app/globals.css", globals_css
        )
        artifacts_produced.append("frontend/src/app/globals.css")
        await self.log("Generated frontend/src/app/globals.css")

        elapsed = time.monotonic() - start_time
        await self.log(
            f"Frontend generation complete. "
            f"{len(artifacts_produced)} files produced in {elapsed:.1f}s."
        )

        return AgentResult(
            agent_name=self.agent_name,
            success=True,
            artifacts_produced=artifacts_produced,
            duration_seconds=elapsed,
        )

    async def _generate_component_plan(self, architecture: str) -> str:
        """Generate a component hierarchy plan from the architecture spec.

        Args:
            architecture: The architecture.md content.

        Returns:
            A structured plan describing components, pages, and their relationships.
        """
        prompt = (
            "Based on the following architecture specification, generate a "
            "detailed component hierarchy plan for a Next.js frontend.\n\n"
            "The plan should include:\n"
            "1. List of pages with their routes\n"
            "2. Shared components (with props described)\n"
            "3. Page-specific components\n"
            "4. State management approach (React hooks/context)\n"
            "5. API endpoints each page needs to call\n\n"
            "Format as structured text with clear sections.\n\n"
            f"--- ARCHITECTURE ---\n{architecture}\n\n"
            "Generate the component plan now."
        )
        return await self.llm_generate(prompt, system=SYSTEM_PROMPT)

    async def _generate_package_json(self, architecture: str) -> str:
        """Generate package.json with Next.js, React, TailwindCSS, shadcn/ui deps.

        Args:
            architecture: The architecture.md content for context.

        Returns:
            The package.json content as a string.
        """
        prompt = (
            "Generate a package.json for a Next.js 14 application with:\n"
            "- next, react, react-dom (latest stable)\n"
            "- typescript, @types/react, @types/node\n"
            "- tailwindcss, postcss, autoprefixer\n"
            "- shadcn/ui dependencies (class-variance-authority, clsx, "
            "tailwind-merge, lucide-react, @radix-ui/react-* primitives)\n"
            "- Include scripts: dev, build, start, lint\n"
            "- Project name should be derived from the architecture\n\n"
            "IMPORTANT: Output ONLY valid JSON. No markdown fences, "
            "no explanation text.\n\n"
            f"--- ARCHITECTURE ---\n{architecture[:2000]}\n\n"
            "Generate the package.json content now."
        )
        result = await self.llm_generate(prompt, system=SYSTEM_PROMPT)
        return self._extract_json_or_code(result)

    async def _generate_tsconfig(self) -> str:
        """Generate tsconfig.json for Next.js + TypeScript project.

        Returns:
            The tsconfig.json content as a string.
        """
        prompt = (
            "Generate a tsconfig.json for a Next.js 14 + TypeScript project.\n"
            "Include:\n"
            "- strict mode enabled\n"
            "- path aliases (@ -> ./src)\n"
            "- module resolution: bundler\n"
            "- jsx: preserve\n"
            "- include and exclude arrays\n\n"
            "IMPORTANT: Output ONLY valid JSON. No markdown fences, "
            "no explanation text."
        )
        result = await self.llm_generate(prompt, system=SYSTEM_PROMPT)
        return self._extract_json_or_code(result)

    async def _generate_tailwind_config(self) -> str:
        """Generate tailwind.config.ts with responsive breakpoints.

        Returns:
            The tailwind.config.ts content as a string.
        """
        prompt = (
            "Generate a tailwind.config.ts for a Next.js project with:\n"
            "- Content paths for src/ directory\n"
            "- Custom breakpoints: sm (360px), md (768px), lg (1280px)\n"
            "- shadcn/ui compatible theme extension\n"
            "- darkMode: 'class'\n\n"
            "IMPORTANT: Output ONLY the TypeScript code. No markdown fences, "
            "no explanation text."
        )
        result = await self.llm_generate(prompt, system=SYSTEM_PROMPT)
        return self._extract_code_block(result)

    async def _generate_layout(
        self, architecture: str, component_plan: str
    ) -> str:
        """Generate the root layout.tsx for the Next.js app.

        Args:
            architecture: The architecture.md content.
            component_plan: The generated component plan.

        Returns:
            The layout.tsx source code as a string.
        """
        prompt = (
            "Generate a Next.js 14 root layout (src/app/layout.tsx) with:\n"
            "- Metadata (title, description from architecture)\n"
            "- Global font setup (Inter from next/font/google)\n"
            "- Import globals.css\n"
            "- Responsive wrapper that works at 360px, 768px, 1280px\n"
            "- Children prop rendering\n\n"
            "IMPORTANT: Output ONLY the TypeScript/JSX code. No markdown "
            "fences, no explanation.\n\n"
            f"--- ARCHITECTURE ---\n{architecture[:1500]}\n\n"
            "Generate layout.tsx now."
        )
        result = await self.llm_generate(prompt, system=SYSTEM_PROMPT)
        return self._extract_code_block(result)

    async def _generate_main_page(
        self, architecture: str, component_plan: str
    ) -> str:
        """Generate the main page (src/app/page.tsx).

        Args:
            architecture: The architecture.md content.
            component_plan: The generated component plan.

        Returns:
            The page.tsx source code as a string.
        """
        prompt = (
            "Generate a Next.js 14 main page (src/app/page.tsx) with:\n"
            "- Hero section or landing content based on the architecture\n"
            "- Responsive layout (mobile-first, works at 360px/768px/1280px)\n"
            "- Loading state while data fetches\n"
            "- Error state for failed API calls\n"
            "- Navigation to other pages\n"
            "- Uses TailwindCSS for styling\n\n"
            "IMPORTANT: Output ONLY the TypeScript/JSX code. No markdown "
            "fences, no explanation.\n\n"
            f"--- ARCHITECTURE ---\n{architecture[:1500]}\n\n"
            f"--- COMPONENT PLAN ---\n{component_plan[:1500]}\n\n"
            "Generate page.tsx now."
        )
        result = await self.llm_generate(prompt, system=SYSTEM_PROMPT)
        return self._extract_code_block(result)

    async def _generate_api_client(self, architecture: str) -> str:
        """Generate the API client (src/lib/api.ts).

        Args:
            architecture: The architecture.md content with API definitions.

        Returns:
            The api.ts source code as a string.
        """
        prompt = (
            "Generate a TypeScript API client (src/lib/api.ts) that:\n"
            "- Exports an ApiClient class or set of functions\n"
            "- Has a configurable base URL (default: http://localhost:8000)\n"
            "- Implements fetch wrapper with error handling\n"
            "- Handles JSON request/response serialization\n"
            "- Includes timeout support (30s default)\n"
            "- Returns typed responses\n"
            "- Includes methods for each API endpoint from the architecture\n"
            "- Each method handles loading state (returns Promise)\n"
            "- Each method handles error states (throws typed errors)\n\n"
            "IMPORTANT: Output ONLY the TypeScript code. No markdown "
            "fences, no explanation.\n\n"
            f"--- ARCHITECTURE API ENDPOINTS ---\n{architecture[:3000]}\n\n"
            "Generate api.ts now."
        )
        result = await self.llm_generate(prompt, system=SYSTEM_PROMPT)
        return self._extract_code_block(result)

    async def _generate_components(
        self, architecture: str, component_plan: str
    ) -> dict[str, str]:
        """Generate shared UI components based on the component plan.

        Args:
            architecture: The architecture.md content.
            component_plan: The generated component plan.

        Returns:
            Dictionary mapping relative component path to source code.
        """
        prompt = (
            "Based on the architecture and component plan, generate the "
            "following shared UI components as separate files. For each "
            "component, provide the filename and complete TypeScript/JSX code.\n\n"
            "Required components:\n"
            "1. loading-spinner.tsx - A reusable loading spinner\n"
            "2. error-display.tsx - Error state display with retry button\n"
            "3. empty-state.tsx - Empty state placeholder\n"
            "4. responsive-container.tsx - Responsive wrapper component\n\n"
            "Each component must:\n"
            "- Be a React functional component with TypeScript types\n"
            "- Use TailwindCSS for styling\n"
            "- Be responsive (mobile-first)\n"
            "- Have proper prop interfaces\n\n"
            "Format your output as:\n"
            "=== FILENAME: loading-spinner.tsx ===\n"
            "[code]\n"
            "=== FILENAME: error-display.tsx ===\n"
            "[code]\n"
            "... and so on for each component.\n\n"
            f"--- ARCHITECTURE ---\n{architecture[:1500]}\n\n"
            f"--- COMPONENT PLAN ---\n{component_plan[:1500]}\n\n"
            "Generate all components now."
        )
        result = await self.llm_generate(prompt, system=SYSTEM_PROMPT)
        return self._parse_multi_file_output(result)

    async def _generate_additional_pages(
        self, architecture: str, component_plan: str
    ) -> dict[str, str]:
        """Generate additional pages based on architecture routes.

        Args:
            architecture: The architecture.md content.
            component_plan: The generated component plan.

        Returns:
            Dictionary mapping relative page path to source code.
        """
        prompt = (
            "Based on the architecture specification, generate additional "
            "Next.js 14 pages beyond the main page. Identify routes from "
            "the architecture and create page files.\n\n"
            "Each page must:\n"
            "- Use 'use client' directive where state is needed\n"
            "- Include loading state (skeleton or spinner)\n"
            "- Include error state (with retry)\n"
            "- Be responsive (mobile-first, 360px/768px/1280px)\n"
            "- Use TailwindCSS + shadcn/ui patterns\n"
            "- Import from @/lib/api for API calls\n"
            "- Import shared components from @/components/\n\n"
            "Format your output as:\n"
            "=== FILENAME: dashboard/page.tsx ===\n"
            "[code]\n"
            "=== FILENAME: settings/page.tsx ===\n"
            "[code]\n"
            "... for each page.\n\n"
            "If the architecture doesn't specify additional routes, "
            "generate at minimum a dashboard/page.tsx and about/page.tsx.\n\n"
            f"--- ARCHITECTURE ---\n{architecture[:2000]}\n\n"
            f"--- COMPONENT PLAN ---\n{component_plan[:1500]}\n\n"
            "Generate the pages now."
        )
        result = await self.llm_generate(prompt, system=SYSTEM_PROMPT)
        return self._parse_multi_file_output(result)

    async def _generate_hooks(self, architecture: str) -> dict[str, str]:
        """Generate custom React hooks for state management and API integration.

        Args:
            architecture: The architecture.md content.

        Returns:
            Dictionary mapping relative hook path to source code.
        """
        prompt = (
            "Generate custom React hooks for a Next.js application:\n\n"
            "1. use-api.ts - Generic hook for API calls with:\n"
            "   - loading state (boolean)\n"
            "   - error state (Error | null)\n"
            "   - data state (generic type)\n"
            "   - refetch function\n"
            "   - Abort controller for cleanup\n\n"
            "2. use-async-action.ts - Hook for mutations/actions with:\n"
            "   - loading state\n"
            "   - error state\n"
            "   - execute function\n"
            "   - reset function\n\n"
            "Each hook must:\n"
            "- Be fully typed with TypeScript generics\n"
            "- Handle cleanup on unmount\n"
            "- Provide proper error typing\n\n"
            "Format your output as:\n"
            "=== FILENAME: use-api.ts ===\n"
            "[code]\n"
            "=== FILENAME: use-async-action.ts ===\n"
            "[code]\n\n"
            f"--- ARCHITECTURE ---\n{architecture[:1500]}\n\n"
            "Generate the hooks now."
        )
        result = await self.llm_generate(prompt, system=SYSTEM_PROMPT)
        return self._parse_multi_file_output(result)

    def _generate_globals_css(self) -> str:
        """Generate globals.css with TailwindCSS directives.

        Returns:
            The globals.css content.
        """
        return (
            "@tailwind base;\n"
            "@tailwind components;\n"
            "@tailwind utilities;\n"
            "\n"
            "@layer base {\n"
            "  :root {\n"
            "    --background: 0 0% 100%;\n"
            "    --foreground: 222.2 84% 4.9%;\n"
            "    --card: 0 0% 100%;\n"
            "    --card-foreground: 222.2 84% 4.9%;\n"
            "    --popover: 0 0% 100%;\n"
            "    --popover-foreground: 222.2 84% 4.9%;\n"
            "    --primary: 222.2 47.4% 11.2%;\n"
            "    --primary-foreground: 210 40% 98%;\n"
            "    --secondary: 210 40% 96.1%;\n"
            "    --secondary-foreground: 222.2 47.4% 11.2%;\n"
            "    --muted: 210 40% 96.1%;\n"
            "    --muted-foreground: 215.4 16.3% 46.9%;\n"
            "    --accent: 210 40% 96.1%;\n"
            "    --accent-foreground: 222.2 47.4% 11.2%;\n"
            "    --destructive: 0 84.2% 60.2%;\n"
            "    --destructive-foreground: 210 40% 98%;\n"
            "    --border: 214.3 31.8% 91.4%;\n"
            "    --input: 214.3 31.8% 91.4%;\n"
            "    --ring: 222.2 84% 4.9%;\n"
            "    --radius: 0.5rem;\n"
            "  }\n"
            "\n"
            "  .dark {\n"
            "    --background: 222.2 84% 4.9%;\n"
            "    --foreground: 210 40% 98%;\n"
            "    --card: 222.2 84% 4.9%;\n"
            "    --card-foreground: 210 40% 98%;\n"
            "    --popover: 222.2 84% 4.9%;\n"
            "    --popover-foreground: 210 40% 98%;\n"
            "    --primary: 210 40% 98%;\n"
            "    --primary-foreground: 222.2 47.4% 11.2%;\n"
            "    --secondary: 217.2 32.6% 17.5%;\n"
            "    --secondary-foreground: 210 40% 98%;\n"
            "    --muted: 217.2 32.6% 17.5%;\n"
            "    --muted-foreground: 215 20.2% 65.1%;\n"
            "    --accent: 217.2 32.6% 17.5%;\n"
            "    --accent-foreground: 210 40% 98%;\n"
            "    --destructive: 0 62.8% 30.6%;\n"
            "    --destructive-foreground: 210 40% 98%;\n"
            "    --border: 217.2 32.6% 17.5%;\n"
            "    --input: 217.2 32.6% 17.5%;\n"
            "    --ring: 212.7 26.8% 83.9%;\n"
            "  }\n"
            "}\n"
            "\n"
            "@layer base {\n"
            "  * {\n"
            "    @apply border-border;\n"
            "  }\n"
            "  body {\n"
            "    @apply bg-background text-foreground;\n"
            "  }\n"
            "}\n"
        )

    def _parse_multi_file_output(self, output: str) -> dict[str, str]:
        """Parse LLM output containing multiple files delimited by markers.

        Expected format:
            === FILENAME: some-file.tsx ===
            [code content]
            === FILENAME: another-file.tsx ===
            [code content]

        Args:
            output: Raw LLM output with file delimiters.

        Returns:
            Dictionary mapping filename to file content.
            Returns a default component if parsing fails.
        """
        files: dict[str, str] = {}
        current_filename: str | None = None
        current_lines: list[str] = []

        for line in output.split("\n"):
            stripped = line.strip()
            if stripped.startswith("=== FILENAME:") and stripped.endswith("==="):
                # Save previous file if exists
                if current_filename and current_lines:
                    content = "\n".join(current_lines).strip()
                    files[current_filename] = self._extract_code_block(content)
                # Start new file
                filename_part = stripped[len("=== FILENAME:"):].rstrip("=").strip()
                current_filename = filename_part
                current_lines = []
            else:
                current_lines.append(line)

        # Don't forget the last file
        if current_filename and current_lines:
            content = "\n".join(current_lines).strip()
            files[current_filename] = self._extract_code_block(content)

        # If parsing yielded nothing, create a default placeholder
        if not files:
            files["placeholder.tsx"] = (
                '"use client";\n\n'
                "export default function Placeholder() {\n"
                "  return <div>Placeholder component</div>;\n"
                "}\n"
            )

        return files

    def _extract_code_block(self, text: str) -> str:
        """Extract code from potential markdown code fences.

        If the text is wrapped in ```...``` fences, strips them.
        Otherwise returns the text as-is.

        Args:
            text: Raw text that may contain code fences.

        Returns:
            Clean code content without markdown fencing.
        """
        stripped = text.strip()
        # Handle ```typescript or ```tsx or ```ts or plain ```
        if stripped.startswith("```"):
            lines = stripped.split("\n")
            # Remove first line (```lang) and last line (```)
            if lines[-1].strip() == "```":
                lines = lines[1:-1]
            else:
                lines = lines[1:]
            return "\n".join(lines).strip()
        return stripped

    def _extract_json_or_code(self, text: str) -> str:
        """Extract JSON or code content, stripping markdown fences.

        Tries to find JSON content within code fences first,
        then falls back to the raw text.

        Args:
            text: Raw text that may contain JSON in code fences.

        Returns:
            Clean JSON/code content.
        """
        stripped = text.strip()
        # Try to find JSON within code fences
        if "```" in stripped:
            return self._extract_code_block(stripped)
        return stripped
