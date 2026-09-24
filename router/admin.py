import datetime
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, update
from sqlalchemy.orm import Session
from typing import Annotated

from database import get_db
from models import Ambulances, Emergencies, Hospitals, PasswordResets, RefreshTokens, Users
from router.auth import admin_dependency, get_admin_user, hash_password
from schemas import (AmbulanceCreate, AmbulanceOut, AmbulanceUpdate, DispatchRequest, EmergencyOut,
                     EmergencyUpdate, HospitalCreate, HospitalOut, HospitalUpdate, Page, StatusUpdate,
                     UserCreate, UserOut, UserUpdate)
from utils import (apply_date_range, apply_sort, change_status, clean_update, emergency_list,
                   free_ambulance, paginate, search_filter)

router = APIRouter(prefix='/admin', tags=['admin'], dependencies=[Depends(get_admin_user)])

db_dependency = Annotated[Session, Depends(get_db)]
Order = Literal['asc', 'desc']

@router.get('/users', response_model=Page[UserOut])
def list_users(db: db_dependency,
               q: str | None = Query(None, description='name / email / username / phone / ID'),
               role: Literal['admin', 'user'] | None = None,
               is_active: bool | None = None,
               created_from: date | None = None, created_to: date | None = None,
               sort_by: Literal['created_at', 'firstname', 'email', 'username'] = 'created_at',
               order: Order = 'desc',
               page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100)):
    query = db.query(Users)
    if q:
        query = query.filter(search_filter(q, Users, [Users.firstname, Users.lastname, Users.email, Users.username, Users.phone]))
    if role:
        query = query.filter(Users.role == role)
    if is_active is not None:
        query = query.filter(Users.is_active == is_active)
    query = apply_date_range(query, Users.created_at, created_from, created_to)
    return paginate(apply_sort(query, Users, sort_by, order), page, page_size)


@router.post('/users', response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, db: db_dependency):
    if db.query(Users).filter((Users.email == body.email.lower()) | (Users.username == body.username)).first():
        raise HTTPException(status_code=409, detail='Email or username already registered')
    user = Users(email=body.email.lower(), username=body.username, firstname=body.firstname, lastname=body.lastname,
                 phone=body.phone, hash_password=hash_password(body.password), role=body.role)
    db.add(user)
    db.commit()
    return user


@router.get('/users/{user_id}', response_model=UserOut)
def get_user(db: db_dependency, user_id: int):
    user = db.query(Users).filter(Users.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail='User not found')
    return user


@router.put('/users/{user_id}', response_model=UserOut)
def update_user(admin: admin_dependency, db: db_dependency, user_id: int, body: UserUpdate):
    user = db.query(Users).filter(Users.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail='User not found')
    data = clean_update(body.model_dump(exclude_unset=True), nullable=('phone',))
    if user.id == admin['id'] and (data.get('role') == 'user' or data.get('is_active') is False):
        raise HTTPException(status_code=400, detail='You cannot demote or deactivate your own account')
    for key, value in data.items():
        setattr(user, key, value)
    db.commit()
    return user


@router.delete('/users/{user_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_user(admin: admin_dependency, db: db_dependency, user_id: int):
    user = db.query(Users).filter(Users.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail='User not found')
    if user.id == admin['id']:
        raise HTTPException(status_code=400, detail='You cannot delete your own account')
    # emergency history thakuk, shudhu requester ta null hobe
    db.execute(update(Emergencies).where(Emergencies.requested_by == user.id).values(requested_by=None))
    db.execute(delete(RefreshTokens).where(RefreshTokens.user_id == user.id))
    db.execute(delete(PasswordResets).where(PasswordResets.user_id == user.id))
    db.delete(user)
    db.commit()


@router.get('/ambulances', response_model=Page[AmbulanceOut])
def list_ambulances(db: db_dependency,
                    q: str | None = Query(None, description='plate / driver name / driver phone / ID'),
                    status_: Literal['available', 'dispatched', 'maintenance'] | None = Query(None, alias='status'),
                    type: Literal['basic', 'advanced', 'icu'] | None = None,
                    created_from: date | None = None, created_to: date | None = None,
                    sort_by: Literal['created_at', 'plate_number', 'driver_name', 'status', 'type'] = 'created_at',
                    order: Order = 'desc',
                    page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100)):
    query = db.query(Ambulances)
    if q:
        query = query.filter(search_filter(q, Ambulances, [Ambulances.plate_number, Ambulances.driver_name, Ambulances.driver_phone]))
    if status_:
        query = query.filter(Ambulances.status == status_)
    if type:
        query = query.filter(Ambulances.type == type)
    query = apply_date_range(query, Ambulances.created_at, created_from, created_to)
    return paginate(apply_sort(query, Ambulances, sort_by, order), page, page_size)


@router.post('/ambulances', response_model=AmbulanceOut, status_code=status.HTTP_201_CREATED)
def create_ambulance(db: db_dependency, body: AmbulanceCreate):
    if db.query(Ambulances).filter(Ambulances.plate_number == body.plate_number).first():
        raise HTTPException(status_code=409, detail='An ambulance with this plate number already exists')
    ambulance = Ambulances(**body.model_dump())
    db.add(ambulance)
    db.commit()
    return ambulance


@router.get('/ambulances/{ambulance_id}', response_model=AmbulanceOut)
def get_ambulance(db: db_dependency, ambulance_id: int):
    ambulance = db.query(Ambulances).filter(Ambulances.id == ambulance_id).first()
    if ambulance is None:
        raise HTTPException(status_code=404, detail='Ambulance not found')
    return ambulance


@router.put('/ambulances/{ambulance_id}', response_model=AmbulanceOut)
def update_ambulance(db: db_dependency, ambulance_id: int, body: AmbulanceUpdate):
    ambulance = db.query(Ambulances).filter(Ambulances.id == ambulance_id).first()
    if ambulance is None:
        raise HTTPException(status_code=404, detail='Ambulance not found')
    data = clean_update(body.model_dump(exclude_unset=True), nullable=('latitude', 'longitude'))
    plate = data.get('plate_number')
    if plate and db.query(Ambulances).filter(Ambulances.plate_number == plate, Ambulances.id != ambulance.id).first():
        raise HTTPException(status_code=409, detail='An ambulance with this plate number already exists')
    new_status = data.get('status')
    if ambulance.status == 'dispatched' and new_status in ('available', 'maintenance'):
        raise HTTPException(status_code=409, detail='Ambulance is on an active emergency; complete or cancel it first')
    if new_status == 'dispatched' and ambulance.status != 'dispatched':
        raise HTTPException(status_code=409, detail='Use POST /admin/emergencies/{id}/dispatch to dispatch an ambulance')
    for key, value in data.items():
        setattr(ambulance, key, value)
    db.commit()
    return ambulance


@router.delete('/ambulances/{ambulance_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_ambulance(db: db_dependency, ambulance_id: int):
    ambulance = db.query(Ambulances).filter(Ambulances.id == ambulance_id).first()
    if ambulance is None:
        raise HTTPException(status_code=404, detail='Ambulance not found')
    if ambulance.status == 'dispatched':
        raise HTTPException(status_code=409, detail='Ambulance is on an active emergency; complete or cancel it first')
    db.execute(update(Emergencies).where(Emergencies.ambulance_id == ambulance.id).values(ambulance_id=None))
    db.delete(ambulance)
    db.commit()


@router.post('/hospitals', response_model=HospitalOut, status_code=status.HTTP_201_CREATED)
def create_hospital(db: db_dependency, body: HospitalCreate):
    hospital = Hospitals(**body.model_dump())
    db.add(hospital)
    db.commit()
    return hospital


@router.put('/hospitals/{hospital_id}', response_model=HospitalOut)
def update_hospital(db: db_dependency, hospital_id: int, body: HospitalUpdate):
    hospital = db.query(Hospitals).filter(Hospitals.id == hospital_id).first()
    if hospital is None:
        raise HTTPException(status_code=404, detail='Hospital not found')
    for key, value in clean_update(body.model_dump(exclude_unset=True)).items():
        setattr(hospital, key, value)
    db.commit()
    return hospital


@router.delete('/hospitals/{hospital_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_hospital(db: db_dependency, hospital_id: int):
    hospital = db.query(Hospitals).filter(Hospitals.id == hospital_id).first()
    if hospital is None:
        raise HTTPException(status_code=404, detail='Hospital not found')
    db.execute(update(Emergencies).where(Emergencies.hospital_id == hospital.id).values(hospital_id=None))
    db.delete(hospital)
    db.commit()


def _get_emergency(db: Session, emergency_id: int) -> Emergencies:
    em = db.query(Emergencies).filter(Emergencies.id == emergency_id).first()
    if em is None:
        raise HTTPException(status_code=404, detail='Emergency request not found')
    return em


@router.get('/emergencies', response_model=Page[EmergencyOut])
def list_all_emergencies(db: db_dependency,
                         q: str | None = Query(None, description='patient name / phone / address / ID'),
                         status_: Literal['pending', 'dispatched', 'en_route', 'completed', 'cancelled'] | None = Query(None, alias='status'),
                         priority: Literal['low', 'medium', 'high', 'critical'] | None = None,
                         ambulance_id: int | None = Query(None, gt=0),
                         hospital_id: int | None = Query(None, gt=0),
                         created_from: date | None = None, created_to: date | None = None,
                         sort_by: Literal['created_at', 'patient_name', 'priority', 'status'] = 'created_at',
                         order: Order = 'desc',
                         page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100)):
    return emergency_list(db, None, q, status_, priority, ambulance_id, hospital_id,
                          created_from, created_to, sort_by, order, page, page_size)


@router.get('/emergencies/{emergency_id}', response_model=EmergencyOut)
def get_emergency(db: db_dependency, emergency_id: int):
    return _get_emergency(db, emergency_id)


@router.put('/emergencies/{emergency_id}', response_model=EmergencyOut)
def update_emergency(db: db_dependency, emergency_id: int, body: EmergencyUpdate):
    em = _get_emergency(db, emergency_id)
    for key, value in clean_update(body.model_dump(exclude_unset=True), nullable=('latitude', 'longitude', 'description')).items():
        setattr(em, key, value)
    db.commit()
    db.refresh(em)
    return em


@router.delete('/emergencies/{emergency_id}', status_code=status.HTTP_204_NO_CONTENT)
def delete_emergency(db: db_dependency, emergency_id: int):
    em = _get_emergency(db, emergency_id)
    if em.status in ('dispatched', 'en_route'):
        free_ambulance(db, em)
    db.delete(em)
    db.commit()


@router.post('/emergencies/{emergency_id}/dispatch', response_model=EmergencyOut)
def dispatch(db: db_dependency, emergency_id: int, body: DispatchRequest):
    """Pending request e available ambulance (ar chaile hospital) assign kore."""
    em = _get_emergency(db, emergency_id)
    if em.status != 'pending':
        raise HTTPException(status_code=409, detail=f"Only pending requests can be dispatched (current: {em.status})")

    # PostgreSQL e FOR UPDATE: duita dispatcher ek ambulance nite parbe na (SQLite e kono effect nai)
    ambulance = db.query(Ambulances).filter(Ambulances.id == body.ambulance_id).with_for_update().first()
    if ambulance is None:
        raise HTTPException(status_code=404, detail='Ambulance not found')
    if ambulance.status != 'available':
        raise HTTPException(status_code=409, detail=f"Ambulance is not available (current: {ambulance.status})")
    if body.hospital_id and db.query(Hospitals).filter(Hospitals.id == body.hospital_id).first() is None:
        raise HTTPException(status_code=404, detail='Hospital not found')

    em.ambulance_id = ambulance.id
    em.hospital_id = body.hospital_id
    em.status = 'dispatched'
    em.dispatched_at = datetime.datetime.now()
    ambulance.status = 'dispatched'
    db.commit()
    db.refresh(em)
    return em


@router.patch('/emergencies/{emergency_id}/status', response_model=EmergencyOut)
def update_status(db: db_dependency, emergency_id: int, body: StatusUpdate):
    em = _get_emergency(db, emergency_id)
    change_status(db, em, body.status)
    db.commit()
    db.refresh(em)
    return em
