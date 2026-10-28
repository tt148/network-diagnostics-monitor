"""SQLAlchemy persistence models for devices, metrics, and incidents."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """Base class for all persisted entities."""


class Device(Base):
    """A monitored fictional or explicitly configured network device."""

    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    device_type: Mapped[str] = mapped_column(String(50))
    hostname: Mapped[str] = mapped_column(String(255), unique=True)
    location: Mapped[str] = mapped_column(String(100), default="Simulated lab")
    description: Mapped[str] = mapped_column(Text, default="")
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    metrics: Mapped[list[Metric]] = relationship(back_populates="device", cascade="all, delete-orphan")
    incidents: Mapped[list[Incident]] = relationship(back_populates="device")


class Metric(Base):
    """A timestamped monitoring measurement."""

    __tablename__ = "metrics"
    __table_args__ = (Index("ix_metrics_device_name_time", "device_id", "name", "recorded_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(50), index=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(20), default="")
    status: Mapped[str] = mapped_column(String(20), default="ok")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[str] = mapped_column(String(30), default="simulation")
    details: Mapped[str] = mapped_column(Text, default="")

    device: Mapped[Device] = relationship(back_populates="metrics")


class Incident(Base):
    """An alert lifecycle record, deduplicated while active."""

    __tablename__ = "incidents"
    __table_args__ = (
        Index("ix_incidents_status_severity", "status", "severity"),
        Index("ix_incidents_device_kind", "device_id", "kind"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)
    kind: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(20), default="warning")
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    is_flapping: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    device: Mapped[Device] = relationship(back_populates="incidents")
