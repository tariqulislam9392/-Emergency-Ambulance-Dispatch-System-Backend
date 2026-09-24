import datetime
from math import ceil

from fastapi import HTTPException
from sqlalchemy import case, or_
from sqlalchemy.orm import Session

from models import Ambulances, Emergencies


def search_filter(q: str, model, text_columns: list):
    """Naam / phone / address e partial match; q sudhu number hole ID-o match korbe."""
    q = q.strip()
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    conditions = [col.ilike(f"%{escaped}%", escape="\\") for col in text_columns]
    if q.isdigit():
        conditions.append(model.id == int(q))
    return or_(*conditions)


def apply_date_range(query, column, date_from: datetime.date | None, date_to: datetime.date | None):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="created_from must not be after created_to")
    if date_from:
        query = query.filter(column >= datetime.datetime.combine(date_from, datetime.time.min))
    if date_to:
        query = query.filter(column < datetime.datetime.combine(date_to + datetime.timedelta(days=1), datetime.time.min))
    return query


def apply_sort(query, model, sort_by: str, order: str):
    col = getattr(model, sort_by)
    primary = col.asc() if order == "asc" else col.desc()
    return query.order_by(primary, model.id.desc())  # id tie-breaker: page er order stable thake


def paginate(query, page: int, page_size: int) -> dict:
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": ceil(total / page_size) if total else 0,
    }


def clean_update(data: dict, nullable: tuple = ()) -> dict:
    """NOT NULL column e explicit null pathale ignore kore."""
    return {k: v for k, v in data.items() if v is not None or k in nullable}


PRIORITY_RANK = case(
    (Emergencies.priority == "critical", 4),
    (Emergencies.priority == "high", 3),
    (Emergencies.priority == "medium", 2),
    else_=1,
)

TRANSITIONS = {
    "pending": {"cancelled"},
    "dispatched": {"en_route", "completed", "cancelled"},
    "en_route": {"completed", "cancelled"},
}


def free_ambulance(db: Session, em: Emergencies):
    if em.ambulance_id:
        amb = db.query(Ambulances).filter(Ambulances.id == em.ambulance_id).first()
        if amb and amb.status == "dispatched":
            amb.status = "available"


def change_status(db: Session, em: Emergencies, new_status: str):
    if new_status not in TRANSITIONS.get(em.status, set()):
        raise HTTPException(status_code=409, detail=f"Cannot change status from '{em.status}' to '{new_status}'")
    em.status = new_status
    if new_status in ("completed", "cancelled"):
        em.completed_at = datetime.datetime.now()
        free_ambulance(db, em)


def emergency_list(db: Session, user_id, q, status, priority, ambulance_id, hospital_id,
                   created_from, created_to, sort_by, order, page, page_size) -> dict:
    """user_id dile shudhu oi user er request, None dile sob (admin)."""
    query = db.query(Emergencies)
    if user_id is not None:
        query = query.filter(Emergencies.requested_by == user_id)
    if q:
        query = query.filter(search_filter(q, Emergencies, [Emergencies.patient_name, Emergencies.patient_phone, Emergencies.address]))
    if status:
        query = query.filter(Emergencies.status == status)
    if priority:
        query = query.filter(Emergencies.priority == priority)
    if ambulance_id:
        query = query.filter(Emergencies.ambulance_id == ambulance_id)
    if hospital_id:
        query = query.filter(Emergencies.hospital_id == hospital_id)
    query = apply_date_range(query, Emergencies.created_at, created_from, created_to)

    if sort_by == "priority":  # alphabetical na, severity onujayi
        query = query.order_by(PRIORITY_RANK.asc() if order == "asc" else PRIORITY_RANK.desc(), Emergencies.id.desc())
    else:
        query = apply_sort(query, Emergencies, sort_by, order)
    return paginate(query, page, page_size)
