"""Git repository state tracker for file change visualization."""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..events.types import Event, EventType, GitSnapshotEvent


@dataclass
class GitState:
    """Represents the current state of a git repository."""
    commit_hash: str = ""
    branch: str = ""
    dirty_files: list[str] = field(default_factory=list)
    staged_files: list[str] = field(default_factory=list)
    untracked_files: list[str] = field(default_factory=list)
    diff_stat: str = ""
    is_git_repo: bool = True


@dataclass
class FileChange:
    """Represents a single file change."""
    path: str
    change_type: str  # added, modified, deleted, renamed
    lines_added: int = 0
    lines_removed: int = 0
    old_path: Optional[str] = None  # For renames


class GitTracker:
    """Tracks git state changes during Claude Code execution."""

    def __init__(self, working_dir: str, session_id: str, run_id: str):
        self.working_dir = Path(working_dir).resolve()
        self.session_id = session_id
        self.run_id = run_id
        self._last_state: Optional[GitState] = None
        self._is_git_repo: Optional[bool] = None

    async def is_git_repo(self) -> bool:
        """Check if the working directory is a git repository."""
        if self._is_git_repo is not None:
            return self._is_git_repo

        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "rev-parse", "--git-dir",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir)
            )
            await proc.wait()
            self._is_git_repo = proc.returncode == 0
        except FileNotFoundError:
            self._is_git_repo = False

        return self._is_git_repo

    async def snapshot(self) -> GitSnapshotEvent:
        """Capture current git state and return as event."""
        state = await self._get_state()

        diff_stat = ""
        if self._last_state and state.is_git_repo:
            diff_stat = await self._get_diff_stat()

        self._last_state = state

        return GitSnapshotEvent(
            type=EventType.GIT_SNAPSHOT,
            session_id=self.session_id,
            run_id=self.run_id,
            commit_hash=state.commit_hash,
            branch=state.branch,
            dirty_files=state.dirty_files + state.untracked_files,
            staged_files=state.staged_files,
            diff_stat=diff_stat,
            payload={
                "untracked_files": state.untracked_files,
                "is_git_repo": state.is_git_repo
            }
        )

    async def get_file_changes(self) -> list[FileChange]:
        """Get detailed file changes since last snapshot."""
        if not await self.is_git_repo():
            return []

        changes = []

        # Get diff with stats
        diff_output = await self._run_git("diff", "--numstat")

        for line in diff_output.strip().split("\n"):
            if not line:
                continue

            parts = line.split("\t")
            if len(parts) >= 3:
                added = int(parts[0]) if parts[0] != "-" else 0
                removed = int(parts[1]) if parts[1] != "-" else 0
                filepath = parts[2]

                changes.append(FileChange(
                    path=filepath,
                    change_type="modified",
                    lines_added=added,
                    lines_removed=removed
                ))

        # Get untracked files
        untracked = await self._run_git("ls-files", "--others", "--exclude-standard")
        for filepath in untracked.strip().split("\n"):
            if filepath:
                changes.append(FileChange(
                    path=filepath,
                    change_type="added"
                ))

        return changes

    async def get_file_diff(self, filepath: str) -> str:
        """Get unified diff for a specific file."""
        if not await self.is_git_repo():
            return ""

        return await self._run_git("diff", "--", filepath)

    async def _get_state(self) -> GitState:
        """Get current git repository state."""
        if not await self.is_git_repo():
            return GitState(is_git_repo=False)

        # Run git commands in parallel
        results = await asyncio.gather(
            self._run_git("rev-parse", "HEAD"),
            self._run_git("rev-parse", "--abbrev-ref", "HEAD"),
            self._run_git("status", "--porcelain"),
            self._run_git("diff", "--stat"),
            return_exceptions=True
        )

        commit_hash = results[0] if isinstance(results[0], str) else ""
        branch = results[1] if isinstance(results[1], str) else ""
        status = results[2] if isinstance(results[2], str) else ""
        diff_stat = results[3] if isinstance(results[3], str) else ""

        # Parse status output
        dirty = []
        staged = []
        untracked = []

        for line in status.strip().split("\n"):
            if not line:
                continue

            status_code = line[:2]
            filepath = line[3:]

            # Index status (staged)
            if status_code[0] not in (" ", "?"):
                staged.append(filepath)

            # Working tree status (dirty)
            if status_code[1] not in (" ", "?"):
                dirty.append(filepath)

            # Untracked
            if status_code == "??":
                untracked.append(filepath)

        return GitState(
            commit_hash=commit_hash.strip(),
            branch=branch.strip(),
            dirty_files=dirty,
            staged_files=staged,
            untracked_files=untracked,
            diff_stat=diff_stat.strip(),
            is_git_repo=True
        )

    async def _get_diff_stat(self) -> str:
        """Get diff stat summary."""
        return await self._run_git("diff", "--stat")

    async def _run_git(self, *args: str) -> str:
        """Run a git command and return output."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.working_dir)
            )
            stdout, _ = await proc.communicate()
            return stdout.decode("utf-8", errors="replace").strip()
        except Exception:
            return ""

    async def create_checkpoint(self, message: str = "agentling checkpoint") -> Optional[str]:
        """Create a git stash or commit as a checkpoint."""
        if not await self.is_git_repo():
            return None

        # Stash current changes
        result = await self._run_git("stash", "push", "-m", message)
        if "No local changes" in result:
            return None

        return result

    async def restore_checkpoint(self) -> bool:
        """Restore the last checkpoint."""
        if not await self.is_git_repo():
            return False

        result = await self._run_git("stash", "pop")
        return "error" not in result.lower()
