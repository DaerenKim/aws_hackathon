"""GitHub Agent for Hackathon Studio.

Creates a public GitHub repository, generates structured commits for
workspace contents, configures repository settings (.gitignore, LICENSE,
branch protection), and pushes all code to main branch.

Uses PyGithub for GitHub API interactions. Authenticates via the
GITHUB_TOKEN environment variable. Implements retry logic (3 retries,
5s delay) for API error resilience.

Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6
"""

import asyncio
import logging
import os
import re
import time
from datetime import datetime, timezone

from app.agents.base import BaseAgent
from app.models.artifacts import AgentResult

logger = logging.getLogger(__name__)

# Retry configuration for GitHub API calls
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 5.0

# Standard .gitignore content for Python + Node.js projects
GITIGNORE_CONTENT = """\
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg
*.manifest
*.spec
pip-log.txt
pip-delete-this-directory.txt
htmlcov/
.tox/
.nox/
.coverage
.coverage.*
.cache
nosetests.xml
coverage.xml
*.cover
*.py,cover
.hypothesis/
.pytest_cache/
cover/
venv/
.env
.venv
env/
ENV/

# Node.js
node_modules/
npm-debug.log*
yarn-debug.log*
yarn-error.log*
.pnpm-debug.log*
dist/
.next/
out/
.nuxt/
.cache/
.output/
.env.local
.env.development.local
.env.test.local
.env.production.local

# IDE
.vscode/
.idea/
*.swp
*.swo
*~
.DS_Store
Thumbs.db

# Misc
*.log
logs/
*.pid
*.seed
*.pid.lock
"""

# MIT License template
MIT_LICENSE_TEMPLATE = """\
MIT License

Copyright (c) {year} Hackathon Studio

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

# Commit structure: ordered commits to organize the repository history
COMMIT_STRUCTURE = [
    {
        "message": "Initial setup: project configuration and .gitignore",
        "paths": [".gitignore", "LICENSE", "README.md", "project_spec.md"],
    },
    {
        "message": "Add backend implementation",
        "paths": ["backend/"],
    },
    {
        "message": "Add frontend implementation",
        "paths": ["frontend/"],
    },
    {
        "message": "Add integration and QA artifacts",
        "paths": [
            "architecture.md",
            "roadmap.md",
            "judge_analysis.md",
            "testing_report.md",
            "logs/",
        ],
    },
    {
        "message": "Add documentation",
        "paths": [
            "developer_guide.md",
            "api_docs.md",
            "docs/",
        ],
    },
    {
        "message": "Add presentation and demo materials",
        "paths": ["ppt/", "video/"],
    },
]


class GitHubAgent(BaseAgent):
    """Agent that sets up a GitHub repository and pushes project contents.

    Creates a new public repository via the GitHub API, generates
    structured commits for workspace contents, configures .gitignore,
    MIT LICENSE, and branch protection requiring one PR approval.

    Write boundaries: .gitignore, LICENSE

    Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6
    """

    async def execute(self, context: dict) -> AgentResult:
        """Execute GitHub repository creation and code push.

        Steps:
        1. Validate GITHUB_TOKEN environment variable
        2. Read project_spec.md to derive repository name
        3. Generate .gitignore and LICENSE files
        4. Create public GitHub repository
        5. Collect workspace files for each commit category
        6. Create structured commits (setup, backend, frontend, integration, docs, presentation)
        7. Push all content to main branch
        8. Configure branch protection (require 1 approval for PRs)
        9. Return repository URL in result

        Args:
            context: Dictionary with optional overrides. Currently unused.

        Returns:
            AgentResult with success status and repo URL in artifacts.
        """
        start_time = time.monotonic()
        artifacts_produced: list[str] = []

        # Step 1: Validate GITHUB_TOKEN
        github_token = os.environ.get("GITHUB_TOKEN")
        if not github_token:
            error_msg = (
                "GITHUB_TOKEN environment variable is not set. "
                "Please set it to a valid GitHub personal access token "
                "with 'repo' scope to create repositories."
            )
            await self.log(error_msg)
            return AgentResult(
                agent_name=self.agent_name,
                success=False,
                artifacts_produced=[],
                error=error_msg,
                duration_seconds=time.monotonic() - start_time,
            )

        # Step 2: Read project_spec.md to derive repository name
        await self.log("Reading project_spec.md to derive repository name...")
        try:
            project_spec = await self.read_artifact(
                "project_spec.md", "project_planner"
            )
            repo_name = self._derive_repo_name(project_spec)
        except (PermissionError, FileNotFoundError) as e:
            error_msg = f"Cannot read project_spec.md: {e}"
            await self.log(error_msg)
            return AgentResult(
                agent_name=self.agent_name,
                success=False,
                artifacts_produced=[],
                error=error_msg,
                duration_seconds=time.monotonic() - start_time,
            )

        await self.log(f"Derived repository name: '{repo_name}'")

        # Step 3: Generate .gitignore and LICENSE
        await self.log("Generating .gitignore and LICENSE files...")
        await self.write_artifact(".gitignore", GITIGNORE_CONTENT)
        artifacts_produced.append(".gitignore")

        license_content = MIT_LICENSE_TEMPLATE.format(
            year=datetime.now(timezone.utc).year
        )
        await self.write_artifact("LICENSE", license_content)
        artifacts_produced.append("LICENSE")

        # Step 4: Create public GitHub repository with retry logic
        await self.log(f"Creating public GitHub repository '{repo_name}'...")
        repo = await self._retry_github_operation(
            operation_name="create_repository",
            operation=lambda: self._create_repository(github_token, repo_name),
        )

        if repo is None:
            error_msg = (
                f"Failed to create GitHub repository '{repo_name}' "
                f"after {MAX_RETRIES} attempts."
            )
            await self.log(error_msg)
            return AgentResult(
                agent_name=self.agent_name,
                success=False,
                artifacts_produced=artifacts_produced,
                error=error_msg,
                duration_seconds=time.monotonic() - start_time,
            )

        repo_url = repo.html_url
        await self.log(f"Repository created: {repo_url}")

        # Step 5 & 6: Collect workspace files and create structured commits
        await self.log("Creating structured commits...")
        push_success = await self._retry_github_operation(
            operation_name="push_commits",
            operation=lambda: self._push_structured_commits(repo, github_token),
        )

        if not push_success:
            error_msg = (
                f"Failed to push structured commits to '{repo_name}' "
                f"after {MAX_RETRIES} attempts."
            )
            await self.log(error_msg)
            return AgentResult(
                agent_name=self.agent_name,
                success=False,
                artifacts_produced=artifacts_produced,
                error=error_msg,
                duration_seconds=time.monotonic() - start_time,
            )

        await self.log("All structured commits pushed successfully.")

        # Step 7: Configure branch protection
        await self.log("Configuring branch protection on main branch...")
        protection_success = await self._retry_github_operation(
            operation_name="configure_branch_protection",
            operation=lambda: self._configure_branch_protection(repo),
        )

        if not protection_success:
            # Branch protection failure is non-fatal; log warning and continue
            await self.log(
                "Warning: Failed to configure branch protection. "
                "Repository still usable but PRs won't require approval."
            )

        elapsed = time.monotonic() - start_time
        await self.log(
            f"GitHub Agent complete. Repository: {repo_url} "
            f"({elapsed:.1f}s elapsed)"
        )

        return AgentResult(
            agent_name=self.agent_name,
            success=True,
            artifacts_produced=artifacts_produced + [repo_url],
            duration_seconds=elapsed,
        )

    def _derive_repo_name(self, project_spec: str) -> str:
        """Derive a GitHub repository name from the project specification.

        Extracts the project name from the first H1 heading or the
        'refined idea' section title. Falls back to 'hackathon-project'
        if no suitable name is found.

        Args:
            project_spec: Content of project_spec.md.

        Returns:
            A sanitized repository name (lowercase, hyphenated).
        """
        # Try to find an H1 heading
        h1_match = re.search(r"^#\s+(.+)$", project_spec, re.MULTILINE)
        if h1_match:
            name = h1_match.group(1).strip()
        else:
            # Fallback: use first non-empty line
            lines = [
                line.strip()
                for line in project_spec.split("\n")
                if line.strip() and not line.strip().startswith("#")
            ]
            name = lines[0] if lines else "hackathon-project"

        # Sanitize: lowercase, replace spaces/special chars with hyphens
        sanitized = re.sub(r"[^a-z0-9]+", "-", name.lower())
        sanitized = sanitized.strip("-")

        # Limit length to 100 characters (GitHub limit)
        if len(sanitized) > 100:
            sanitized = sanitized[:100].rstrip("-")

        return sanitized or "hackathon-project"

    async def _retry_github_operation(
        self,
        operation_name: str,
        operation,
    ):
        """Execute a GitHub API operation with retry logic.

        Retries up to MAX_RETRIES times with RETRY_DELAY_SECONDS delay
        between attempts on any exception (authentication failure, rate
        limiting, network errors, name conflicts, etc.).

        Args:
            operation_name: Descriptive name for logging.
            operation: Callable (sync or async) to execute.

        Returns:
            The result of the operation, or None if all retries failed.
        """
        last_error: Exception | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                result = operation()
                # Support both sync and async callables
                if asyncio.iscoroutine(result):
                    result = await result
                return result
            except Exception as e:
                last_error = e
                await self.log(
                    f"GitHub API error during '{operation_name}' "
                    f"(attempt {attempt}/{MAX_RETRIES}): "
                    f"{type(e).__name__}: {str(e)}"
                )
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY_SECONDS)

        # All retries exhausted
        await self.log(
            f"All {MAX_RETRIES} retries exhausted for '{operation_name}'. "
            f"Last error: {last_error}"
        )
        return None

    def _create_repository(self, token: str, repo_name: str):
        """Create a new public GitHub repository.

        Uses PyGithub to authenticate and create the repository.

        Args:
            token: GitHub personal access token.
            repo_name: Name for the new repository.

        Returns:
            The created GitHub Repository object.

        Raises:
            github.GithubException: On API errors.
        """
        from github import Github

        g = Github(token)
        user = g.get_user()

        repo = user.create_repo(
            name=repo_name,
            description="Hackathon project generated by Hackathon Studio",
            private=False,
            auto_init=False,
        )
        return repo

    async def _push_structured_commits(self, repo, token: str) -> bool:
        """Push workspace contents as structured commits to the repository.

        Creates commits in the defined order: initial setup, backend,
        frontend, integration, docs, presentation. Each commit contains
        only files matching its designated paths.

        Args:
            repo: PyGithub Repository object.
            token: GitHub personal access token for API calls.

        Returns:
            True if all commits were pushed successfully.

        Raises:
            Exception: On GitHub API errors.
        """
        from github import Github, InputGitTreeElement, GithubException

        g = Github(token)

        # Collect all workspace files
        all_files = await self._collect_workspace_files()

        if not all_files:
            await self.log("Warning: No files found in workspace to push.")
            return True

        # Include generated .gitignore and LICENSE in the all_files dict
        all_files[".gitignore"] = GITIGNORE_CONTENT
        all_files["LICENSE"] = MIT_LICENSE_TEMPLATE.format(
            year=datetime.now(timezone.utc).year
        )

        # Track which files have been committed
        committed_files: set[str] = set()
        parent_sha: str | None = None

        for commit_info in COMMIT_STRUCTURE:
            commit_message = commit_info["message"]
            commit_paths = commit_info["paths"]

            # Collect files matching this commit's paths
            files_for_commit: dict[str, str] = {}
            for file_path, content in all_files.items():
                if file_path in committed_files:
                    continue
                if self._matches_commit_paths(file_path, commit_paths):
                    files_for_commit[file_path] = content
                    committed_files.add(file_path)

            if not files_for_commit:
                await self.log(
                    f"Skipping commit '{commit_message}': no matching files."
                )
                continue

            # Create tree elements for this commit
            tree_elements = []
            for file_path, content in files_for_commit.items():
                blob = repo.create_git_blob(content, "utf-8")
                tree_elements.append(
                    InputGitTreeElement(
                        path=file_path,
                        mode="100644",
                        type="blob",
                        sha=blob.sha,
                    )
                )

            # Create tree (with parent if not first commit)
            if parent_sha:
                parent_commit = repo.get_git_commit(parent_sha)
                base_tree = parent_commit.tree
                tree = repo.create_git_tree(tree_elements, base_tree)
                commit = repo.create_git_commit(
                    message=commit_message,
                    tree=tree,
                    parents=[parent_commit],
                )
            else:
                tree = repo.create_git_tree(tree_elements)
                commit = repo.create_git_commit(
                    message=commit_message,
                    tree=tree,
                    parents=[],
                )

            parent_sha = commit.sha
            await self.log(
                f"Created commit: '{commit_message}' "
                f"({len(files_for_commit)} files)"
            )

        # Handle remaining files not covered by any commit category
        remaining_files: dict[str, str] = {
            path: content
            for path, content in all_files.items()
            if path not in committed_files
        }

        if remaining_files and parent_sha:
            tree_elements = []
            for file_path, content in remaining_files.items():
                blob = repo.create_git_blob(content, "utf-8")
                tree_elements.append(
                    InputGitTreeElement(
                        path=file_path,
                        mode="100644",
                        type="blob",
                        sha=blob.sha,
                    )
                )

            parent_commit = repo.get_git_commit(parent_sha)
            base_tree = parent_commit.tree
            tree = repo.create_git_tree(tree_elements, base_tree)
            commit = repo.create_git_commit(
                message="Add remaining project files",
                tree=tree,
                parents=[parent_commit],
            )
            parent_sha = commit.sha
            await self.log(
                f"Created commit for remaining files ({len(remaining_files)} files)"
            )

        # Update the main branch reference to point to the last commit
        if parent_sha:
            try:
                ref = repo.get_git_ref("heads/main")
                ref.edit(parent_sha)
            except GithubException:
                # Branch may not exist yet, create it
                repo.create_git_ref(f"refs/heads/main", parent_sha)

            await self.log("Main branch updated with all commits.")

        return True

    def _configure_branch_protection(self, repo) -> bool:
        """Configure branch protection on the main branch.

        Requires at least 1 approval for pull requests.

        Args:
            repo: PyGithub Repository object.

        Returns:
            True if branch protection was configured successfully.

        Raises:
            github.GithubException: On API errors.
        """
        branch = repo.get_branch("main")
        branch.edit_protection(
            required_approving_review_count=1,
            enforce_admins=False,
            dismiss_stale_reviews=False,
            require_code_owner_reviews=False,
        )
        return True

    async def _collect_workspace_files(self) -> dict[str, str]:
        """Collect all text files from the workspace for pushing.

        Recursively reads all files from the workspace, skipping binary
        files and files that are too large for the GitHub API.

        Returns:
            Dictionary mapping relative file paths to content strings.
        """
        all_files: dict[str, str] = {}

        # Directories to scan (matching commit structure paths)
        directories_to_scan = [
            "backend/",
            "frontend/",
            "logs/",
            "docs/",
            "ppt/",
            "video/",
        ]

        # Top-level files to include
        top_level_files = [
            "README.md",
            "project_spec.md",
            "architecture.md",
            "roadmap.md",
            "judge_analysis.md",
            "testing_report.md",
            "developer_guide.md",
            "api_docs.md",
        ]

        # Read top-level files
        for file_path in top_level_files:
            try:
                if await self.workspace.file_exists(file_path):
                    content = await self.workspace.read_file(file_path)
                    all_files[file_path] = content
            except Exception as e:
                await self.log(f"Warning: Could not read '{file_path}': {e}")

        # Recursively read directory contents
        for directory in directories_to_scan:
            try:
                if await self.workspace.file_exists(directory):
                    dir_files = await self._read_directory_recursive(directory)
                    all_files.update(dir_files)
            except Exception as e:
                await self.log(
                    f"Warning: Could not scan directory '{directory}': {e}"
                )

        return all_files

    async def _read_directory_recursive(self, directory: str) -> dict[str, str]:
        """Recursively read all text files from a workspace directory.

        Skips binary files and files that cannot be decoded as UTF-8.

        Args:
            directory: Directory path relative to workspace root.

        Returns:
            Dictionary mapping relative file paths to content strings.
        """
        contents: dict[str, str] = {}

        # Text file extensions we can safely push to GitHub
        text_extensions = {
            ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".md",
            ".txt", ".css", ".yaml", ".yml", ".toml", ".cfg",
            ".ini", ".env", ".html", ".sh", ".bat", ".gitignore",
            ".eslintrc", ".prettierrc", ".lock",
        }

        try:
            files = await self.workspace.list_files(directory)
            for file_path in files:
                ext = "." + file_path.rsplit(".", 1)[-1] if "." in file_path else ""
                # Include files with known text extensions or no extension
                if ext.lower() in text_extensions or ext == "":
                    try:
                        content = await self.workspace.read_file(file_path)
                        # Skip files that are too large (>1MB) for GitHub API
                        if len(content.encode("utf-8")) <= 1_000_000:
                            contents[file_path] = content
                        else:
                            await self.log(
                                f"Skipping large file: '{file_path}' (>1MB)"
                            )
                    except (UnicodeDecodeError, Exception) as e:
                        await self.log(
                            f"Warning: Could not read '{file_path}': {e}"
                        )
        except (FileNotFoundError, NotADirectoryError):
            pass

        return contents

    def _matches_commit_paths(
        self, file_path: str, commit_paths: list[str]
    ) -> bool:
        """Check if a file path matches any of the commit's designated paths.

        Args:
            file_path: Relative file path to check.
            commit_paths: List of path prefixes or exact file names.

        Returns:
            True if the file matches any of the commit paths.
        """
        normalized = file_path.replace("\\", "/")

        for path_pattern in commit_paths:
            if path_pattern.endswith("/"):
                # Directory prefix match
                if normalized.startswith(path_pattern):
                    return True
            else:
                # Exact file match
                if normalized == path_pattern:
                    return True

        return False
