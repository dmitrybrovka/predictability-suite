"""SQLite store via SQLAlchemy 2."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    create_engine,
    delete,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from predictability.core.errors import NoActiveModelError, UsageError
from predictability.core.schema import (
    DEFAULT_MIN_HISTORY,
    ChildIssue,
    Dependency,
    Epic,
    IngestReport,
    ModelArtifact,
    SlipUnit,
)

DEFAULT_DB = Path("predictability.sqlite")

# (table, column, DDL) for columns introduced after the first release.
_ADDED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("artifacts", "min_history", "min_history INTEGER"),
)


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for store tables."""


class EpicRow(Base):
    """ORM row for a canonical epic. Primary key is ``(tracker, external_id)``."""

    __tablename__ = "epics"
    tracker: Mapped[str] = mapped_column(String, primary_key=True)
    external_id: Mapped[str] = mapped_column(String, primary_key=True)
    team_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    committed_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline_source: Mapped[str | None] = mapped_column(String)
    actual_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    title: Mapped[str | None] = mapped_column(String)
    estimate: Mapped[float | None] = mapped_column(Float)
    labels_json: Mapped[str] = mapped_column(Text, default="[]")
    raw_payload_hash: Mapped[str | None] = mapped_column(String)


class ChildRow(Base):
    """ORM row for a child issue used as a factor input."""

    __tablename__ = "children"
    tracker: Mapped[str] = mapped_column(String, primary_key=True)
    external_id: Mapped[str] = mapped_column(String, primary_key=True)
    epic_external_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    team_id: Mapped[str | None] = mapped_column(String)
    estimate: Mapped[float | None] = mapped_column(Float)
    actual_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DepRow(Base):
    """ORM row for a directed dependency link."""

    __tablename__ = "dependencies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tracker: Mapped[str] = mapped_column(String, nullable=False)
    from_external_id: Mapped[str] = mapped_column(String, nullable=False)
    to_external_id: Mapped[str] = mapped_column(String, nullable=False)
    from_kind: Mapped[str] = mapped_column(String, nullable=False)
    link_type: Mapped[str] = mapped_column(String, default="blocks")
    to_team_id: Mapped[str | None] = mapped_column(String)


class ArtifactRow(Base):
    """ORM row for a trained model artifact. At most one ``is_active``."""

    __tablename__ = "artifacts"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    backend: Mapped[str] = mapped_column(String, nullable=False)
    backend_version: Mapped[str] = mapped_column(String, nullable=False)
    factor_set_hash: Mapped[str] = mapped_column(String, nullable=False)
    quantiles_json: Mapped[str] = mapped_column(Text, nullable=False)
    slip_unit: Mapped[str] = mapped_column(String, nullable=False)
    train_epic_count: Mapped[int] = mapped_column(Integer, nullable=False)
    train_team_count: Mapped[int] = mapped_column(Integer, nullable=False)
    data_cutoff: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    blob_path: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Nullable so databases written before this column keep opening; rows from
    # then predate the pinned threshold and fall back to the default.
    min_history: Mapped[int | None] = mapped_column(Integer)


def _dt(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _epic_from_row(row: EpicRow) -> Epic:
    labels: list[str] = json.loads(row.labels_json)
    return Epic(
        tracker=row.tracker,
        external_id=row.external_id,
        team_id=row.team_id,
        status=row.status,
        committed_deadline=_dt(row.committed_deadline),
        deadline_source=row.deadline_source,
        actual_completed_at=_dt(row.actual_completed_at),
        created_at=_dt(row.created_at) or datetime.now(UTC),
        updated_at=_dt(row.updated_at) or datetime.now(UTC),
        title=row.title,
        estimate=row.estimate,
        labels=labels,
        raw_payload_hash=row.raw_payload_hash,
    )


class Store:
    """SQLite persistence for epics, children, dependencies, and model artifacts."""

    def __init__(self, path: Path | str | None = None) -> None:
        """Open or create ``path`` (default ``./predictability.sqlite``)."""
        self.path = Path(path) if path is not None else DEFAULT_DB
        self.engine: Engine = create_engine(f"sqlite:///{self.path}", future=True)
        Base.metadata.create_all(self.engine)
        self._add_missing_columns()
        self._session = sessionmaker(self.engine, expire_on_commit=False)

    def _add_missing_columns(self) -> None:
        """Patch columns added after the database was first created.

        ``create_all`` only creates missing tables, so new columns have to be
        added explicitly.
        """
        with self.engine.begin() as conn:
            for table, column, ddl in _ADDED_COLUMNS:
                rows = conn.exec_driver_sql(f"PRAGMA table_info({table})").fetchall()
                if column not in {row[1] for row in rows}:
                    conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {ddl}")

    def session(self) -> Session:
        """Return a new SQLAlchemy session."""
        return self._session()

    def upsert_epics(self, epics: list[Epic]) -> IngestReport:
        """Insert or update epics on ``(tracker, external_id)``.

        Returns:
            Counts of imported vs updated rows.
        """
        report = IngestReport()
        with self.session() as session:
            for epic in epics:
                existing = session.get(EpicRow, (epic.tracker, epic.external_id))
                payload = {
                    "team_id": epic.team_id,
                    "status": epic.status,
                    "committed_deadline": _dt(epic.committed_deadline),
                    "deadline_source": epic.deadline_source,
                    "actual_completed_at": _dt(epic.actual_completed_at),
                    "created_at": _dt(epic.created_at),
                    "updated_at": _dt(epic.updated_at),
                    "title": epic.title,
                    "estimate": epic.estimate,
                    "labels_json": json.dumps(epic.labels),
                    "raw_payload_hash": epic.raw_payload_hash,
                }
                if existing is None:
                    session.add(
                        EpicRow(tracker=epic.tracker, external_id=epic.external_id, **payload)
                    )
                    report.imported += 1
                else:
                    for key, value in payload.items():
                        setattr(existing, key, value)
                    report.updated += 1
            session.commit()
        return report

    def upsert_children(self, children: list[ChildIssue]) -> int:
        """Insert new children; update existing ones. Returns new-row count."""
        n = 0
        with self.session() as session:
            for child in children:
                existing = session.get(ChildRow, (child.tracker, child.external_id))
                payload = {
                    "epic_external_id": child.epic_external_id,
                    "status": child.status,
                    "updated_at": _dt(child.updated_at),
                    "team_id": child.team_id,
                    "estimate": child.estimate,
                    "actual_completed_at": _dt(child.actual_completed_at),
                }
                if existing is None:
                    session.add(
                        ChildRow(tracker=child.tracker, external_id=child.external_id, **payload)
                    )
                    n += 1
                else:
                    for key, value in payload.items():
                        setattr(existing, key, value)
            session.commit()
        return n

    def replace_dependencies(self, tracker: str | Iterable[str], deps: list[Dependency]) -> None:
        """Replace all dependency rows for the given tracker name(s)."""
        # Adapter name, adapter.id, and the tracker on each row can all differ.
        # Union them so re-ingest neither duplicates nor leaves stale links.
        names = {tracker} if isinstance(tracker, str) else set(tracker)
        names.update(dep.tracker for dep in deps)
        names.discard("")
        with self.session() as session:
            if names:
                session.execute(delete(DepRow).where(DepRow.tracker.in_(sorted(names))))
            for dep in deps:
                session.add(
                    DepRow(
                        tracker=dep.tracker,
                        from_external_id=dep.from_external_id,
                        to_external_id=dep.to_external_id,
                        from_kind=dep.from_kind,
                        link_type=dep.link_type,
                        to_team_id=dep.to_team_id,
                    )
                )
            session.commit()

    def list_epics(self, *, status: str | None = None) -> list[Epic]:
        """Return stored epics, optionally filtered by ``status``."""
        with self.session() as session:
            stmt = select(EpicRow)
            if status is not None:
                stmt = stmt.where(EpicRow.status == status)
            rows = session.scalars(stmt).all()
            return [_epic_from_row(r) for r in rows]

    def list_completed_epics(self) -> list[Epic]:
        """Return done epics that have both a deadline and an actual completion."""
        return [
            e
            for e in self.list_epics(status="done")
            if e.actual_completed_at is not None and e.committed_deadline is not None
        ]

    def list_children(self) -> list[ChildIssue]:
        """Return all stored child issues."""
        with self.session() as session:
            rows = session.scalars(select(ChildRow)).all()
            return [
                ChildIssue(
                    tracker=r.tracker,
                    external_id=r.external_id,
                    epic_external_id=r.epic_external_id,
                    status=r.status,
                    updated_at=_dt(r.updated_at) or datetime.now(UTC),
                    team_id=r.team_id,
                    estimate=r.estimate,
                    actual_completed_at=_dt(r.actual_completed_at),
                )
                for r in rows
            ]

    def list_dependencies(self) -> list[Dependency]:
        """Return all stored dependency links."""
        with self.session() as session:
            rows = session.scalars(select(DepRow)).all()
            return [
                Dependency(
                    tracker=r.tracker,
                    from_external_id=r.from_external_id,
                    to_external_id=r.to_external_id,
                    from_kind=r.from_kind,
                    link_type=r.link_type,
                    to_team_id=r.to_team_id,
                )
                for r in rows
            ]

    def artifact_dir(self) -> Path:
        """Directory next to the DB file where serialized models are stored."""
        d = self.path.parent / f"{self.path.stem}_artifacts"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save_artifact(
        self,
        *,
        backend: str,
        backend_version: str,
        factor_set_hash: str,
        quantiles: list[float],
        slip_unit: SlipUnit,
        train_epic_count: int,
        train_team_count: int,
        data_cutoff: datetime | None,
        blob_path: str,
        activate: bool,
        min_history: int = DEFAULT_MIN_HISTORY,
    ) -> ModelArtifact:
        """Persist artifact metadata. If ``activate``, clear any previous active row."""
        art_id = uuid4()
        created = datetime.now(UTC)
        with self.session() as session:
            if activate:
                for row in session.scalars(
                    select(ArtifactRow).where(ArtifactRow.is_active.is_(True))
                ):
                    row.is_active = False
            session.add(
                ArtifactRow(
                    id=str(art_id),
                    backend=backend,
                    backend_version=backend_version,
                    factor_set_hash=factor_set_hash,
                    quantiles_json=json.dumps(quantiles),
                    slip_unit=slip_unit,
                    train_epic_count=train_epic_count,
                    train_team_count=train_team_count,
                    data_cutoff=_dt(data_cutoff),
                    created_at=created,
                    blob_path=blob_path,
                    is_active=activate,
                    min_history=min_history,
                )
            )
            session.commit()
        return ModelArtifact(
            id=art_id,
            backend=backend,
            backend_version=backend_version,
            factor_set_hash=factor_set_hash,
            quantiles=quantiles,
            slip_unit=slip_unit,
            train_epic_count=train_epic_count,
            train_team_count=train_team_count,
            data_cutoff=data_cutoff,
            created_at=created,
            blob_path=blob_path,
            is_active=activate,
            min_history=min_history,
        )

    def get_artifact(self, model_id: UUID | str | None = None) -> ModelArtifact:
        """Load the active artifact, or the one identified by ``model_id``.

        Raises:
            NoActiveModelError: No active artifact and ``model_id`` is omitted.
            UsageError: ``model_id`` is unknown.
        """
        with self.session() as session:
            if model_id is None:
                row = session.scalars(
                    select(ArtifactRow).where(ArtifactRow.is_active.is_(True))
                ).first()
                if row is None:
                    raise NoActiveModelError("no active model artifact; run train first")
            else:
                row = session.get(ArtifactRow, str(model_id))
                if row is None:
                    msg = f"unknown model id {model_id}"
                    raise UsageError(msg)
            return ModelArtifact(
                id=UUID(row.id),
                backend=row.backend,
                backend_version=row.backend_version,
                factor_set_hash=row.factor_set_hash,
                quantiles=json.loads(row.quantiles_json),
                slip_unit=row.slip_unit,
                train_epic_count=row.train_epic_count,
                train_team_count=row.train_team_count,
                data_cutoff=_dt(row.data_cutoff),
                created_at=_dt(row.created_at) or datetime.now(UTC),
                blob_path=row.blob_path,
                is_active=row.is_active,
                min_history=(
                    row.min_history if row.min_history is not None else DEFAULT_MIN_HISTORY
                ),
            )

    def active_id(self) -> str | None:
        """Return the active artifact id, or ``None`` if none is active."""
        with self.session() as session:
            row = session.scalars(
                select(ArtifactRow).where(ArtifactRow.is_active.is_(True))
            ).first()
            return None if row is None else row.id

    def train_row_count(self) -> int:
        """Number of completed epics eligible for training."""
        return len(self.list_completed_epics())

    def close(self) -> None:
        """Dispose the SQLAlchemy engine."""
        self.engine.dispose()
