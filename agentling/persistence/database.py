"""SQLite database connection and migration management."""

import aiosqlite
import asyncio
from pathlib import Path
from typing import Optional

from .repositories import (
    SessionRepository, RunRepository, EventRepository, GitSnapshotRepository,
    AgentRepository, AgentRunRepository, AgentPatternRepository, SessionSnapshotRepository
)


class Database:
    """SQLite database manager with async support."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            # Default to user's home directory
            db_dir = Path.home() / ".agentling"
            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(db_dir / "agentling.db")

        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

        # Repositories
        self.sessions: Optional[SessionRepository] = None
        self.runs: Optional[RunRepository] = None
        self.events: Optional[EventRepository] = None
        self.git_snapshots: Optional[GitSnapshotRepository] = None
        self.agents: Optional[AgentRepository] = None
        self.agent_runs: Optional[AgentRunRepository] = None
        self.agent_patterns: Optional[AgentPatternRepository] = None
        self.session_snapshots: Optional[SessionSnapshotRepository] = None

    async def connect(self) -> None:
        """Connect to database and run migrations."""
        async with self._lock:
            if self._connection is not None:
                return

            self._connection = await aiosqlite.connect(self.db_path)
            self._connection.row_factory = aiosqlite.Row

            # Enable foreign keys
            await self._connection.execute("PRAGMA foreign_keys = ON")

            # Run migrations
            await self._run_migrations()

            # Initialize repositories
            self.sessions = SessionRepository(self._connection)
            self.runs = RunRepository(self._connection)
            self.events = EventRepository(self._connection)
            self.git_snapshots = GitSnapshotRepository(self._connection)
            self.agents = AgentRepository(self._connection)
            self.agent_runs = AgentRunRepository(self._connection)
            self.agent_patterns = AgentPatternRepository(self._connection)
            self.session_snapshots = SessionSnapshotRepository(self._connection)

    async def disconnect(self) -> None:
        """Close database connection."""
        async with self._lock:
            if self._connection:
                await self._connection.close()
                self._connection = None

    async def _run_migrations(self) -> None:
        """Run pending database migrations."""
        migrations_dir = Path(__file__).parent / "migrations"

        # Get current schema version
        try:
            cursor = await self._connection.execute(
                "SELECT MAX(version) FROM schema_migrations"
            )
            row = await cursor.fetchone()
            current_version = row[0] if row and row[0] else 0
        except aiosqlite.OperationalError:
            current_version = 0

        # Find and run pending migrations
        migration_files = sorted(migrations_dir.glob("*.sql"))

        for migration_file in migration_files:
            # Extract version from filename (e.g., 001_initial.sql -> 1)
            version = int(migration_file.stem.split("_")[0])

            if version > current_version:
                sql = migration_file.read_text()
                await self._connection.executescript(sql)
                await self._connection.commit()

    @property
    def connection(self) -> aiosqlite.Connection:
        """Get the database connection."""
        if self._connection is None:
            raise RuntimeError("Database not connected. Call connect() first.")
        return self._connection

    async def __aenter__(self) -> "Database":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.disconnect()
