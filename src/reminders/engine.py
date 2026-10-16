"""Medicine reminders (CLAUDE.md section 9).

- Every active Medication has daily DoseEvents at its `times` (local time, settings.timezone).
- The patient app shows doses that are due now; the patient taps Taken or Skip.
- A dose still pending 2 hours after its time becomes `missed`.
- Adherence % (7 and 30 days) = taken / (taken + skipped + missed); it feeds the twin and alerts.
- SMS / WhatsApp are out of scope: `Notifier` is a stub interface that only logs.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from config.settings import get_settings
from src.db.models import DoseEvent, Medication

log = logging.getLogger("glycorenal.reminders")
MISSED_AFTER = timedelta(hours=2)
DUE_WINDOW_BEFORE = timedelta(minutes=30)   # show a dose as "due" from 30 min before its time


class Notifier:
    """Stub for SMS / WhatsApp reminders (out of scope for the prototype)."""

    def send(self, patient_id: str, message: str) -> None:
        log.info("[reminder stub] to %s: %s", patient_id, message)


def _tz() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def _active(m: Medication, day: date) -> bool:
    return (m.start_date is None or m.start_date <= day) and (m.end_date is None or m.end_date >= day)


def ensure_dose_events(session: Session, days_ahead: int = 1, patient_id: str | None = None) -> int:
    """Create DoseEvents for today (and `days_ahead` more days) that don't exist yet."""
    tz = _tz()
    today = datetime.now(tz).date()
    q = select(Medication)
    if patient_id:
        q = q.where(Medication.patient_id == patient_id)
    created = 0
    for m in session.exec(q).all():
        for d in range(days_ahead + 1):
            day = today + timedelta(days=d)
            if not _active(m, day):
                continue
            for hhmm in m.times or []:
                h, mi = map(int, hhmm.split(":"))
                t = datetime.combine(day, time(h, mi), tzinfo=tz).astimezone(timezone.utc)
                exists = session.exec(select(DoseEvent.id).where(DoseEvent.medication_id == m.id,
                                                                 DoseEvent.scheduled_time == t)).first()
                if not exists:
                    session.add(DoseEvent(medication_id=m.id, scheduled_time=t))
                    created += 1
    session.commit()
    return created


def reschedule(session: Session, med: Medication) -> None:
    """After a prescription change: drop this medicine's future pending doses and recreate them."""
    now = datetime.now(timezone.utc)
    for e in session.exec(select(DoseEvent).where(DoseEvent.medication_id == med.id,
                                                  DoseEvent.status == "pending",
                                                  DoseEvent.scheduled_time > now)).all():
        session.delete(e)
    session.commit()
    ensure_dose_events(session, patient_id=med.patient_id)


def mark_missed(session: Session, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    late = session.exec(select(DoseEvent).where(DoseEvent.status == "pending",
                                                DoseEvent.scheduled_time < now - MISSED_AFTER)).all()
    for e in late:
        e.status = "missed"
        session.add(e)
    session.commit()
    return len(late)


def _event_dict(e: DoseEvent, m: Medication) -> dict:
    local = e.scheduled_time.astimezone(_tz())
    return {"id": e.id, "medication_id": m.id, "drug": m.drug, "dose": m.dose, "with_food": m.with_food,
            "scheduled_time": e.scheduled_time.isoformat(), "local_time": local.strftime("%H:%M"),
            "local_date": local.date().isoformat(), "status": e.status,
            "responded_at": e.responded_at.isoformat() if e.responded_at else None}


def doses(session: Session, patient_id: str, day: date | None = None) -> list[dict]:
    """All doses on a local day (default today) for a patient."""
    tz = _tz()
    day = day or datetime.now(tz).date()
    start = datetime.combine(day, time(0, 0), tzinfo=tz).astimezone(timezone.utc)
    rows = session.exec(select(DoseEvent, Medication).join(Medication)
                        .where(Medication.patient_id == patient_id,
                               DoseEvent.scheduled_time >= start,
                               DoseEvent.scheduled_time < start + timedelta(days=1))
                        .order_by(DoseEvent.scheduled_time)).all()
    return [_event_dict(e, m) for e, m in rows]


def due_now(session: Session, patient_id: str, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    rows = session.exec(select(DoseEvent, Medication).join(Medication)
                        .where(Medication.patient_id == patient_id, DoseEvent.status == "pending",
                               DoseEvent.scheduled_time <= now + DUE_WINDOW_BEFORE,
                               DoseEvent.scheduled_time >= now - MISSED_AFTER)
                        .order_by(DoseEvent.scheduled_time)).all()
    return [_event_dict(e, m) for e, m in rows]


def next_dose(session: Session, patient_id: str, now: datetime | None = None) -> dict | None:
    now = now or datetime.now(timezone.utc)
    row = session.exec(select(DoseEvent, Medication).join(Medication)
                       .where(Medication.patient_id == patient_id, DoseEvent.status == "pending",
                              DoseEvent.scheduled_time >= now - MISSED_AFTER)
                       .order_by(DoseEvent.scheduled_time)).first()
    return _event_dict(*row) if row else None


def respond(session: Session, event_id: int, status: str) -> DoseEvent:
    if status not in ("taken", "skipped"):
        raise ValueError("status must be 'taken' or 'skipped'")
    e = session.get(DoseEvent, event_id)
    if e is None:
        raise LookupError(event_id)
    e.status, e.responded_at = status, datetime.now(timezone.utc)
    session.add(e)
    session.commit()
    return e


def adherence(session: Session, patient_id: str, days: int, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    rows = session.exec(select(DoseEvent.status).join(Medication)
                        .where(Medication.patient_id == patient_id, DoseEvent.status != "pending",
                               DoseEvent.scheduled_time > now - timedelta(days=days),
                               DoseEvent.scheduled_time <= now)).all()
    counts = {s: rows.count(s) for s in ("taken", "skipped", "missed")}
    total = sum(counts.values())
    return {"days": days, "pct": round(100 * counts["taken"] / total, 1) if total else None, **counts}
