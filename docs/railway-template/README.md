# Railway marketplace listing — copy-paste kit

Everything the **Publish template** form asks for. Create the template with
*Project → Settings → Generate Template from Project* (see the steps at the bottom), then paste these in.

## Listing

**Name:** Smart Marking

**Tagline (≤ 80 chars):** AI marking for handwritten scripts — teachers check the doubtful parts, then release.

**Category:** Education (fallback: AI / Machine Learning)

**Icon:** `docs/railway-template/icon.png` (512 × 512)

**Demo project:** none (each deployment holds a school's own scripts)

## Overview (Markdown)

```markdown
**Smart Marking** marks handwritten scripts photographed or scanned by students, against *your* mark scheme or rubric — and puts every doubtful part in front of a teacher before anything reaches a student.

### What you get
- **Bring your own model.** TokenRouter, OpenRouter, OpenAI, Anthropic, Moonshot (Kimi), Qwen or Google Gemini — paste a key under Settings, keys are kept per provider. Free options: OpenRouter `:free` models and Gemini's free tier.
- **Typed assignments.** Upload the question paper and the mark scheme (maths/science) or rubric (essays); the app transcribes them into an editable table. Reuse them from a bank.
- **Per-part marking with a second opinion.** An extractor reads the pages, a marker awards each allocation (M1/A1/B1…) or band, an independent reviewer checks it. Illegible, out-of-scheme or disputed parts land in **Review** for you.
- **Classes and student hand-in.** Upload a classlist CSV, paste one link into Google Classroom; students type their register number, photograph their pages and hand in from their phone — no accounts, no passwords.
- **Release when you're ready.** Students see marks and feedback only after you release; download a marks CSV or a `.docx` marking record per student (with a blank "Teacher's mark" column for moderation).
- **Learns from your corrections.** A nightly reflection distils rubric notes and exemplar cases from what you changed — approved notes shape the next run.

### What's in the template
- `web` — the app (FastAPI + React), built from the Dockerfile, with the marking worker embedded
- `Postgres` — assignments, classes, marks, settings (API keys encrypted at rest)
- a 5 GB volume at `/data` for page images (deleted after marking by default)

### After deploying
1. Open the app and sign in with `TEACHER_PASSWORD`.
2. **Settings** → pick a provider, paste its key, **Load models from provider**, **Test connection**, **Save**.
3. **Assignments** → new assignment → upload the paper and mark scheme → **Read questions / Read mark scheme** → **Save**.
4. **Classes** → new class → classlist CSV (`name, reg_no`) → **Set assignment** → **Open** → **Copy link** for your students.

Source and docs: https://github.com/twahidin/smart-marking-system
```

## Services and variables (template composer)

### Service `web` — source `https://github.com/twahidin/smart-marking-system` (branch `main`)

| Variable | Value | Notes |
|---|---|---|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` | reference variable |
| `SECRET_KEY` | `${{secret(64)}}` | generated per deployment; signs sessions + encrypts API keys |
| `TEACHER_PASSWORD` | `${{secret(12, "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789")}}` | generated; the deployer reads it from Variables. Mark it *required / user-editable* so they can set their own. |
| `STORAGE_DIR` | `/data` | the volume mount |
| `LLM_PROVIDER` | `tokenrouter` | optional, user-editable |
| `LLM_MODEL` | *(empty)* | optional — provider default when blank |
| `LLM_API_KEY` | *(empty)* | optional — pre-seeds the key for `LLM_PROVIDER` |

Settings: builder **Dockerfile** (auto from `railway.json`), healthcheck `/api/health` (auto),
**Public networking → HTTP** (leave the port unset — the app listens on Railway's `$PORT`), volume
mounted at **`/data`** (5 GB is plenty; pages are deleted after marking).

Do **not** copy `PORT=8000` from the production project — it was only needed because that project's
domain was pinned to port 8000.

### Service `Postgres` — Railway's Postgres template (default settings)

## Steps in the dashboard

1. https://railway.com/project/2ca1604a-cc3c-4ca0-8a52-4b1f8a73369e/settings → **Generate Template from Project** → **Create Template**.
2. In the composer: remove the `PORT` variable on `web`; replace `SECRET_KEY` and `TEACHER_PASSWORD` values with the functions above; confirm `DATABASE_URL` is the `${{Postgres.DATABASE_URL}}` reference; confirm the `/data` volume and public HTTP networking; **Create Template**.
3. Deploy the template once yourself into a scratch project to make sure it comes up (health check green, sign-in works) — then delete the scratch project.
4. Workspace → **Templates** → **Publish** → paste the listing above, upload the icon, choose the category, publish.
5. Copy the template URL (`https://railway.com/new/template/<code>`) and paste it into the README's *Deploy on Railway* button.
