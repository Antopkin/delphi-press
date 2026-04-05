"""Tests for src.web.router — HTML page routes."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, date, datetime

import pytest
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from src.config import Settings
from src.db.engine import create_session_factory
from src.db.models import Base, Headline, Prediction, PredictionStatus

# ── Fakes (same as test_api) ──────────────────────────────────────


class FakeRedis:
    def __init__(self):
        self._queues = {}

    async def ping(self):
        return True

    async def close(self):
        pass


class FakeArqPool:
    def __init__(self):
        self.jobs = []

    async def enqueue_job(self, func_name, *args, **kwargs):
        self.jobs.append((func_name, args, kwargs))

    async def close(self):
        pass


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
async def web_engine():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def web_app(web_engine):
    """FastAPI app with both API and web routers for testing pages."""
    from src.api.router import api_router
    from src.security.encryption import KeyVault
    from src.web.router import web_router

    app = FastAPI()
    app.include_router(api_router)
    app.include_router(web_router)

    app.mount(
        "/static",
        StaticFiles(directory="src/web/static"),
        name="static",
    )

    settings = Settings()

    # Expose app_version to Jinja2 templates (cache-busting)
    from src.web.router import templates

    templates.env.globals["app_version"] = settings.app_version

    app.state.settings = settings
    app.state.engine = web_engine
    app.state.session_factory = create_session_factory(web_engine)
    app.state.redis = FakeRedis()
    app.state.arq_pool = FakeArqPool()
    app.state.start_time = time.monotonic()
    app.state.key_vault = KeyVault(settings.fernet_key)

    return app


@pytest.fixture
async def web_client(web_app):
    async with AsyncClient(
        transport=ASGITransport(app=web_app),
        base_url="http://test",
    ) as client:
        yield client


@pytest.fixture
def seed_web_prediction(web_app):
    """Factory that creates a Prediction row in test DB."""

    async def _seed(**overrides) -> str:
        defaults = {
            "id": str(uuid.uuid4()),
            "outlet_name": "TASS",
            "outlet_normalized": "tass",
            "target_date": date(2026, 4, 1),
            "status": PredictionStatus.PENDING,
        }
        defaults.update(overrides)

        session_factory = web_app.state.session_factory
        async with session_factory() as session:
            pred = Prediction(**defaults)
            session.add(pred)
            await session.commit()
        return defaults["id"]

    return _seed


@pytest.fixture
def seed_web_headline(web_app):
    """Factory that creates a Headline row in test DB."""

    async def _seed(prediction_id: str, **overrides) -> None:
        defaults = {
            "prediction_id": prediction_id,
            "rank": 1,
            "headline_text": "Test headline for display",
            "first_paragraph": "First paragraph text.",
            "confidence": 0.85,
            "confidence_label": "very_high",
            "category": "politics",
            "reasoning": "Test reasoning.",
            "agent_agreement": "consensus",
        }
        defaults.update(overrides)

        session_factory = web_app.state.session_factory
        async with session_factory() as session:
            headline = Headline(**defaults)
            session.add(headline)
            await session.commit()

    return _seed


# ── Index page ────────────────────────────────────────────────────


class TestIndexPage:
    async def test_index_returns_200(self, web_client):
        resp = await web_client.get("/")
        assert resp.status_code == 200

    async def test_index_contains_hero(self, web_client):
        resp = await web_client.get("/")
        assert "Что напишут СМИ завтра?" in resp.text

    async def test_index_contains_form(self, web_client):
        resp = await web_client.get("/")
        assert 'id="prediction-form"' in resp.text
        assert 'id="outlet"' in resp.text
        assert 'id="target_date"' in resp.text

    async def test_index_contains_preset_cards(self, web_client):
        resp = await web_client.get("/")
        assert 'name="preset"' in resp.text
        assert 'value="light"' in resp.text
        assert 'value="full"' in resp.text
        assert "~$0.20" in resp.text
        assert "~$7" in resp.text
        # Standard preset hidden from UI (kept in backend for backward compat)
        assert 'value="standard"' not in resp.text


# ── About page ────────────────────────────────────────────────────


class TestAboutPage:
    async def test_about_returns_200(self, web_client):
        resp = await web_client.get("/about")
        assert resp.status_code == 200

    async def test_about_contains_methodology(self, web_client):
        resp = await web_client.get("/about")
        assert "Метод Дельфи" in resp.text


# ── Progress page ─────────────────────────────────────────────────


class TestProgressPage:
    async def test_progress_page_with_pending_prediction(self, web_client, seed_web_prediction):
        pred_id = await seed_web_prediction()
        resp = await web_client.get(f"/predict/{pred_id}")
        assert resp.status_code == 200
        assert "Формируем прогноз" in resp.text

    async def test_progress_page_shows_outlet(self, web_client, seed_web_prediction):
        pred_id = await seed_web_prediction(outlet_name="РБК")
        resp = await web_client.get(f"/predict/{pred_id}")
        assert "РБК" in resp.text

    async def test_progress_redirects_to_results_when_completed(
        self, web_client, seed_web_prediction
    ):
        pred_id = await seed_web_prediction(
            status=PredictionStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
        resp = await web_client.get(f"/predict/{pred_id}")
        assert resp.status_code == 200
        # Should render results template, not progress
        assert "Прогноз для" in resp.text


# ── Results page ──────────────────────────────────────────────────


class TestResultsPage:
    async def test_results_page_with_completed_prediction(
        self, web_client, seed_web_prediction, seed_web_headline
    ):
        pred_id = await seed_web_prediction(
            status=PredictionStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
        await seed_web_headline(pred_id)

        resp = await web_client.get(f"/results/{pred_id}")
        assert resp.status_code == 200
        assert "Test headline for display" in resp.text

    async def test_results_page_redirects_to_progress_when_pending(
        self, web_client, seed_web_prediction
    ):
        pred_id = await seed_web_prediction(status=PredictionStatus.PENDING)
        resp = await web_client.get(f"/results/{pred_id}")
        assert resp.status_code == 200
        # Should render progress template
        assert "Формируем прогноз" in resp.text


# ── Auth pages ────────────────────────────────────────────────────


class TestLoginPage:
    async def test_login_page_returns_200(self, web_client):
        resp = await web_client.get("/login")
        assert resp.status_code == 200
        assert "Вход" in resp.text

    async def test_login_contains_form(self, web_client):
        resp = await web_client.get("/login")
        assert 'action="/login"' in resp.text
        assert 'name="email"' in resp.text
        assert 'name="password"' in resp.text

    async def test_login_redirects_when_authenticated(self, web_client):
        # Register a user first
        email = f"auth-{uuid.uuid4().hex[:8]}@test.com"
        reg = await web_client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "securepass123"},
        )
        token = reg.json()["access_token"]

        resp = await web_client.get(
            "/login",
            cookies={"access_token": token},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert resp.headers["location"] == "/"

    async def test_login_submit_success_sets_cookie(self, web_client):
        email = f"login-{uuid.uuid4().hex[:8]}@test.com"
        await web_client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "securepass123"},
        )

        resp = await web_client.post(
            "/login",
            data={"email": email, "password": "securepass123", "next": "/"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "access_token" in resp.cookies

    async def test_login_submit_wrong_password_shows_error(self, web_client):
        email = f"fail-{uuid.uuid4().hex[:8]}@test.com"
        await web_client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "securepass123"},
        )

        resp = await web_client.post(
            "/login",
            data={"email": email, "password": "wrongpassword", "next": "/"},
        )
        assert resp.status_code == 200
        assert "Неверный email или пароль" in resp.text


class TestRegisterPage:
    async def test_register_page_returns_200(self, web_client):
        resp = await web_client.get("/register")
        assert resp.status_code == 200
        assert "Регистрация" in resp.text

    async def test_register_submit_success_sets_cookie(self, web_client):
        email = f"reg-{uuid.uuid4().hex[:8]}@test.com"
        resp = await web_client.post(
            "/register",
            data={"email": email, "password": "securepass123"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "access_token" in resp.cookies

    async def test_register_duplicate_email_shows_error(self, web_client):
        email = f"dup-{uuid.uuid4().hex[:8]}@test.com"
        await web_client.post(
            "/register",
            data={"email": email, "password": "securepass123"},
            follow_redirects=False,
        )
        resp = await web_client.post(
            "/register",
            data={"email": email, "password": "anotherpass123"},
        )
        assert resp.status_code == 200
        assert "уже существует" in resp.text

    async def test_register_short_password_shows_error(self, web_client):
        resp = await web_client.post(
            "/register",
            data={"email": "short@test.com", "password": "short"},
        )
        assert resp.status_code == 200
        assert "не менее 8 символов" in resp.text


class TestLogout:
    async def test_logout_post_clears_cookie_and_redirects(self, web_client):
        resp = await web_client.post("/logout", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/"

    async def test_logout_get_returns_405(self, web_client):
        """GET /logout should no longer work (prefetch/img tag abuse)."""
        resp = await web_client.get("/logout", follow_redirects=False)
        assert resp.status_code == 405


class TestMyPredictions:
    async def test_guest_sees_registration_prompt(self, web_client):
        resp = await web_client.get("/")
        assert "Зарегистрируйтесь" in resp.text
        assert "Мои прогнозы" not in resp.text

    async def test_authenticated_user_sees_my_predictions_label(
        self, web_client, seed_web_prediction
    ):
        email = f"my-{uuid.uuid4().hex[:8]}@test.com"
        reg = await web_client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "securepass123"},
        )
        token = reg.json()["access_token"]

        # Get user_id from /me
        me = await web_client.get(
            "/api/v1/auth/me",
            cookies={"access_token": token},
        )
        user_id = me.json()["id"]

        # Create a prediction for this user
        await seed_web_prediction(user_id=user_id)

        resp = await web_client.get("/", cookies={"access_token": token})
        assert "Мои прогнозы" in resp.text
        assert "Зарегистрируйтесь" not in resp.text

    async def test_authenticated_user_does_not_see_other_users_predictions(
        self, web_client, seed_web_prediction
    ):
        # Create prediction for another user
        await seed_web_prediction(user_id="other-user-id", outlet_name="SecretOutlet")

        # Register new user
        email = f"filter-{uuid.uuid4().hex[:8]}@test.com"
        reg = await web_client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "securepass123"},
        )
        token = reg.json()["access_token"]

        resp = await web_client.get("/", cookies={"access_token": token})
        assert "SecretOutlet" not in resp.text


class TestSettingsPage:
    async def test_settings_redirects_to_login_for_guests(self, web_client):
        resp = await web_client.get("/settings", follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["location"]

    async def test_settings_returns_200_for_authenticated(self, web_client):
        email = f"settings-{uuid.uuid4().hex[:8]}@test.com"
        reg = await web_client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "securepass123"},
        )
        token = reg.json()["access_token"]

        resp = await web_client.get("/settings", cookies={"access_token": token})
        assert resp.status_code == 200
        assert "Настройки" in resp.text
        assert "Добавить ключ" in resp.text

    async def test_settings_shows_keys_table(self, web_client):
        email = f"keys-{uuid.uuid4().hex[:8]}@test.com"
        reg = await web_client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "securepass123"},
        )
        token = reg.json()["access_token"]

        # Add a key via API
        await web_client.post(
            "/api/v1/keys",
            json={"provider": "openrouter", "api_key": "sk-or-test-key-12345"},
            cookies={"access_token": token},
        )

        resp = await web_client.get("/settings", cookies={"access_token": token})
        assert resp.status_code == 200
        assert "openrouter" in resp.text


class TestNavigation:
    async def test_nav_shows_login_for_guests(self, web_client):
        resp = await web_client.get("/")
        assert "Войти" in resp.text
        assert "Настройки" not in resp.text

    async def test_nav_shows_settings_for_authenticated(self, web_client):
        email = f"nav-{uuid.uuid4().hex[:8]}@test.com"
        reg = await web_client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "securepass123"},
        )
        token = reg.json()["access_token"]

        resp = await web_client.get("/", cookies={"access_token": token})
        assert "Настройки" in resp.text
        assert "Выйти" in resp.text
        assert "Войти" not in resp.text


# ── CSRF Protection ────────────────────────────────────────────────


class TestCSRF:
    @pytest.fixture
    async def csrf_app(self, web_engine):
        """Web app WITH CSRF middleware enabled."""
        from src.api.router import api_router
        from src.security.csrf import CSRFMiddleware
        from src.security.encryption import KeyVault
        from src.web.router import web_router

        app = FastAPI()
        app.add_middleware(CSRFMiddleware)
        app.include_router(api_router)
        app.include_router(web_router)

        app.mount("/static", StaticFiles(directory="src/web/static"), name="static")

        settings = Settings()
        app.state.settings = settings
        app.state.engine = web_engine
        app.state.session_factory = create_session_factory(web_engine)
        app.state.redis = FakeRedis()
        app.state.arq_pool = FakeArqPool()
        app.state.start_time = time.monotonic()
        app.state.key_vault = KeyVault(settings.fernet_key)

        return app

    @pytest.fixture
    async def csrf_client(self, csrf_app):
        async with AsyncClient(
            transport=ASGITransport(app=csrf_app),
            base_url="http://test",
        ) as client:
            yield client

    async def test_login_post_without_csrf_rejected(self, csrf_client):
        """POST /login without CSRF token should be rejected."""
        resp = await csrf_client.post(
            "/login",
            data={"email": "test@test.com", "password": "securepass123"},
            follow_redirects=False,
        )
        assert resp.status_code == 403

    async def test_json_api_bypasses_csrf(self, csrf_client):
        """JSON API requests should bypass CSRF (protected by CORS+SameSite)."""
        resp = await csrf_client.post(
            "/api/v1/auth/register",
            json={"email": f"csrf-{uuid.uuid4().hex[:6]}@test.com", "password": "securepass123"},
        )
        # Should NOT be 403. JSON is exempt from CSRF.
        assert resp.status_code != 403

    async def test_register_with_csrf_preserves_form_body(self, csrf_client):
        """CSRF middleware must not consume request body — Form(...) must still work."""
        # Get CSRF token via GET
        get_resp = await csrf_client.get("/register")
        csrf_token = get_resp.cookies.get("csrf_token", "")

        resp = await csrf_client.post(
            "/register",
            data={
                "email": f"csrf-reg-{uuid.uuid4().hex[:6]}@test.com",
                "password": "securepass123",
                "csrf_token": csrf_token,
            },
            cookies={"csrf_token": csrf_token},
            follow_redirects=False,
        )
        # Must redirect (302) on success, NOT return 422 "Field required"
        assert resp.status_code == 302, f"Expected redirect, got {resp.status_code}"


# ── Static Asset Cache-Busting (M26) ─────────────────────────────


class TestStaticAssetCacheBusting:
    async def test_static_css_has_version_param(self, web_client):
        """CSS link must include ?v= for cache-busting after deploy."""
        resp = await web_client.get("/")
        assert resp.status_code == 200
        assert "tailwind.css?v=" in resp.text

    async def test_static_js_has_version_param(self, web_client):
        """JS scripts must include ?v= for cache-busting after deploy."""
        resp = await web_client.get("/")
        assert resp.status_code == 200
        assert "form.js?v=" in resp.text

    async def test_index_contains_outlet_url_field(self, web_client):
        """Index page must have a hidden outlet_url field for unknown outlets."""
        resp = await web_client.get("/")
        assert resp.status_code == 200
        assert 'id="outlet_url"' in resp.text

    async def test_version_param_matches_app_version(self, web_client):
        """Version in ?v= must match Settings().app_version (synced with CHANGELOG)."""
        from src.config import Settings

        resp = await web_client.get("/")
        version = Settings().app_version
        assert f"tailwind.css?v={version}" in resp.text
        assert f"form.js?v={version}" in resp.text
        # Version must not be the placeholder "0.1.0"
        assert version != "0.1.0", f"app_version still at placeholder {version}"
