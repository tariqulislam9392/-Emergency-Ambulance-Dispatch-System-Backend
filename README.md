# Emergency Ambulance Dispatch System — Backend

Tomar library project er moto structure: `database.py`, `models.py`, `main.py` + `router/auth.py`, `router/admin.py`.

## Run
```bash
python -m venv venv && venv\Scripts\activate      # Linux/Mac: source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```
Swagger: http://localhost:8000/docs → **Authorize** (username = email ba username)
Default admin (first run e auto): `admin@example.com` / `Admin12345`  (env: ADMIN_EMAIL, ADMIN_PASSWORD)

## File → kaj
| File | Kaj |
|---|---|
| `database.py` | engine, session, Base, `get_db` |
| `models.py` | Users, Ambulances, Hospitals, Emergencies, RefreshTokens, PasswordResets |
| `schemas.py` | Pydantic validation (backend form validation) |
| `utils.py` | search / filter / date range / sort / pagination + status transition |
| `router/auth.py` | signup, login, refresh, logout, me, forgot/reset password, `get_current_user`, `get_admin_user` |
| `router/admin.py` | admin-only: users, ambulances, hospitals write, emergencies manage + dispatch |
| `main.py` | user routes: hospitals read, emergency create/my/get/update/cancel |

## Routes
| Route | Access |
|---|---|
| `POST /auth/signup, /auth/login, /auth/refresh, /auth/logout, /auth/forgot-password, /auth/reset-password` | public |
| `GET /auth/me` | logged-in |
| `GET /hospitals`, `GET /hospitals/{id}` | logged-in user |
| `POST /emergencies`, `GET /emergencies/my`, `GET/PUT /emergencies/{id}`, `POST /emergencies/{id}/cancel` | user (nijer gulo) |
| `/admin/users`, `/admin/ambulances` (full CRUD) | admin |
| `POST/PUT/DELETE /admin/hospitals` | admin |
| `GET /admin/emergencies`, `GET/PUT/DELETE /admin/emergencies/{id}` | admin |
| `POST /admin/emergencies/{id}/dispatch`, `PATCH /admin/emergencies/{id}/status` | admin |

## List query params (sob list endpoint e)
`q` (name/phone/address/**ID**), filter (`status`, `priority`, `type`, `role`, `city`, `min_beds` ...),
`created_from` / `created_to` (YYYY-MM-DD), `sort_by`, `order=asc|desc`, `page`, `page_size` (1–100).
Response: `{ items, total, page, page_size, pages }`

Example: `GET /admin/emergencies?status=pending&priority=critical&sort_by=priority&order=desc&page=1&page_size=20`

## Validation error format
```json
{ "detail": "Validation failed", "errors": [ { "field": "password", "message": "..." } ] }
```

## Frontend token flow
1. Login → access_token + refresh_token save koro.
2. Request e `Authorization: Bearer <access_token>`.
3. `401` + `detail == "Token expired"` hole `POST /auth/refresh` → notun pair save → request retry.
4. Refresh fail hole login page e pathao.

## Dispatch flow
`pending` → (admin dispatch) → `dispatched` → `en_route` → `completed`; `cancelled` jekono active state theke.
Dispatch e ambulance `dispatched` hoy, complete/cancel hole abar `available`.
