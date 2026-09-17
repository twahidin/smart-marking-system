# Deploy and Host Smart Marking on Railway

**📘 Smart Marking Setup Guide** — step by step with screenshots of the real app: [read online](https://claude.ai/artifact/Fu6LVAMCYYxg2fPb3oFsFw) · [download the PDF](https://github.com/twahidin/smart-marking-system/raw/main/docs/setup-guide/Smart-Marking-Setup-Guide.pdf) · [on GitHub](https://github.com/twahidin/smart-marking-system/blob/main/docs/setup-guide/README.md)

Smart Marking marks handwritten scripts that students photograph or scan, against **your** mark scheme (maths/science) or rubric (essays). An extractor reads the pages, a marker awards each allocation or band, and an independent reviewer checks it; anything illegible, out of scheme or disputed lands in a **Review** queue for the teacher. Students hand in from their phone with a class code and register number; feedback is shown only after the teacher releases it. Bring your own LLM key (TokenRouter, OpenRouter, OpenAI, Anthropic, Moonshot, Qwen or Google Gemini).

## About Hosting Smart Marking

The template deploys two services: `web` (FastAPI + React, built from the Dockerfile, with the marking worker embedded) and `Postgres` (assignments, classes, marks and settings; API keys are encrypted at rest with the generated `SECRET_KEY`). Page images live on a volume mounted at `/data` and are deleted after marking by default, so storage stays small. After the deploy finishes, open the `web` domain, sign in with `TEACHER_PASSWORD` (generated — read it from the service's Variables, or set your own before deploying), go to **Settings** to paste a provider key and pick a model, then create an assignment and a class. No student accounts or passwords are needed: students use the class link and their register number. Everything runs inside your Railway project; scripts never leave it except for the model calls you configure.

## Common Use Cases

- Marking a class set of maths or science worksheets against a mark scheme, with M1/A1/B1-style allocations and a teacher check on the doubtful parts
- Grading essays against a band rubric and giving students structured feedback (strengths, question by question, what to work on next)
- Letting students hand in photographed work from their phones and receiving marks and feedback once the teacher releases them
- Producing per-student `.docx` marking records and a marks CSV for moderation and departmental records

## Dependencies for Smart Marking Hosting

- An API key for one supported LLM provider with a vision-capable model (free options: OpenRouter `:free` models, Google Gemini's free tier)
- The bundled Postgres service and the `/data` volume (both created by this template)

### Deployment Dependencies

- Railway's Postgres template (`ghcr.io/railwayapp-templates/postgres-ssl`) — created for you
- A vision-capable model from any supported provider: https://github.com/twahidin/smart-marking-system#web-app

### Implementation Details

Variables you may want to change before deploying: `TEACHER_PASSWORD` (generated), `LLM_PROVIDER` (default `tokenrouter`), and optionally `LLM_MODEL` / `LLM_API_KEY` to pre-seed the model and key. Source and documentation: https://github.com/twahidin/smart-marking-system — setup guide (PDF): https://github.com/twahidin/smart-marking-system/raw/main/docs/setup-guide/Smart-Marking-Setup-Guide.pdf

## Why Deploy Smart Marking on Railway?

Railway is a singular platform to deploy your infrastructure stack. Railway will host your infrastructure so you don't have to deal with configuration, while allowing you to vertically and horizontally scale it.

By deploying Smart Marking on Railway, you are one step closer to supporting a complete full-stack application with minimal burden. Host your servers, databases, AI agents, and more on Railway.
