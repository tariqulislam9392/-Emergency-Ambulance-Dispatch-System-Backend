import datetime
import os
from datetime import date
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

import models
from database import SessionLocal, engine, get_db
from models import Emergencies, Hospitals, Users
from router import admin, auth
from router.auth import get_current_user, hash_password
from schemas import EmergencyCreate, EmergencyOut, EmergencyUpdate, HospitalOut, Page
from utils import apply_date_range, apply_sort, change_status, emergency_list, paginate, search_filter

app = FastAPI(title='Emergency Ambulance Dispatch System')

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000","https://stalwart-crumble-5d348c.netlify.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

models.Base.metadata.create_all(bind=engine)
app.include_router(auth.router)
app.include_router(admin.router)

db_dependency = Annotated[Session, Depends(get_db)]
user_dependency = Annotated[dict, Depends(get_current_user)]


def seed_admin():
    email = os.getenv('ADMIN_EMAIL', 'admin@example.com').lower()
    with SessionLocal() as db:
        if not db.query(Users).filter(Users.email == email).first():
            db.add(Users(email=email, username='admin', firstname='System', lastname='Admin',
                         hash_password=hash_password(os.getenv('ADMIN_PASSWORD', 'Admin12345')), role='admin'))
            db.commit()


seed_admin()


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    errors = []
    for err in exc.errors():
        loc = [str(p) for p in err['loc'] if p not in ('body', 'query', 'path')]
        errors.append({'field': '.'.join(loc), 'message': str(err['msg']).removeprefix('Value error, ')})
    return JSONResponse(status_code=422, content={'detail': 'Validation failed', 'errors': errors})


@app.get('/')
def health():
    return {'status': 'ok'}


def list_hospitals(user: user_dependency, db: db_dependency,
                   q: str | None = Query(None, description='name / city / address / ID'),
                   city: str | None = None,
                   min_beds: int | None = Query(None, ge=0),
                   created_from: date | None = None, created_to: date | None = None,
                   sort_by: Literal['created_at', 'name', 'city', 'available_beds'] = 'name',
                   order: Literal['asc', 'desc'] = 'asc',
                   page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100)):
    query = db.query(Hospitals)
    if q:
        query = query.filter(search_filter(q, Hospitals, [Hospitals.name, Hospitals.city, Hospitals.address]))
    if city:
        query = query.filter(Hospitals.city.ilike(city.strip()))
    if min_beds is not None:
        query = query.filter(Hospitals.available_beds >= min_beds)
    query = apply_date_range(query, Hospitals.created_at, created_from, created_to)
    return paginate(apply_sort(query, Hospitals, sort_by, order), page, page_size)


@app.get('/hospitals/{hospital_id}', response_model=HospitalOut)
def get_hospital(user: user_dependency, db: db_dependency, hospital_id: int):
    hospital = db.query(Hospitals).filter(Hospitals.id == hospital_id).first()
    if hospital is None:
        raise HTTPException(status_code=404, detail='Hospital not found')
    return hospital


@app.post('/emergencies', response_model=EmergencyOut, status_code=201)
def create_emergency(user: user_dependency, db: db_dependency, body: EmergencyCreate):
    em = Emergencies(**body.model_dump(), requested_by=user.get('id'))
    db.add(em)
    db.commit()
    db.refresh(em)
    return em



@app.get('/emergencies/my', response_model=Page[EmergencyOut])
def my_emergencies(user: user_dependency, db: db_dependency,
                   q: str | None = Query(None, description='patient name / phone / address / ID'),
                   status_: Literal['pending', 'dispatched', 'en_route', 'completed', 'cancelled'] | None = Query(None, alias='status'),
                   priority: Literal['low', 'medium', 'high', 'critical'] | None = None,
                   created_from: date | None = None, created_to: date | None = None,
                   sort_by: Literal['created_at', 'patient_name', 'priority', 'status'] = 'created_at',
                   order: Literal['asc', 'desc'] = 'desc',
                   page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100)):
    return emergency_list(db, user.get('id'), q, status_, priority, None, None,
                          created_from, created_to, sort_by, order, page, page_size)


def _get_own_emergency(db: Session, user: dict, emergency_id: int) -> Emergencies:
    em = db.query(Emergencies).filter(Emergencies.id == emergency_id, Emergencies.requested_by == user.get('id')).first()
    if em is None:  
        raise HTTPException(status_code=404, detail='Emergency request not found')
    return em


@app.get('/emergencies/{emergency_id}', response_model=EmergencyOut)
def get_my_emergency(user: user_dependency, db: db_dependency, emergency_id: int):
    return _get_own_emergency(db, user, emergency_id)


@app.put('/emergencies/{emergency_id}', response_model=EmergencyOut)
def update_my_emergency(user: user_dependency, db: db_dependency, emergency_id: int, body: EmergencyUpdate):
    em = _get_own_emergency(db, user, emergency_id)
    if em.status != 'pending':
        raise HTTPException(status_code=409, detail='Request can no longer be edited; contact dispatch')
    data = body.model_dump(exclude_unset=True)
    for key, value in data.items():
        if value is None and key not in ('latitude', 'longitude', 'description'):
            continue
        setattr(em, key, value)
    db.commit()
    db.refresh(em)
    return em


@app.post('/emergencies/{emergency_id}/cancel', response_model=EmergencyOut)
def cancel_emergency(user: user_dependency, db: db_dependency, emergency_id: int):
    em = _get_own_emergency(db, user, emergency_id)
    if em.status not in ('pending', 'dispatched'):
        raise HTTPException(status_code=409, detail='Request can no longer be cancelled by the user')
    change_status(db, em, 'cancelled')
    db.commit()
    db.refresh(em)
    return em

@app.get('/hospitals', response_model=Page[HospitalOut])
def get_hospitals(db: db_dependency,
                  q: str | None = Query(None, description='hospital name / phone / address / ID'),
                  page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=100)):
    def hospital_list(db, q, page, page_size):
        query = db.query(Hospitals)
        if q:
            query = query.filter(search_filter(q, Hospitals, [Hospitals.name, Hospitals.city, Hospitals.address]))
        return paginate(query.order_by(Hospitals.id.desc()), page, page_size)

    return hospital_list(db, q, page, page_size)

