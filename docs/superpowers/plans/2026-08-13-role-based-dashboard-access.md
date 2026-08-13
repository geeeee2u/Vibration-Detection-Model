# Role-Based Dashboard Access Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Protect model settings so only administrator accounts can access or modify them, while technician accounts can use operational dashboards.

**Architecture:** FastAPI validates credentials loaded from environment variables and stores the authenticated role in a signed session cookie. Frontend pages obtain the current session from the API, show account information in the sidebar, and use a reusable login dialog. The backend remains the authorization boundary for settings and reanalysis APIs.

**Tech Stack:** FastAPI, Starlette session middleware, Python standard library environment variables, vanilla JavaScript, pytest.

## Global Constraints

- Store credentials only in `.env`; do not commit actual passwords.
- Use roles `administrator` and `technician` exactly.
- Show `해당 계정으로는 접근할 수 없습니다.` to a technician who opens model settings.
- Enforce authorization in backend routes, not only in the frontend.

---

### Task 1: Server-side session authentication

**Files:**
- Modify: `backend/main.py`
- Create: `.env.example`
- Modify: `.gitignore`
- Test: `tests/test_backend_api.py`

**Interfaces:**
- Produces `POST /api/auth/login`, `POST /api/auth/logout`, and `GET /api/auth/me`.
- Produces administrator-only protection for `/settings`, `GET /api/settings`, `PUT /api/settings`, and `POST /api/reanalyze`.

- [ ] **Step 1: Write failing API tests**

```python
def test_technician_cannot_open_or_change_settings(client):
    client.post('/api/auth/login', json={'username': 'technician', 'password': 'tech123'})
    assert client.get('/settings').status_code == 403
    assert client.get('/api/settings').status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\\Scripts\\python.exe -m pytest tests\\test_backend_api.py -q`
Expected: FAIL because authentication routes and authorization do not exist.

- [ ] **Step 3: Implement sessions and role checks**

```python
app.add_middleware(SessionMiddleware, secret_key=os.environ['SESSION_SECRET'])

def require_administrator(request: Request):
    if request.session.get('role') != 'administrator':
        raise HTTPException(403, '해당 계정으로는 접근할 수 없습니다.')
```

Load `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `TECHNICIAN_USERNAME`, and `TECHNICIAN_PASSWORD` from `.env`; include only their variable names in `.env.example`.

- [ ] **Step 4: Run focused tests**

Run: `.venv\\Scripts\\python.exe -m pytest tests\\test_backend_api.py -q`
Expected: PASS.

### Task 2: Login dialog and account display

**Files:**
- Modify: `frontend/assets/app.js`
- Modify: `frontend/overview.html`
- Modify: `frontend/analysis.html`
- Modify: `frontend/alarms.html`
- Modify: `frontend/performance.html`
- Modify: `frontend/settings.html`
- Test: `tests/test_frontend_layout.py`

**Interfaces:**
- Consumes `GET /api/auth/me`, `POST /api/auth/login`, and `POST /api/auth/logout`.
- Produces a reusable account section and modal on every dashboard page.

- [ ] **Step 1: Write a failing static layout test**

```python
def test_each_dashboard_page_has_account_control():
    for filename in PAGE_FILENAMES:
        html = (ROOT / 'frontend' / filename).read_text(encoding='utf-8')
        assert 'data-account-control' in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\\Scripts\\python.exe -m pytest tests\\test_frontend_layout.py -q`
Expected: FAIL because account controls are absent.

- [ ] **Step 3: Implement UI behavior**

```javascript
async function loadCurrentUser() {
  const user = await requestJson('/api/auth/me');
  renderAccount(user);
}
```

Use the account control to open a login dialog, submit credentials to `/api/auth/login`, reload user state after success, and send logout requests to `/api/auth/logout`.

- [ ] **Step 4: Run focused tests**

Run: `.venv\\Scripts\\python.exe -m pytest tests\\test_frontend_layout.py -q`
Expected: PASS.

### Task 3: Settings denial screen and end-to-end verification

**Files:**
- Modify: `frontend/assets/app.js`
- Test: `tests/test_backend_api.py`
- Test: `tests/test_frontend_layout.py`

**Interfaces:**
- Consumes HTTP 403 responses containing `해당 계정으로는 접근할 수 없습니다.`.
- Produces a visible access-denied panel on `/settings` for technicians.

- [ ] **Step 1: Write a failing behavior test**

```python
def test_settings_denial_message_is_present_in_frontend_script():
    script = (ROOT / 'frontend' / 'assets' / 'app.js').read_text(encoding='utf-8')
    assert '해당 계정으로는 접근할 수 없습니다.' in script
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\\Scripts\\python.exe -m pytest tests\\test_frontend_layout.py -q`
Expected: FAIL because the denial panel is not implemented.

- [ ] **Step 3: Implement the denial panel**

```javascript
if (user.role === 'technician' && document.body.dataset.page === 'settings') {
  document.querySelector('main').innerHTML = '<section>해당 계정으로는 접근할 수 없습니다.</section>';
  return;
}
```

Keep direct backend authorization enabled so the panel is not the only protection.

- [ ] **Step 4: Run full validation**

Run: `.venv\\Scripts\\python.exe -m pytest -q`
Expected: all tests pass, then manually verify administrator and technician login flows in the browser.
