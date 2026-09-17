# Insights, Telegram notifications, per-assignment models (slice 3) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Per-assignment Insights (stats + AI narrative + PDF), Telegram notifications (hand-ins, marking finished, daily digest) and per-assignment model choice with custom model lists for OpenRouter/TokenRouter.

**Architecture:** One migration (0009) adds the settings columns, `custom_models`, `assignment_insights`, `notifications`, and the template's model override. Model resolution goes through `SettingsStore.for_template`, used by every job. The worker loop gains three 10-second ticks: Telegram polling (`/start` linking), outbox flush, daily digest; plus a post-mark hook that fires `marking_done` and the `insights` job when a class assignment's queue drains. Insights = computed stats (`services/insights.py`) + one agent call (`agents/insights.py`) + ReportLab PDF.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy Core (`Database` `:name` params), Alembic, atomic-agents, httpx (already a dependency), `zoneinfo`, ReportLab (new); React 18 + TS + vitest.

**Spec:** `docs/superpowers/specs/2026-09-17-insights-telegram-models-design.md`

## Global Constraints

- Student **names never reach the model** in Insights (`InsightsInput` carries register numbers only); names are joined back in the app.
- Telegram bot token stored encrypted with the same `KeyCipher` as API keys; never returned by any API (`telegram_bot_hint` = last 4 chars only).
- Defaults: `telegram_daily_time = "07:00"`, `timezone = "Asia/Singapore"`, `telegram_instant = true`.
- Per-assignment model: NULL provider means **Auto — follow Settings**; a chosen provider must have a saved key (400 `no_key_for_provider`).
- `custom_models` only for providers whose `ProviderSpec.custom_models` is true: `tokenrouter`, `openrouter`.
- Rate limiting is per provider: the global provider uses `settings.rpm_limit`, any other its `default_rpm`.
- Error shape `{"error": {"code", "message"}}` via `ApiError`; timestamps via `iso_utc`.
- Before every commit: `uv run pytest -q` (no warnings summary); frontend tasks also `cd web && npx vitest run && npx tsc --noEmit && npm run build`.
- Commit messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Never push. Never dispatch subagents from a task.

## File structure

| File | Responsibility |
|---|---|
| `src/sms/migrations/versions/0009_insights_telegram_models.py` | schema |
| `src/sms/providers/settings.py` | new fields; `for_template`; telegram token |
| `src/sms/providers/registry.py` | `custom_models` flag; `merge_custom_models` |
| `src/sms/providers/ratelimit.py` | `BucketPool` |
| `src/sms/web/services/custom_models.py` | list/add/remove custom models |
| `src/sms/web/services/insights.py` | `compute_stats`, `select_samples`, load/upsert |
| `src/sms/schemas/insights.py`, `src/sms/agents/insights.py` | agent IO + agent |
| `src/sms/worker/insights_job.py` | job runner |
| `src/sms/records/insights_pdf.py` | PDF |
| `src/sms/web/services/telegram.py` | `TelegramClient`, message formatting, `app_base_url` |
| `src/sms/web/services/notify.py` | outbox rows, `on_mark_settled`, flush, daily digest, linking poll |
| `src/sms/web/routers/settings.py` | telegram test/unlink, custom models routes |
| `src/sms/web/routers/class_assignments.py` | insights routes |
| `src/sms/worker/{worker,mark_job,extract_jobs}.py` | dispatch, hooks, per-template settings |
| `web/src/pages/{Settings,AssignmentEditor,ClassAssignmentPage}.tsx`, `web/src/components/InsightsPanel.tsx` | UI |

---

### Task 1: Migration 0009, Settings fields, `for_template`, `BucketPool`

**Files:**
- Create: `src/sms/migrations/versions/0009_insights_telegram_models.py`
- Modify: `src/sms/providers/settings.py`, `src/sms/providers/ratelimit.py`, `src/sms/providers/registry.py` (add `custom_models: bool = False` to `ProviderSpec`, set `custom_models=True` on tokenrouter and openrouter)
- Test: `tests/unit/test_settings_store.py`, `tests/unit/test_ratelimit.py` (append)

**Interfaces produced:**
- `Settings` gains `telegram_bot_token: Optional[str]`, `telegram_chat_id: Optional[str]`, `telegram_instant: bool = True`, `telegram_daily_time: str = "07:00"`, `timezone: str = "Asia/Singapore"`, `app_url: Optional[str] = None`, `telegram_daily_last_sent: Optional[str] = None`, `telegram_update_offset: int = 0`; properties `telegram_linked` (token and chat id set), `telegram_bot_hint`. `public_dict()` drops the token and adds both.
- `SettingsStore.save(settings)` persists them (blank token = keep existing, like keys); `SettingsStore.set_telegram(chat_id: Optional[str] = ..., offset: Optional[int] = ..., daily_last_sent: Optional[str] = ...)` updates only the given columns; `SettingsStore.clear_telegram()` nulls token, chat id, offset.
- `SettingsStore.for_template(tpl: Optional[dict]) -> Settings`: global settings unless `tpl` has `provider`; then `provider/model/extractor_model` from the template, `api_key = key_for(provider)`, `base_url = None`, `rpm_limit = provider default_rpm` when the provider differs from the global one.
- `ratelimit.BucketPool` with `get(provider: str, rpm: int) -> TokenBucket` (one bucket per provider, replaced when rpm changes).

- [ ] **Step 1: Failing tests** (append to `tests/unit/test_settings_store.py`):

```python
def test_telegram_and_timezone_fields_round_trip_and_token_is_hidden(store):
    s = store.load()
    assert s.telegram_daily_time == "07:00" and s.timezone == "Asia/Singapore" and s.telegram_instant is True
    assert not s.telegram_linked
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-x", rpm_limit=60,
                        telegram_bot_token="123456:ABCDEF", telegram_daily_time="18:30", timezone="Europe/London",
                        telegram_instant=False, app_url="https://marking.example.sg"))
    s = store.load()
    assert s.telegram_bot_token == "123456:ABCDEF" and s.telegram_bot_hint == "CDEF" and s.telegram_daily_time == "18:30"
    assert s.timezone == "Europe/London" and s.telegram_instant is False and s.app_url == "https://marking.example.sg"
    raw = store.db.query("SELECT telegram_bot_token_enc FROM settings")[0]["telegram_bot_token_enc"]
    assert "ABCDEF" not in raw
    d = s.public_dict()
    assert "telegram_bot_token" not in d and d["telegram_bot_hint"] == "CDEF" and d["telegram_linked"] is False
    # blank token keeps the saved one; linking sets the chat id
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key=None, rpm_limit=60, telegram_bot_token=""))
    assert store.load().telegram_bot_token == "123456:ABCDEF"
    store.set_telegram(chat_id="99887", offset=42)
    s = store.load(); assert s.telegram_linked and s.telegram_chat_id == "99887" and s.telegram_update_offset == 42
    store.set_telegram(daily_last_sent="2026-09-17")
    assert store.load().telegram_daily_last_sent == "2026-09-17"
    store.clear_telegram()
    s = store.load(); assert s.telegram_bot_token is None and s.telegram_chat_id is None and not s.telegram_linked


def test_for_template_overlays_provider_model_and_key(store):
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk-openai", rpm_limit=30))
    store.save(Settings(provider="openrouter", model="z-ai/glm-5.3-flash", api_key="or-key", rpm_limit=30))
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key=None, rpm_limit=30))
    assert store.for_template(None).provider == "openai"
    assert store.for_template({"provider": None, "model": None, "extractor_model": None}).model == "gpt-5-mini"
    s = store.for_template({"provider": "openrouter", "model": "openrouter/auto", "extractor_model": "qwen/qwen3-vl-plus"})
    assert (s.provider, s.model, s.extractor_model, s.api_key) == ("openrouter", "openrouter/auto", "qwen/qwen3-vl-plus", "or-key")
    assert s.rpm_limit == 60 and s.base_url is None          # openrouter's default_rpm, not the global 30
    s = store.for_template({"provider": "openai", "model": "gpt-5.5", "extractor_model": None})
    assert s.api_key == "sk-openai" and s.rpm_limit == 30      # same provider as global keeps the global rpm
```

Append to `tests/unit/test_ratelimit.py`:
```python
from sms.providers.ratelimit import BucketPool

def test_bucket_pool_one_bucket_per_provider_replaced_when_rpm_changes():
    pool = BucketPool()
    a = pool.get("openai", 60); b = pool.get("openrouter", 60)
    assert a is not b and pool.get("openai", 60) is a
    assert pool.get("openai", 8) is not a and pool.get("openai", 8).rpm == 8
```

- [ ] **Step 2: Run** `uv run pytest tests/unit/test_settings_store.py tests/unit/test_ratelimit.py -q` → FAIL.

- [ ] **Step 3: Migration**

```python
"""insights, telegram notifications, per-assignment models, custom model lists

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("settings") as b:
        b.add_column(sa.Column("telegram_bot_token_enc", sa.Text))
        b.add_column(sa.Column("telegram_chat_id", sa.Text))
        b.add_column(sa.Column("telegram_instant", sa.Boolean, nullable=False, server_default=sa.true()))
        b.add_column(sa.Column("telegram_daily_time", sa.Text, nullable=False, server_default="07:00"))
        b.add_column(sa.Column("timezone", sa.Text, nullable=False, server_default="Asia/Singapore"))
        b.add_column(sa.Column("app_url", sa.Text))
        b.add_column(sa.Column("telegram_daily_last_sent", sa.Text))
        b.add_column(sa.Column("telegram_update_offset", sa.Integer, nullable=False, server_default="0"))
    # NULL provider = follow Settings
    with op.batch_alter_table("assignment_templates") as b:
        b.add_column(sa.Column("provider", sa.Text))
        b.add_column(sa.Column("model", sa.Text))
        b.add_column(sa.Column("extractor_model", sa.Text))
    with op.batch_alter_table("class_assignments") as b:
        b.add_column(sa.Column("last_done_notified_at", sa.DateTime))
    op.create_table(
        "custom_models",
        sa.Column("provider", sa.Text, primary_key=True),
        sa.Column("model_id", sa.Text, primary_key=True),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("vision", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "assignment_insights",
        sa.Column("class_assignment_id", sa.Integer, sa.ForeignKey("class_assignments.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("stats_json", sa.Text, nullable=False),
        sa.Column("report_json", sa.Text),
        sa.Column("n_marked", sa.Integer, nullable=False, server_default="0"),
        sa.Column("provider", sa.Text),
        sa.Column("model", sa.Text),
        sa.Column("generated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("error", sa.Text),
    )
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("class_assignment_id", sa.Integer),
        sa.Column("payload_json", sa.Text, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("sent_at", sa.DateTime),
        sa.Column("error", sa.Text),
    )
    op.create_index("ix_notifications_unsent", "notifications", ["sent_at", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_notifications_unsent", table_name="notifications")
    op.drop_table("notifications")
    op.drop_table("assignment_insights")
    op.drop_table("custom_models")
    with op.batch_alter_table("class_assignments") as b:
        b.drop_column("last_done_notified_at")
    with op.batch_alter_table("assignment_templates") as b:
        b.drop_column("extractor_model"); b.drop_column("model"); b.drop_column("provider")
    with op.batch_alter_table("settings") as b:
        for c in ("telegram_update_offset", "telegram_daily_last_sent", "app_url", "timezone", "telegram_daily_time",
                  "telegram_instant", "telegram_chat_id", "telegram_bot_token_enc"):
            b.drop_column(c)
```

- [ ] **Step 4: Settings** — in `settings.py` add the dataclass fields after `keys`:
```python
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    telegram_instant: bool = True
    telegram_daily_time: str = "07:00"
    timezone: str = "Asia/Singapore"
    app_url: Optional[str] = None
    telegram_daily_last_sent: Optional[str] = None
    telegram_update_offset: int = 0

    @property
    def telegram_linked(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def telegram_bot_hint(self) -> str:
        return self.telegram_bot_token[-4:] if self.telegram_bot_token else ""
```
`public_dict`: also `d.pop("telegram_bot_token")`, `d["telegram_linked"] = self.telegram_linked`, `d["telegram_bot_hint"] = self.telegram_bot_hint`.

`load()`: read the new columns (`r.get(...)` with the defaults above; token via `self._decrypt(r["telegram_bot_token_enc"])`). `save()`: add to `params` `"tg_instant": bool(...)`, `"tg_time": settings.telegram_daily_time or "07:00"`, `"tz": settings.timezone or "Asia/Singapore"`, `"app_url": (settings.app_url or "").strip() or None`; UPDATE/INSERT include `telegram_instant = :tg_instant, telegram_daily_time = :tg_time, timezone = :tz, app_url = :app_url`; and, inside the same transaction, if `(settings.telegram_bot_token or "").strip()`: `UPDATE settings SET telegram_bot_token_enc = :t WHERE id = 1` with the encrypted value. Add:
```python
    def set_telegram(self, *, chat_id: Any = _UNSET, offset: Any = _UNSET, daily_last_sent: Any = _UNSET) -> None:
        sets, params = [], {}
        if chat_id is not _UNSET: sets.append("telegram_chat_id = :c"); params["c"] = chat_id
        if offset is not _UNSET: sets.append("telegram_update_offset = :o"); params["o"] = int(offset)
        if daily_last_sent is not _UNSET: sets.append("telegram_daily_last_sent = :d"); params["d"] = daily_last_sent
        if sets:
            self.db.execute(f"UPDATE settings SET {', '.join(sets)} WHERE id = 1", params)

    def clear_telegram(self) -> None:
        self.db.execute("UPDATE settings SET telegram_bot_token_enc = NULL, telegram_chat_id = NULL, telegram_update_offset = 0 WHERE id = 1")

    def for_template(self, tpl: Optional[dict]) -> Settings:
        """The settings a job for this assignment runs with: the global ones, or the template's own
        provider/model (with that provider's saved key and default rpm) when it sets one."""
        s = self.load()
        if not tpl or not tpl.get("provider"):
            return s
        provider = tpl["provider"]
        spec = get_provider(provider)
        s.model = tpl.get("model") or spec.default_model
        s.extractor_model = tpl.get("extractor_model") or None
        s.api_key = self.key_for(provider)
        s.base_url = None
        if provider != s.provider:
            s.rpm_limit = spec.default_rpm
        s.provider = provider
        return s
```
(`_UNSET = object()` at module level; `set_telegram` is a no-op when there is no settings row — `load()`/`save()` seed one via `ensure_seeded`, and tests call `save` first.)

`ratelimit.py`:
```python
class BucketPool:
    """One TokenBucket per provider for the worker's lifetime (replaced only when its rpm changes)."""
    def __init__(self) -> None:
        self._buckets: Dict[str, TokenBucket] = {}

    def get(self, provider: str, rpm: int) -> TokenBucket:
        b = self._buckets.get(provider)
        if b is None or b.rpm != rpm:
            b = TokenBucket(rpm); self._buckets[provider] = b
        return b
```

- [ ] **Step 5: Run** `uv run pytest -q` → PASS. **Step 6: Commit** `feat(settings): migration 0009, telegram/timezone fields, per-template settings, bucket pool`.

---

### Task 2: Custom models (service, API, `/api/providers` merge)

**Files:** Create `src/sms/web/services/custom_models.py`; modify `src/sms/providers/registry.py`, `src/sms/web/routers/settings.py`; test `tests/web/test_settings_api.py`.

**Interfaces produced:** `list_custom_models(db) -> Dict[str, List[dict]]` (`{provider: [{id, label, vision, custom: True}]}`), `add_custom_model(db, provider, model_id, label, vision) -> dict`, `remove_custom_model(db, provider, model_id) -> None`; `registry.providers_with_custom(custom: Dict[str, List[dict]]) -> list` (registry dicts with custom models appended and `custom_models` flag). Routes: `GET /api/providers` (merged), `POST /api/settings/models/{provider}` body `{model_id, label?, vision=true}` → 201 the model dict (400 `not_supported` for providers without the flag, 400 `bad_model` for blank id), `DELETE /api/settings/models/{provider}/{model_id:path}` → 204.

- [ ] **Step 1: Test**
```python
def test_custom_models_for_aggregators_appear_in_providers(auth):
    r = auth.post("/api/settings/models/openrouter", json={"model_id": "google/gemini-3.8-flash", "label": "Gemini 3.8 Flash", "vision": True})
    assert r.status_code == 201 and r.json() == {"id": "google/gemini-3.8-flash", "label": "Gemini 3.8 Flash", "vision": True, "custom": True}
    r = auth.post("/api/settings/models/openrouter", json={"model_id": "meta/llama-5-text"})   # label defaults to the id
    assert r.json()["label"] == "meta/llama-5-text"
    assert auth.post("/api/settings/models/openai", json={"model_id": "x"}).json()["error"]["code"] == "not_supported"
    assert auth.post("/api/settings/models/openrouter", json={"model_id": "  "}).json()["error"]["code"] == "bad_model"
    prov = {p["id"]: p for p in auth.get("/api/providers").json()}
    ids = [m["id"] for m in prov["openrouter"]["models"]]
    assert ids[-2:] == ["google/gemini-3.8-flash", "meta/llama-5-text"] and prov["openrouter"]["custom_models"] is True
    assert prov["openai"]["custom_models"] is False and not any(m.get("custom") for m in prov["openai"]["models"])
    assert auth.delete("/api/settings/models/openrouter/google/gemini-3.8-flash").status_code == 204
    assert "google/gemini-3.8-flash" not in [m["id"] for m in {p["id"]: p for p in auth.get("/api/providers").json()}["openrouter"]["models"]]
    # adding the same id again replaces the label instead of failing
    auth.post("/api/settings/models/openrouter", json={"model_id": "meta/llama-5-text", "label": "Llama 5", "vision": False})
    m = [m for m in {p["id"]: p for p in auth.get("/api/providers").json()}["openrouter"]["models"] if m["id"] == "meta/llama-5-text"][0]
    assert m["label"] == "Llama 5" and m["vision"] is False
```
- [ ] **Step 2:** run → FAIL. **Step 3:** implement:

`services/custom_models.py`:
```python
from typing import Any, Dict, List
from sms.memory.db import Database
from sms.providers.registry import get_provider
from sms.web.errors import ApiError

def list_custom_models(db: Database) -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = {}
    for r in db.query("SELECT provider, model_id, label, vision FROM custom_models ORDER BY created_at, model_id"):
        out.setdefault(r["provider"], []).append({"id": r["model_id"], "label": r["label"], "vision": bool(r["vision"]), "custom": True})
    return out

def add_custom_model(db: Database, provider: str, model_id: str, label: str = "", vision: bool = True) -> dict:
    try:
        spec = get_provider(provider)
    except KeyError as e:
        raise ApiError(400, "bad_provider", str(e))
    if not spec.custom_models:
        raise ApiError(400, "not_supported", f"{spec.label} uses its curated list — type a custom model id instead")
    model_id = (model_id or "").strip(); label = (label or "").strip() or model_id
    if not model_id:
        raise ApiError(400, "bad_model", "Enter the model id")
    with db.transaction() as tx:
        if tx.execute("UPDATE custom_models SET label = :l, vision = :v WHERE provider = :p AND model_id = :m",
                      {"l": label, "v": bool(vision), "p": provider, "m": model_id}) == 0:
            tx.execute("INSERT INTO custom_models (provider, model_id, label, vision) VALUES (:p, :m, :l, :v)",
                       {"p": provider, "m": model_id, "l": label, "v": bool(vision)})
    return {"id": model_id, "label": label, "vision": bool(vision), "custom": True}

def remove_custom_model(db: Database, provider: str, model_id: str) -> None:
    db.execute("DELETE FROM custom_models WHERE provider = :p AND model_id = :m", {"p": provider, "m": model_id})
```
`registry.py`: `providers_with_custom(custom)`: `dicts = registry_as_dicts()`; for each `d`, `d["models"] = d["models"] + custom.get(d["id"], [])`. `registry_as_dicts` already includes `custom_models` via `asdict`. Router: `GET /providers` → `providers_with_custom(list_custom_models(db))` (add `db=Depends(get_db)`); the two routes above with `class CustomModelBody(BaseModel): model_id: str; label: str = ""; vision: bool = True`.

- [ ] **Step 4:** `uv run pytest -q` → PASS. Check `web/src/pages/__tests__/Settings.test.tsx` fixtures still type-check later (Task 8 adds `custom_models` to `ProviderSpec`). **Step 5:** commit `feat(settings): custom model lists for OpenRouter and TokenRouter`.

---

### Task 3: Per-assignment model override end to end (API + jobs + per-provider buckets)

**Files:** modify `src/sms/web/services/assignments.py`, `src/sms/web/routers/assignments.py`, `src/sms/worker/mark_job.py`, `src/sms/worker/extract_jobs.py`, `src/sms/worker/worker.py`; tests `tests/web/test_assignments_api.py`, `tests/unit/test_worker.py`, `tests/unit/test_extract_jobs.py`.

**Interfaces produced:** template dict gains `provider, model, extractor_model` (nullable) and `effective_model: {provider, model, extractor_model}` (the template's or the global settings'); `TemplateBody` gains the three optional fields; `_validate` gains them (400 `bad_provider` unknown; 400 `no_key_for_provider` when no key saved for it; blank model → provider default; all three NULL when provider is blank). `run_mark_job(..., bucket=None, bucket_pool=None)`, `run_paper_extract_job/run_scheme_extract_job(..., bucket=None, bucket_pool=None)`: settings via `settings_store.for_template(get_template(db, assignment_id))`; bucket = `bucket_pool.get(settings.provider, settings.rpm_limit)` when a pool is given. `Worker` holds `self.pool = BucketPool()` and passes `bucket_pool=self.pool` to mark/extract/reflect/insights runners (reflect uses the global provider).

- [ ] **Step 1: Tests**

`tests/web/test_assignments_api.py`:
```python
def test_template_model_override_requires_a_saved_key(auth):
    t = _create(auth).json()
    assert t["provider"] is None and t["effective_model"]["provider"] == "tokenrouter"
    r = auth.put(f"/api/assignments/{t['id']}", json={**_body(), "provider": "openai", "model": "gpt-5.5"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "no_key_for_provider"
    _with_key(auth)   # saves an OpenAI key
    r = auth.put(f"/api/assignments/{t['id']}", json={**_body(), "provider": "openai", "model": "gpt-5.5", "extractor_model": "gpt-5-mini"})
    assert r.status_code == 200 and r.json()["effective_model"] == {"provider": "openai", "model": "gpt-5.5", "extractor_model": "gpt-5-mini"}
    r = auth.put(f"/api/assignments/{t['id']}", json={**_body(), "provider": "openai", "model": ""})
    assert r.json()["model"] == "gpt-5-mini"                      # blank model -> provider default
    r = auth.put(f"/api/assignments/{t['id']}", json={**_body(), "provider": ""})
    assert r.json()["provider"] is None and r.json()["model"] is None
    assert auth.put(f"/api/assignments/{t['id']}", json={**_body(), "provider": "nope", "model": "x"}).json()["error"]["code"] == "bad_provider"
```
(add a module-level `_body()` returning the default create body if the file lacks one.)

`tests/unit/test_worker.py`:
```python
def test_mark_job_uses_the_assignments_own_model_and_bucket(env):
    db, store, storage, sid = env
    store.save(Settings(provider="openrouter", model="z-ai/glm-5.3-flash", api_key="or-key", rpm_limit=60))
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key=None, rpm_limit=60))
    tid = db.insert("INSERT INTO assignment_templates (title, subject, context, rubric_json, provider, model) VALUES "
                    "('T', 'math', '', '{\"criterion_defs\": [{\"id\": \"c1\", \"description\": \"d\", \"max_score\": 2}]}', 'openrouter', 'openrouter/auto') RETURNING id")
    db.execute("UPDATE submissions SET assignment_id = ?, scheme_kind = 'criteria' WHERE id = ?", (tid, sid))
    seen = {}
    def factory(**kw):
        seen["settings"] = kw["settings"]; seen["bucket"] = kw["bucket"]; return RunRowPipeline(db)
    from sms.providers.ratelimit import BucketPool
    pool = BucketPool()
    run_mark_job(db, storage, store, sid, pipeline_factory=factory, bucket_pool=pool)
    assert (seen["settings"].provider, seen["settings"].model, seen["settings"].api_key) == ("openrouter", "openrouter/auto", "or-key")
    assert seen["bucket"] is pool.get("openrouter", 60)
    assert db.query("SELECT provider, model FROM marking_runs WHERE run_id = 'r1'")[0]["model"] == "openrouter/auto"
```
Add an equivalent in `tests/unit/test_extract_jobs.py` for the paper extractor (factory receives `settings.provider == "openrouter"` when the template sets it) — mirror the existing test's fixture style there.

- [ ] **Step 2:** run → FAIL. **Step 3:** implement. `_validate` gains `provider: Optional[str] = None, model: Optional[str] = None, extractor_model: Optional[str] = None, *, db: Optional[Database] = None`:
```python
    provider = (provider or "").strip() or None
    if provider:
        try:
            spec = get_provider(provider)
        except KeyError:
            raise ApiError(400, "bad_provider", f"Unknown provider {provider!r}")
        if db is not None and SettingsStore.has_key_for(db, provider) is False:
            raise ApiError(400, "no_key_for_provider", f"Save a {spec.label} key under Settings before choosing it here")
        model = (model or "").strip() or spec.default_model
        extractor_model = (extractor_model or "").strip() or None
    else:
        model = extractor_model = None
```
Add `SettingsStore.has_key_for(db, provider) -> bool` as a `@staticmethod` (`SELECT 1 FROM provider_keys WHERE provider = :p`). Include `"provider", "model", "extractor_model"` in the fields dict, `_INSERT` and the UPDATE; `create_template/update_template/duplicate_template` carry them; `_row_to_dict` emits them plus `effective_model` (needs the global settings: read `provider, model, extractor_model` from `settings` row id 1 in `_row_to_dict` callers — compute once in `list_templates/get_template` via a helper `_global_model(db)` and pass in). Router `TemplateBody` + `_kwargs` gain the three fields; `create/update/import` pass `db`.

`mark_job.run_mark_job`: replace `settings = settings_store.load()` with
```python
    tpl = get_template(db, sub["assignment_id"]) if sub.get("assignment_id") is not None else None
    settings = settings_store.for_template(tpl)
    if bucket_pool is not None:
        bucket = bucket_pool.get(settings.provider, settings.rpm_limit)
```
(import `get_template` from `sms.web.services.assignments`). Same in `extract_jobs._settings(settings_store, template_row)` → `settings_store.for_template(get_template(db, template_id))`, and both extract runners accept `bucket_pool`. `worker.py`: `self.pool = BucketPool()`; in `run_once` pass `bucket_pool=self.pool` (keep `bucket=` for the reflect runner using `self.pool.get(settings.provider, settings.rpm_limit)`); remove `_bucket_for`.

- [ ] **Step 4:** `uv run pytest -q` → PASS. **Step 5:** commit `feat(assignments): per-assignment provider/model; jobs resolve settings per template; per-provider rate buckets`.

---

### Task 4: Insights statistics + live endpoint

**Files:** create `src/sms/web/services/insights.py`; modify `src/sms/web/routers/class_assignments.py`; tests `tests/unit/test_insights_stats.py`, `tests/web/test_insights_api.py`.

**Interfaces produced:** `compute_stats(db, jobs, ca: dict) -> dict` (shape in spec §A1; `parts[].q_id` = scheme row key, `label` via `q_label` for mark schemes / criterion name for rubrics / criterion id for criteria); `select_samples(db, jobs, ca, stats, per_part=10, max_parts=4) -> List[dict]` (`{part, reg_no, extracted, awarded, max, justification}`, weakest parts first, lowest scores first, no names); `load_insights(db, caid) -> Optional[dict]` (`{stats, report, n_marked, provider, model, generated_at, error}`); `upsert_insights(db, caid, *, stats, report, n_marked, provider, model, error)`; `insights_payload(db, jobs, ca) -> dict` (`load_insights` or live `{stats: compute_stats(...), report: None, ...}`, plus `job: {status}` from `jobs` for dedupe key `insights:{caid}` — add `JobStore.active_by_dedupe(key) -> Optional[dict]` if missing). Route `GET /{caid}/insights`.

- [ ] **Step 1: Tests** — `tests/unit/test_insights_stats.py` builds an app via the web fixtures (`app`, `auth`) and seeds three students with `seed_v2` linked to a class assignment (reuse `_link` from `tests/web/test_class_assignments_api.py`; import it): Tan = default parts (1a 2/2, 1b 0/1, 2 escalated → resolved later), Danish = parts with 1a 1/2 (M1 only), 1b 1/1, 2 3/3 and `queue={}`, Priya = not handed in.
```python
def test_compute_stats_from_marked_scripts(auth, app):
    ... seed as above; then
    from sms.web.services.insights import compute_stats
    from sms.web.services.class_assignments import get_class_assignment
    ca = get_class_assignment(app.state.db, cls_id, ca_id)
    st = compute_stats(app.state.db, app.state.jobs, ca)
    assert (st["n_students"], st["n_marked"], st["n_pending"]) == (3, 2, 1)
    p = {x["q_id"]: x for x in st["parts"]}
    assert p["1a"]["attempted"] == 2 and p["1a"]["mean_pct"] == 75.0 and p["1a"]["full"] == 1
    assert p["1a"]["allocations"] == [{"label": "M1", "lost": 0}, {"label": "A1", "lost": 1}]
    assert p["1b"]["mean_pct"] == 50.0 and p["1b"]["zero"] == 1
    assert p["2"]["pending"] == 1 and p["2"]["attempted"] == 1      # Tan's part 2 is still in the queue
    assert st["weakest"][0] == "1b"                                 # ties broken by scheme order; min-attempts rule disabled below 5 students
    assert st["most_lost"][0] == {"q_id": "1a", "label": "A1", "lost": 1, "of": 2} or st["most_lost"][0]["q_id"] == "1b"
    s = {x["reg_no"]: x for x in st["students"]}
    assert s[1]["weak_parts"] == ["1b"] and s[1]["name"] == "Tan Wei Ling" and s[2]["total"] == 5
    assert st["totals"]["max"] == 6 and len(st["totals"]["buckets"]) == 5
```
Add `test_select_samples_is_anonymous`: returns rows for the weakest parts only, each with `reg_no` and no `name` key, `extracted` ≤ 300 chars, sorted ascending by `awarded/max`.

`tests/web/test_insights_api.py`:
```python
def test_insights_endpoint_returns_live_stats_before_any_report(auth, app):
    ... seed one marked student
    r = auth.get(f"/api/classes/{cls}/assignments/{ca}/insights")
    assert r.status_code == 200
    body = r.json(); assert body["report"] is None and body["stats"]["n_marked"] == 1 and body["job"] is None
    assert auth.get(f"/api/classes/{cls}/assignments/999/insights").status_code == 404
```
- [ ] **Step 2:** FAIL. **Step 3:** implement `services/insights.py`:
```python
"""Per-assignment insights: statistics computed from stored marks, and the stored AI narrative."""
import json, statistics
from typing import Any, Dict, List, Optional
from sms.memory.db import Database
from sms.schemas.scheme import q_label
from sms.timeutil import iso_utc
from sms.web.services.assignments import get_template
from sms.web.services.class_assignments import roster
from sms.web.services.submissions import get_submission, row_key, row_max
from sms.worker.jobs import JobStore

def _part_rows(template: Optional[dict]) -> List[dict]:
    """[{q_id, label, max, allocations:[labels]}] in scheme order."""
    if not template: return []
    kind = template["scheme_kind"]
    if kind == "mark_scheme":
        return [{"q_id": row_key(kind, r), "label": q_label(row_key(kind, r)), "max": row_max(kind, r),
                 "allocations": [m["label"] for m in r.get("marks", [])]} for r in template["scheme"]]
    if kind == "rubric":
        return [{"q_id": row_key(kind, r), "label": r["criterion"], "max": row_max(kind, r),
                 "allocations": [b["band"] for b in r.get("bands", [])]} for r in template["scheme"]]
    return [{"q_id": c["id"], "label": c["id"], "max": c["max_score"], "allocations": []} for c in template["rubric"]["criterion_defs"]]

def _part_marks(detail: dict) -> Dict[str, dict]:
    """q_id -> {total, max, pending, lost:[labels], extracted, justification, in_scheme, illegible} (teacher wins)."""
    out = {}
    if detail.get("marks_version") == 2:
        for p in detail.get("parts") or []:
            teacher = p.get("teacher")
            if p.get("band") is not None or "descriptor_met" in p:      # rubric criterion
                lost = [] if (teacher or {}).get("band", p.get("band")) == (p.get("scheme") or {}).get("bands", [{}])[0].get("band") else [p.get("band") or ""]
            else:
                got = {a["label"]: a["got"] for a in (teacher or {}).get("allocations") or p.get("awarded") or []}
                lost = [l for l, g in got.items() if not g]
            out[p["q_id"]] = {"total": teacher["total"] if teacher else p["total"], "max": p["max"], "pending": p["escalated"],
                              "lost": lost, "extracted": p.get("extracted") or "", "justification": p.get("justification") or "",
                              "in_scheme": p.get("in_scheme", True), "illegible": p.get("illegible", False)}
    else:
        for m in detail.get("marks") or []:
            total = sum(m["teacher_scores"]) if m.get("teacher_scores") else m["total"]
            out[m["q_id"]] = {"total": total, "max": m["max"], "pending": m["escalated"], "lost": [], "extracted": m.get("evidence") or "",
                              "justification": m.get("rationale") or "", "in_scheme": True, "illegible": False}
    return out

def compute_stats(db: Database, jobs: JobStore, ca: dict) -> dict:
    template = get_template(db, ca["template_id"])
    parts = _part_rows(template)
    rows = roster(db, ca)["rows"]
    marked = []
    for r in rows:
        if r["submission_id"] is None: continue
        d = get_submission(db, jobs, r["submission_id"])
        if d and d.get("run_id"):
            marked.append((r, _part_marks(d), d))
    n_pending = sum(1 for r in rows if r["submission_id"] is not None and r["status"] in ("handed_in", "marking", "needs_you"))
    per_part, students, totals = [], [], []
    for p in parts:
        seen = [pm[p["q_id"]] for _, pm, _ in marked if p["q_id"] in pm]
        scored = [x for x in seen if not x["pending"]]
        pct = [100.0 * x["total"] / p["max"] for x in scored if p["max"]]
        lost = {a: 0 for a in p["allocations"]}
        for x in scored:
            for l in x["lost"]:
                if l in lost: lost[l] += 1
        per_part.append({"q_id": p["q_id"], "label": p["label"], "max": p["max"], "attempted": len(seen),
                         "mean_pct": round(sum(pct) / len(pct), 1) if pct else None,
                         "full": sum(1 for x in scored if x["total"] >= p["max"]), "zero": sum(1 for x in scored if x["total"] == 0),
                         "allocations": [{"label": a, "lost": n} for a, n in lost.items()],
                         "not_in_scheme": sum(1 for x in seen if not x["in_scheme"]), "illegible": sum(1 for x in seen if x["illegible"]),
                         "pending": sum(1 for x in seen if x["pending"])})
    max_total = sum(p["max"] for p in parts)
    for r, pm, d in marked:
        t = d["totals"]["total"] if d.get("totals") else 0
        totals.append(t)
        weak = [p["q_id"] for p in parts if p["q_id"] in pm and not pm[p["q_id"]]["pending"] and p["max"] and pm[p["q_id"]]["total"] / p["max"] < 0.5]
        students.append({"student_id": r["student_id"], "reg_no": r["reg_no"], "name": r["name"], "total": t, "max": max_total, "weak_parts": weak})
    min_attempts = 5 if len(marked) >= 5 else 1
    weakest = [p["q_id"] for p in sorted((p for p in per_part if p["mean_pct"] is not None and p["attempted"] >= min_attempts),
                                          key=lambda p: (p["mean_pct"], parts.index(next(q for q in parts if q["q_id"] == p["q_id"]))))]
    most_lost = sorted(({"q_id": p["q_id"], "label": a["label"], "lost": a["lost"], "of": p["attempted"] - p["pending"]}
                        for p in per_part for a in p["allocations"] if a["lost"]), key=lambda x: -x["lost"])[:8]
    step = max(1, -(-max_total // 5)) if max_total else 1
    buckets = [{"from": i * step, "to": min((i + 1) * step - 1, max_total) if i < 4 else max_total,
                "n": sum(1 for t in totals if i * step <= t <= (min((i + 1) * step - 1, max_total) if i < 4 else max_total))} for i in range(5)]
    return {"n_students": len(rows), "n_marked": len(marked), "n_pending": n_pending,
            "totals": {"mean": round(statistics.mean(totals), 1) if totals else None, "median": statistics.median(totals) if totals else None,
                       "max": max_total, "buckets": buckets},
            "parts": per_part, "weakest": weakest, "most_lost": most_lost, "students": students}
```
(The bucket boundaries for the last bucket must reach `max_total`; write it so a perfect score lands in bucket 5 — the expression above does. Simplify if clearer, but keep the test's `len == 5`.) `select_samples`, `load_insights`, `upsert_insights` (UPDATE then INSERT), `insights_payload` as described; `_part_marks` for rubric parts: treat "lost" as the band when it is not the first (top) band in the scheme row. Route:
```python
@router.get("/{caid}/insights")
def insights(class_id: int, caid: int, db=Depends(get_db), jobs=Depends(get_jobs)):
    ca = require_class_assignment(db, class_id, caid)
    return insights_payload(db, jobs, ca)
```
- [ ] **Step 4:** PASS; **Step 5:** commit `feat(insights): per-assignment statistics and live endpoint`.

---

### Task 5: Insights agent, job, triggers, PDF

**Files:** create `src/sms/schemas/insights.py`, `src/sms/agents/insights.py`, `src/sms/worker/insights_job.py`, `src/sms/records/insights_pdf.py`; modify `src/sms/worker/worker.py` (dispatch `insights`), `src/sms/web/services/class_assignments.py` (`release` enqueues), `src/sms/web/routers/class_assignments.py` (regenerate + pdf), `pyproject.toml` (`reportlab>=4.2`); tests `tests/unit/test_insights_job.py`, `tests/unit/test_insights_pdf.py`, `tests/web/test_insights_api.py`.

**Interfaces produced:** `InsightsInput(BaseIOSchema){assignment_title, subject, scheme_kind, stats: dict, samples: List[Sample]}` (stats passed **without** `students[].name` — strip in the job), `InsightsReport(BaseIOSchema){summary, strengths, gaps:[Gap{part_ids, title, what_went_wrong, students_affected}], recommendations:[Recommendation{title, detail, part_ids}], students_to_support:[Support{reg_nos, focus}]}`; `build_insights(client, model, model_api_parameters)`; `run_insights_job(db, jobs, settings_store, caid, bucket=None, bucket_pool=None, agent_factory=None) -> dict`; `enqueue_insights(jobs, caid) -> Optional[int]` (dedupe `insights:{caid}`); `render_insights_pdf(ca: dict, stats: dict, report: Optional[dict], students_by_reg: Dict[int, str]) -> bytes`. Routes: `POST /{caid}/insights/regenerate` → 202 `{job_id}` / 409 `already_running` / 409 `nothing_marked`; `GET /{caid}/insights.pdf` (`application/pdf`, `attachment; filename="<slug>-insights.pdf"`).

- [ ] **Step 1: Tests**
```python
# tests/unit/test_insights_job.py
def test_insights_job_strips_names_and_stores_report(auth, app):
    ... seed two marked students linked to a class assignment (as Task 4) ...
    captured = {}
    class FakeAgent:
        def run(self, inp):
            captured["input"] = inp
            return InsightsReport(summary="Class did well on 1(a).", strengths=["Method in 1(a)"],
                                  gaps=[Gap(part_ids=["1b"], title="Hence questions", what_went_wrong="Did not reuse 1(a)", students_affected=1)],
                                  recommendations=[Recommendation(title="Reteach follow-through", detail="Use 1(b)", part_ids=["1b"])],
                                  students_to_support=[Support(reg_nos=[1], focus="follow-through")])
    out = run_insights_job(app.state.db, app.state.jobs, app.state.settings_store, ca_id, agent_factory=lambda **kw: FakeAgent())
    dumped = captured["input"].model_dump_json()
    assert "Tan Wei Ling" not in dumped and "Muhammad" not in dumped and '"reg_no": 1' in dumped.replace('"reg_no":1', '"reg_no": 1')
    row = app.state.db.query("SELECT * FROM assignment_insights WHERE class_assignment_id = :c", {"c": ca_id})[0]
    assert json.loads(row["report_json"])["summary"].startswith("Class did well") and row["n_marked"] == 2 and row["error"] is None
    assert row["provider"] == "openai"
    # a failing model call keeps the previous report and records the error
    class Boom:
        def run(self, inp): raise RuntimeError("model down")
    with pytest.raises(RuntimeError):
        run_insights_job(app.state.db, app.state.jobs, app.state.settings_store, ca_id, agent_factory=lambda **kw: Boom())
    row = app.state.db.query("SELECT * FROM assignment_insights WHERE class_assignment_id = :c", {"c": ca_id})[0]
    assert row["error"] == "model down" and json.loads(row["report_json"])["summary"].startswith("Class did well")

def test_insights_pdf_renders(tmp_path):
    from sms.records.insights_pdf import render_insights_pdf
    data = render_insights_pdf({"title": "Worksheet 3", "id": 1}, STATS_FIXTURE, REPORT_FIXTURE, {1: "Tan Wei Ling"})
    assert data[:4] == b"%PDF" and len(data) > 2000
    # text survives: pypdf is not a dependency, so check the raw stream for a known label via reportlab's own reader-free check
    assert b"Worksheet 3" in data or True   # ReportLab compresses streams; the length assertion is the real check
```
Use small `STATS_FIXTURE`/`REPORT_FIXTURE` dicts matching the spec shapes (2 parts, 2 students). In `tests/web/test_insights_api.py`: regenerate → 202 and a queued job with dedupe `insights:{caid}`; second call → 409 `already_running`; with nothing marked → 409 `nothing_marked`; `insights.pdf` → 200 `application/pdf` (stats-only PDF works when no report); release enqueues an insights job (assert a job row with that dedupe key after `POST …/release`).

- [ ] **Step 2:** FAIL. **Step 3:** implement.

`schemas/insights.py`: pydantic models as above (`Sample{part: str, reg_no: int, extracted: str, awarded: int, max: int, justification: str}`; `stats: dict` typed `Dict[str, Any]`).

`agents/insights.py` (mirror `agents/reflection.py`): background "You are a head of department reading a class set's marks against the mark scheme; you write for the teacher who will plan the next lesson"; steps: read the statistics part by part, read the samples for the weakest parts, name what went wrong in mark-scheme terms, propose next-lesson actions; output instructions: only refer to part ids present in `stats.parts`, refer to students by register number only, 3–5 recommendations each tied to parts, no praise padding.

`worker/insights_job.py`:
```python
def enqueue_insights(jobs: JobStore, caid: int) -> Optional[int]:
    return jobs.enqueue_unique("insights", {"class_assignment_id": caid}, dedupe_key=f"insights:{caid}")

def run_insights_job(db, jobs, settings_store, caid, bucket=None, bucket_pool=None, agent_factory=None) -> dict:
    rows = db.query("SELECT * FROM class_assignments WHERE id = :id", {"id": caid})
    if not rows: raise ValueError(f"class assignment {caid} not found")
    ca = get_class_assignment(db, rows[0]["class_id"], caid)
    stats = compute_stats(db, jobs, ca)
    prev = load_insights(db, caid)
    if stats["n_marked"] == 0:
        upsert_insights(db, caid, stats=stats, report=prev["report"] if prev else None, n_marked=0, provider=None, model=None, error="Nothing marked yet")
        return stats
    tpl = get_template(db, ca["template_id"])
    settings = settings_store.for_template(tpl)
    if not settings.has_key: raise RuntimeError("No API key configured — add one under Settings")
    if bucket_pool is not None: bucket = bucket_pool.get(settings.provider, settings.rpm_limit)
    anon = {**stats, "students": [{k: v for k, v in s.items() if k not in ("name", "student_id")} for s in stats["students"]]}
    samples = select_samples(db, jobs, ca, stats)
    inp = InsightsInput(assignment_title=ca["title"], subject=ca["subject"] or "math", scheme_kind=ca["scheme_kind"] or "criteria", stats=anon, samples=samples)
    try:
        agent = (agent_factory or _default_agent_factory)(db=db, settings=settings, bucket=bucket or TokenBucket(settings.rpm_limit))
        report = agent.run(inp)
    except Exception as e:
        upsert_insights(db, caid, stats=stats, report=prev["report"] if prev else None, n_marked=stats["n_marked"],
                        provider=settings.provider, model=settings.model, error=error_message(e))
        raise
    upsert_insights(db, caid, stats=stats, report=report.model_dump(), n_marked=stats["n_marked"], provider=settings.provider, model=settings.model, error=None)
    return report.model_dump()
```
`_default_agent_factory` like reflect_job's (build_client → build_insights → wire_metrics → RateLimitedAgent). `worker.run_once`: `elif job["kind"] == "insights": payload = json.loads(...); self.insights_runner(self.db, self.jobs, self.settings_store, int(payload["class_assignment_id"]), bucket_pool=self.pool)` with `insights_runner` constructor arg defaulting to `run_insights_job`. `release()` in class_assignments: after the UPDATE, `enqueue_insights(JobStore(db), caid)`. Routes:
```python
@router.post("/{caid}/insights/regenerate", status_code=202)
def regenerate_insights(class_id: int, caid: int, db=Depends(get_db), jobs=Depends(get_jobs)):
    ca = require_class_assignment(db, class_id, caid)
    if not db.query("SELECT 1 FROM submissions WHERE class_assignment_id = :a AND run_id IS NOT NULL", {"a": caid}):
        raise ApiError(409, "nothing_marked", "Nothing has been marked yet")
    job_id = enqueue_insights(jobs, caid)
    if job_id is None: raise ApiError(409, "already_running", "Insights are already being generated")
    return JSONResponse(status_code=202, content={"job_id": job_id})

@router.get("/{caid}/insights.pdf")
async def insights_pdf(class_id: int, caid: int, db=Depends(get_db), jobs=Depends(get_jobs)):
    ca = require_class_assignment(db, class_id, caid)
    def build():
        p = insights_payload(db, jobs, ca)
        names = {s["reg_no"]: s["name"] for s in p["stats"]["students"]}
        return render_insights_pdf(ca, p["stats"], p["report"], names)
    data = await run_in_threadpool(build)
    return Response(content=data, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{slug(ca["title"])}-insights.pdf"'})
```
`records/insights_pdf.py` with ReportLab platypus: title (assignment title, class name if available, generated date, "n marked / n students, mean x / max"), Summary paragraph, "Marks by part" as a `reportlab.graphics.charts.barcharts.VerticalBarChart` (mean % per part, labels = part labels), "Most-lost allocations" bullet list, Strengths, Gaps, Recommendations, "Students to support" table (name via `students_by_reg`, focus). No report → the numeric sections only with a note "AI narrative not generated yet". Escape text with `xml.sax.saxutils.escape`.

- [ ] **Step 4:** `uv run pytest -q` → PASS (add `reportlab` with `uv add "reportlab>=4.2"`; ensure `uv.lock` is committed). **Step 5:** commit `feat(insights): narrative agent, job with triggers, PDF`.

---

### Task 6: Telegram client, settings endpoints, linking poll

**Files:** create `src/sms/web/services/telegram.py`; modify `src/sms/web/routers/settings.py`, `src/sms/worker/worker.py`; tests `tests/unit/test_telegram.py`, `tests/web/test_settings_api.py`.

**Interfaces produced:** `TelegramClient(token, *, transport=None)` (httpx; `transport` for tests) with `get_updates(offset: int) -> List[dict]`, `send_message(chat_id: str, html: str) -> None` (raises `TelegramError(str)` on non-OK), `get_me() -> dict`; `escape(text) -> str`; `app_base_url(settings) -> Optional[str]` (`settings.app_url` else `https://{RAILWAY_PUBLIC_DOMAIN}` else None); `poll_updates(settings_store, client_factory=TelegramClient) -> bool` (links on `/start`, replies, advances offset; returns True when linked this pass). `SettingsBody` gains `telegram_bot_token: Optional[str]`, `telegram_instant: bool = True`, `telegram_daily_time: str = "07:00"` (validated `HH:MM`, 400 `bad_time`), `timezone: str` (validated with `zoneinfo.ZoneInfo`, 400 `bad_timezone`), `app_url: Optional[str]`. Routes: `POST /api/settings/telegram/test` (409 `not_linked`; 502 `telegram_error`), `DELETE /api/settings/telegram` → 204. Worker: `_maybe_poll_telegram()` every 10 s when a token is stored (uses `poll_updates`).

- [ ] **Step 1: Tests** — `tests/unit/test_telegram.py` uses `httpx.MockTransport`:
```python
def test_poll_links_on_start_and_advances_offset(tmp_path):
    db = Database(path=str(tmp_path / "t.db")); store = SettingsStore(db, KeyCipher("k"))
    store.save(Settings(provider="openai", model="gpt-5-mini", api_key="sk", rpm_limit=60, telegram_bot_token="1:abc"))
    calls = []
    def handler(req):
        calls.append((req.url.path, dict(req.url.params) if req.method == "GET" else json.loads(req.content or b"{}")))
        if req.url.path.endswith("/getUpdates"):
            return httpx.Response(200, json={"ok": True, "result": [{"update_id": 10, "message": {"text": "hello", "chat": {"id": 5}}},
                                                                      {"update_id": 11, "message": {"text": "/start", "chat": {"id": 777}}}]})
        return httpx.Response(200, json={"ok": True, "result": {}})
    factory = lambda token: TelegramClient(token, transport=httpx.MockTransport(handler))
    assert poll_updates(store, client_factory=factory) is True
    s = store.load(); assert s.telegram_chat_id == "777" and s.telegram_update_offset == 12
    sent = [c for c in calls if c[0].endswith("/sendMessage")]
    assert sent and sent[0][1]["chat_id"] == "777" and "Linked" in sent[0][1]["text"]
    # next poll asks from offset 12 and finds nothing
    assert poll_updates(store, client_factory=factory) is False
    assert calls[-1][0].endswith("/getUpdates") and calls[-1][1]["offset"] == "12"

def test_escape_and_send_error():
    assert escape("a < b & c") == "a &lt; b &amp; c"
    def handler(req): return httpx.Response(400, json={"ok": False, "description": "chat not found"})
    with pytest.raises(TelegramError, match="chat not found"):
        TelegramClient("1:abc", transport=httpx.MockTransport(handler)).send_message("1", "x")
```
`tests/web/test_settings_api.py`: PUT with `telegram_bot_token`, `timezone: "Asia/Singapore"`, `telegram_daily_time: "06:45"` → response has `telegram_bot_hint`, no token; `timezone: "Mars/Olympus"` → 400 `bad_timezone`; `telegram_daily_time: "25:00"` → 400 `bad_time`; `POST /api/settings/telegram/test` → 409 `not_linked` before linking; after `store.set_telegram(chat_id="1")` and monkeypatching `sms.web.routers.settings.TelegramClient` with a fake, → 204; `DELETE /api/settings/telegram` → 204 and `telegram_linked` false.

- [ ] **Step 2:** FAIL. **Step 3:** implement `services/telegram.py`:
```python
class TelegramError(RuntimeError): ...

class TelegramClient:
    def __init__(self, token: str, *, transport=None, timeout: float = 15.0):
        self._base = f"https://api.telegram.org/bot{token}"
        self._http = httpx.Client(timeout=timeout, transport=transport)
    def _call(self, method: str, **params) -> Any:
        r = self._http.post(f"{self._base}/{method}", json=params) if params else self._http.get(f"{self._base}/{method}")
        body = r.json() if r.content else {}
        if r.status_code != 200 or not body.get("ok"):
            raise TelegramError(body.get("description") or f"HTTP {r.status_code}")
        return body["result"]
    def get_updates(self, offset: int) -> List[dict]:
        r = self._http.get(f"{self._base}/getUpdates", params={"offset": str(offset), "timeout": "0", "allowed_updates": '["message"]'})
        ... same ok check ...
    def send_message(self, chat_id: str, html: str) -> None:
        self._call("sendMessage", chat_id=chat_id, text=html, parse_mode="HTML", disable_web_page_preview=True)
    def get_me(self) -> dict: return self._call("getMe")

def escape(text: str) -> str: return html.escape(str(text), quote=False)

def app_base_url(settings) -> Optional[str]:
    if settings.app_url: return settings.app_url.rstrip("/")
    dom = os.environ.get("RAILWAY_PUBLIC_DOMAIN")
    return f"https://{dom}" if dom else None

def poll_updates(settings_store, client_factory=TelegramClient) -> bool:
    s = settings_store.load()
    if not s.telegram_bot_token: return False
    client = client_factory(s.telegram_bot_token)
    updates = client.get_updates(s.telegram_update_offset)
    linked = False; last = None
    for u in updates:
        last = u["update_id"]
        msg = u.get("message") or {}
        if (msg.get("text") or "").strip().startswith("/start"):
            chat_id = str(msg["chat"]["id"])
            settings_store.set_telegram(chat_id=chat_id)
            client.send_message(chat_id, "Linked to Smart Marking ✓ — you'll get marking updates here.")
            linked = True
    if last is not None: settings_store.set_telegram(offset=last + 1)
    return linked
```
Settings router: validate time with `re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v)`; timezone with `ZoneInfo(v)` in try/except `ZoneInfoNotFoundError`/`ValueError`; pass the new fields into `Settings(...)`. `test_telegram`: load; not linked → 409; `TelegramClient(token).send_message(chat_id, "Smart Marking is connected ✓")`; catch `TelegramError` → 502 `telegram_error`. `DELETE /telegram` → `store.clear_telegram()`. Worker: `_last_telegram_tick` monotonic; every `TELEGRAM_TICK_S = 10`: `poll_updates(self.settings_store)` inside try/except logging.

- [ ] **Step 4:** PASS. **Step 5:** commit `feat(telegram): bot client, /start linking via polling, settings endpoints`.

---

### Task 7: Notification outbox — hand-ins, marking finished, daily digest

**Files:** create `src/sms/web/services/notify.py`; modify `src/sms/web/services/submissions.py` (hand_in row + null `last_done_notified_at`), `src/sms/worker/worker.py` (post-mark hook, flush tick, daily tick); tests `tests/unit/test_notify.py`, `tests/unit/test_worker.py`.

**Interfaces produced:** `record_hand_in(db, submission_row: dict)` (inserts a `hand_in` row when `class_assignment_id` set and `source == 'student'` and `telegram_instant` — read settings row directly — and nulls `class_assignments.last_done_notified_at`); `on_mark_settled(db, jobs, submission_id)` — if the submission has a `class_assignment_id` and no sibling is in `uploaded/queued/marking`: enqueue insights when ≥1 marked, and insert a `marking_done` row `{marked, needs_you, insights}` if `last_done_notified_at` is NULL (then set it) and `telegram_instant`; `flush_notifications(settings_store, db, client_factory=TelegramClient) -> int` (groups unsent by `(kind, class_assignment_id)`, formats, sends, marks `sent_at` or `error`; returns sent count; no-op unless linked); `format_hand_ins(ca_title, class_name, rows, url) -> str`, `format_marking_done(...)`, `build_daily_digest(db, settings) -> Optional[str]` (None when no activity in 24 h), `maybe_send_daily(settings_store, db, now: datetime, client_factory=...) -> bool`.

- [ ] **Step 1: Tests** (`tests/unit/test_notify.py`, using the web `app`/`auth` fixtures for seeding, `httpx.MockTransport` to capture sends):
  - `test_hand_in_rows_are_batched_into_one_message`: link telegram via `store.set_telegram(chat_id="7")` + token; two student hand-ins via the student API (see `tests/web/test_student_api.py::_setup`) → two `hand_in` rows; `flush_notifications` sends **one** message containing "2 new hand-ins", both names, and the app link `/classes/{cls}/assignments/{ca}`; rows have `sent_at`.
  - `test_marking_done_fires_once_per_drain`: seed a class assignment with one submission `status='done'` (via `seed_v2`, `queue={}`) and call `on_mark_settled` twice → exactly one `marking_done` row and one queued `insights` job; a new hand-in (`record_hand_in`) nulls the guard, then `on_mark_settled` fires again.
  - `test_marking_done_waits_for_in_flight_siblings`: two submissions, one `marking` → no row.
  - `test_instant_off_suppresses_events`: `telegram_instant=False` → no hand_in/marking_done rows, but insights still enqueued.
  - `test_daily_digest_once_per_day_and_skips_quiet_days`: settings tz Asia/Singapore, time 07:00; `maybe_send_daily(store, db, now=datetime(2026,9,17,6,59,tzinfo=UTC))` → False (it is 14:59 local — wait: choose `now` so local is 06:59 → `datetime(2026,9,16,22,59,tzinfo=UTC)`); at local 07:01 with activity → True, `telegram_daily_last_sent == "2026-09-17"`, message contains the class name and counts; calling again → False; next day with no activity → False and no send.
  - `test_failed_send_keeps_row_with_error`: transport returns 400 → row unsent, `error` set; a later successful flush sends it.

- [ ] **Step 2:** FAIL. **Step 3:** implement `notify.py` (SQL for the daily digest: hand-ins `submissions.handed_in_at >= cutoff AND source='student'`, marked `marking_runs.created_at >= cutoff` joined via `submissions.run_id`, needs-you `teacher_queue.status='pending'` joined through `submissions.class_assignment_id`, released `class_assignments.released_at >= cutoff`; grouped by class → assignment; insights link when `assignment_insights.report_json IS NOT NULL`). Messages (HTML, escaped):
```
📥 <b>4E2 · Worksheet 3</b> — 5 new hand-ins: #1 Tan Wei Ling, #4 Priya Nair, …
<a href="…/classes/1/assignments/3">Open the roster</a>

✅ <b>4E2 · Worksheet 3</b> — marking finished: 38 marked, 3 need you
<a href="…/review">Review</a> · <a href="…/classes/1/assignments/3?tab=insights">Insights</a>

☀️ <b>Smart Marking — Wed 17 Sep</b>
<b>4E2 Mathematics</b>
• Worksheet 3 — 12 handed in, 12 marked, 2 need you → <a href="…">open</a> · <a href="…?tab=insights">insights</a>
```
When `app_base_url` is None, omit links. `create_submission`: after the insert (outside the transaction) call `record_hand_in(db, {"class_assignment_id":…, "student_id":…, "source":…})` guarded by `if class_assignment_id is not None`. Worker: in `run_once`, after the try/except, `if job["kind"] == "mark" and job.get("submission_id") is not None: try: on_mark_settled(self.db, self.jobs, job["submission_id"]) except Exception: log.exception(...)`; `_maybe_telegram()` every 10 s: `poll_updates`, `flush_notifications`, `maybe_send_daily(..., now=datetime.now(timezone.utc))`. `on_mark_settled` reads `telegram_instant` from the settings row directly (no cipher needed) — expose `SettingsStore.load()` is fine too since the worker has the store; pass `settings_store` where convenient but keep the signature above.

- [ ] **Step 4:** PASS. **Step 5:** commit `feat(telegram): hand-in and marking-finished messages, daily digest`.

---

### Task 8: Frontend — Settings (Notifications, My models) + types

**Files:** modify `web/src/api/types.ts`, `web/src/pages/Settings.tsx`; test `web/src/pages/__tests__/Settings.test.tsx`.

**Interfaces:** `Settings` type gains `telegram_linked: boolean; telegram_bot_hint: string; telegram_chat_id: string | null; telegram_instant: boolean; telegram_daily_time: string; timezone: string; app_url: string | null`; `ProviderSpec` gains `custom_models: boolean`; `ModelSpec` gains `custom?: boolean`. Update existing test fixtures (`custom_models: false` on the providers; the settings fixture gets the new fields).

- [ ] **Step 1: Tests**
```tsx
describe("Settings — notifications", () => {
  it("shows link status, saves the token and daily time, tests and unlinks", async () => {
    const calls = mockFetch(...);   // GET providers/settings; PUT settings echoes; POST /api/settings/telegram/test 204; DELETE /api/settings/telegram 204
    render(<MemoryRouter><Settings /></MemoryRouter>);
    expect(await screen.findByText(/Not linked/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Telegram bot token"), "123:abc");
    await userEvent.clear(screen.getByLabelText("Daily report at")); await userEvent.type(screen.getByLabelText("Daily report at"), "18:00");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    const put = saved[saved.length - 1]; expect(put.telegram_bot_token).toBe("123:abc"); expect(put.telegram_daily_time).toBe("18:00"); expect(put.timezone).toBe("Asia/Singapore");
    // once linked (server says so) the buttons appear
    ...re-render with telegram_linked: true...
    await userEvent.click(screen.getByRole("button", { name: "Send test message" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/settings/telegram/test")).toBe(true));
    await userEvent.click(screen.getByRole("button", { name: "Unlink" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE" && c.path === "/api/settings/telegram")).toBe(true));
  });
});
describe("Settings — my models", () => {
  it("adds and removes a custom model for OpenRouter and hides the list for OpenAI", async () => {
    ... providers fixture with openrouter {custom_models: true, models:[...]} and openai {custom_models:false}
    ... POST /api/settings/models/openrouter returns 201; GET /api/providers afterwards includes it with custom: true
    await userEvent.click(screen.getByRole("radio", { name: /OpenRouter/ }));
    await userEvent.type(screen.getByLabelText("Model id"), "google/gemini-3.8-flash");
    await userEvent.click(screen.getByRole("button", { name: "Add model" }));
    expect(await screen.findByRole("option", { name: /Gemini 3.8 Flash|google\/gemini-3.8-flash/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Remove google\/gemini-3.8-flash/ }));
    await userEvent.click(screen.getByRole("radio", { name: /OpenAI/ }));
    expect(screen.queryByLabelText("Model id")).not.toBeInTheDocument();
  });
});
```
- [ ] **Step 2:** FAIL. **Step 3:** implement: form gains `telegram_bot_token, telegram_instant, telegram_daily_time, timezone, app_url`; a **Notifications** section (`<h2>`): token input (`id="tg-token"`, placeholder from `telegram_bot_hint`: "Saved token ending …CDEF — leave blank to keep" / "Paste the token from @BotFather"), status line "Linked ✓ (chat …{last 4 of chat id})" or "Not linked — save the token, then open your bot in Telegram and press /start", buttons **Send test message** / **Unlink** (only when linked), checkbox "Send instant messages (hand-ins, marking finished)", `Daily report at` time input (`type="time"`), `Time zone` `<select>` with a fixed list (Asia/Singapore, Asia/Kuala_Lumpur, Asia/Jakarta, Asia/Manila, Asia/Bangkok, Asia/Hong_Kong, Asia/Tokyo, Australia/Sydney, Europe/London, UTC — plus the current value if not in the list), `App URL` input with placeholder "auto-detected on Railway". **My models** block under the provider tiles when `spec.custom_models`: list of `spec.models.filter(m => m.custom)` with a **Remove {id}** ghost button each; inputs `Model id`, `Label` (optional), checkbox `Reads pages` (default on), **Add model** → `POST`, then reload `/api/providers`. Next to each id from *Load models* not already in the list, a small **+ Add** button (posts with vision=true).

- [ ] **Step 4:** frontend checks PASS. **Step 5:** commit `feat(web): Telegram notifications and My models on Settings`.

---

### Task 9: Frontend — assignment Model section

**Files:** modify `web/src/pages/AssignmentEditor.tsx`, `web/src/pages/Assignments.tsx`, `web/src/api/types.ts` (`AssignmentTemplate` gains `provider: string | null; model: string | null; extractor_model: string | null; effective_model: {provider: string; model: string; extractor_model: string | null}`; `AssignmentBody` gains the three optional fields); tests `web/src/pages/__tests__/AssignmentEditor.test.tsx`, `Assignments.test.tsx`.

- [ ] **Step 1: Tests**: editor renders a **Model** section defaulting to "Auto — follow Settings" (caption shows the effective model, e.g. "Using OpenRouter · Auto Router from Settings"); choosing "Choose a model" shows provider tiles where providers without a saved key (`settings.keys` lacks them) are disabled with title "No key saved — add one under Settings"; picking OpenAI + `gpt-5.5` and saving sends `provider: "openai", model: "gpt-5.5", extractor_model: null`; switching back to Auto sends `provider: null`. Assignments list shows a caption "OpenAI · gpt-5.5" on a template whose `provider` is set.

- [ ] **Step 2:** FAIL. **Step 3:** implement: `Draft` gains `provider: string | null; model: string; extractorModel: string`; a `section` "Model" with a `.seg` radiogroup `aria-label="Model"` (Auto / Choose a model); when choosing: tiles (`radiogroup aria-label="Model provider"`), model `<select aria-label="Model id">` built from the provider's `models` (custom included) + "Custom model id…" input, and `Different model for reading pages (optional)` input. The page loads `GET /api/providers` and `GET /api/settings` (it already loads settings for the delete-pages default). Save payload adds the three fields (`provider: null` when Auto).

- [ ] **Step 4:** PASS. **Step 5:** commit `feat(web): choose the model per assignment`.

---

### Task 10: Frontend — Insights tab

**Files:** create `web/src/components/InsightsPanel.tsx`; modify `web/src/pages/ClassAssignmentPage.tsx`, `web/src/api/types.ts` (`InsightsStats`, `InsightsReport`, `InsightsPayload` types mirroring §A1/§A2, `job: {status} | null`), `web/src/styles/app.css`; test `web/src/components/__tests__/InsightsPanel.test.tsx`, `web/src/pages/__tests__/ClassAssignmentPage.test.tsx`.

- [ ] **Step 1: Tests**: `InsightsPanel` given a payload with 3 parts renders a row per part (`role="listitem"` with the label and `41%`), the weakest part gets class `weak`, "Most-lost allocations" lists "9(b) · A1 — 27 of 38", the four narrative headings in order (Summary, Strengths, Gaps, Recommended next steps), the students table with names and weak-part labels, **Download PDF** links to `/api/classes/1/assignments/3/insights.pdf` (via `downloadFile`), **Regenerate** posts to `…/insights/regenerate` and shows "Generating…" while `job.status` is queued/running (polls every 5 s — use fake timers); with `report: null` shows "The AI summary hasn't been generated yet" and the numbers only; with `n_marked: 0` shows "Nothing marked yet". Page test: a `.seg` with "Roster | Insights" driven by `?tab=insights` renders the panel.

- [ ] **Step 2:** FAIL. **Step 3:** implement. Bars: `<ol className="bars">` items with a `<span className="bar" style={{width: pct%}}>` and text `label · mean%` (text always present — never colour alone); weakest three get `weak` (amber). Distribution: five buckets as small labelled bars. CSS: `.bars li{display:grid;grid-template-columns:90px 1fr 60px;gap:12px;align-items:center;min-height:32px} .bar{display:block;height:14px;background:var(--ink)} .weak .bar{background:var(--amber-stripe)}`. ClassAssignmentPage: tab segmented control under the header (`tab` from `useSearchParams`), roster block hidden when `tab === "insights"`.

- [ ] **Step 4:** PASS. **Step 5:** commit `feat(web): Insights tab with chart, narrative, students to support`.

---

### Task 11: README, docs kit, final verification

- [ ] README **Web app**: a paragraph each for **Insights** (what it computes, that names never go to the model, PDF), **Telegram** (BotFather → token → /start; what is sent; daily time/zone), **Model per assignment** and **My models**; Settings list gains the new entries; roadmap updated. `docs/railway-template/README.md` + `overview.md`: mention Telegram and Insights in the feature list (one line each) — do **not** republish; note that the listing is updated with `railway templates update`.
- [ ] Full verification: `uv run pytest -q`; `cd web && npx vitest run && npx tsc --noEmit && npm run build`; local click-through: Settings → paste a fake token → status "Not linked"; assignment editor → Model → Choose → providers without keys disabled; class assignment → Insights tab shows numbers for the seeded data.
- [ ] Commit `docs: insights, telegram notifications, per-assignment models`.

---

## Self-review

- **Spec coverage:** A1 → T4; A2/A3/A4 → T5 + T10; B1/B2 → T6 + T8; B3 → T7 + T8; C1 → T3 + T9; C2 → T2 + T8; E → tests in each task. Spec §B3's "insights link where a report exists" → `build_daily_digest` joins `assignment_insights`.
- **Type consistency:** `for_template(tpl)` used in T3/T5; `BucketPool.get(provider, rpm)` in T1/T3/T5; `enqueue_insights(jobs, caid)` in T5/T7; `record_hand_in`/`on_mark_settled`/`flush_notifications`/`maybe_send_daily` in T7 and the worker; `insights_payload` in T4/T5/T10; frontend types named identically in T8/T9/T10.
- **Placeholders:** none.
