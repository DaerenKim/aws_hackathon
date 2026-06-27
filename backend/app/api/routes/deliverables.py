"""Deliverables API endpoints.

Provides endpoints for listing and serving generated artifacts from
the shared workspace directory.
"""

import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from app.api.deps import get_workspace_service
from app.services.workspace import WorkspaceService

router = APIRouter(prefix="/api/deliverables", tags=["deliverables"])

# Text-based file extensions served as plain text
TEXT_EXTENSIONS = {".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".csv", ".log"}


class FileInfo(BaseModel):
    """Metadata for a file in the workspace."""

    path: str
    size: int
    is_directory: bool = False


class DeliverablesList(BaseModel):
    """Response for listing all deliverable artifacts."""

    files: list[FileInfo]
    total_count: int


def _list_files_recursive(directory: Path, base: Path) -> list[FileInfo]:
    """Recursively list all files in a directory.

    Args:
        directory: The directory to list.
        base: The workspace root for computing relative paths.

    Returns:
        List of FileInfo for all files found.
    """
    files: list[FileInfo] = []
    if not directory.exists() or not directory.is_dir():
        return files

    for item in sorted(directory.rglob("*")):
        if item.is_file():
            relative_path = str(item.relative_to(base))
            files.append(
                FileInfo(
                    path=relative_path,
                    size=item.stat().st_size,
                )
            )
    return files


@router.get("", response_model=DeliverablesList)
async def list_deliverables(
    workspace: WorkspaceService = Depends(get_workspace_service),
) -> DeliverablesList:
    """List all artifacts in the workspace.

    Returns a recursive file listing of all generated deliverables
    available for download.
    """
    files = _list_files_recursive(workspace.workspace_root, workspace.workspace_root)
    return DeliverablesList(files=files, total_count=len(files))


@router.get("/{path:path}", response_model=None)
async def get_deliverable(
    path: str,
    workspace: WorkspaceService = Depends(get_workspace_service),
) -> FileResponse | PlainTextResponse:
    """Serve a specific artifact file from the workspace.

    For text files (.md, .txt, .json), returns plain text content.
    For binary files (.pptx, .mp4, .pdf, etc.), returns a FileResponse
    for direct download.

    Args:
        path: Relative file path within the workspace.

    Returns:
        FileResponse for binary files, PlainTextResponse for text files.

    Raises:
        HTTPException: 404 if file not found, 400 if path traversal detected.
    """
    # Validate path — prevent traversal
    try:
        resolved = workspace._resolve_path(path)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid path: path traversal not allowed",
        )

    if not resolved.exists():
        raise HTTPException(
            status_code=404,
            detail=f"File not found: {path}",
        )

    if resolved.is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"Path is a directory, not a file: {path}",
        )

    # Determine how to serve the file based on extension
    suffix = resolved.suffix.lower()

    if suffix in TEXT_EXTENSIONS:
        # Serve text files as plain text
        content = resolved.read_text(encoding="utf-8")
        media_type = "text/plain"
        if suffix == ".json":
            media_type = "application/json"
        elif suffix == ".md":
            media_type = "text/markdown"
        elif suffix in (".yaml", ".yml"):
            media_type = "text/yaml"
        return PlainTextResponse(content=content, media_type=media_type)

    # Serve binary files with appropriate content type
    content_type, _ = mimetypes.guess_type(str(resolved))
    if content_type is None:
        content_type = "application/octet-stream"

    return FileResponse(
        path=resolved,
        media_type=content_type,
        filename=resolved.name,
    )
