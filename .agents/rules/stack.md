# Agrosphere Stack Rules & Context Mapping

This file defines project architecture rules and context mappings to help Antigravity index and reason about different components within Agrosphere.

## Workspace Context Mappings

Use these tags to refer to specific folders and scopes in discussions:

- `@backend` maps to: `c:/Users/Admin/Desktop/agrosphere/backend`
- `@frontend` maps to: `c:/Users/Admin/Desktop/agrosphere/frontend`
- `@env` maps to: `c:/Users/Admin/Desktop/agrosphere/.env` & `c:/Users/Admin/Desktop/agrosphere/.env.example`

## Core Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15, React, TypeScript, Tailwind CSS |
| Backend | FastAPI (Uvicorn), Python 3.12, SQLAlchemy |
| AI | Google GenAI SDK |

## Backend Architecture Rules

- **Runtime**: Python 3.12
- **Framework**: FastAPI (built on Uvicorn web server)
- **ORM**: SQLAlchemy for database access
- **AI Integration**: Use the `google-genai` SDK for Gemini API calls via the FastAPI RAG pipeline (see *Architectural Constraints*).
- **Settings**: Loaded via Pydantic Settings or `python-dotenv` from the root or local `.env` file.
- **API Handlers**: All async handlers use proper Pydantic schemas for request validation and response serialization.

## Frontend Architecture Rules

- **Runtime**: Node.js v24 (or later)
- **Framework**: Next.js 15 with React
- **Styling**: Tailwind CSS
- **TypeScript**: Strict mode enforced across all code blocks and pages.

## Architectural Constraints

### Offline-First PWA

The frontend must function in low-connectivity field conditions.

- **Service Worker**: Implement `next-pwa` with background sync to queue crop disease leaf scans when offline.
- **Caching**: Persist pending scans in IndexedDB; sync to the backend once connectivity is restored.

### Guardrailed AI

All AI treatment recommendations must pass through a controlled pipeline.

- **RAG Pipeline**: Route every recommendation through a FastAPI RAG service backed by verified agricultural extension databases.
- **Safety**: This prevents dosage hallucinations and ensures recommendations cite authoritative sources.

### Dual-Mode Profiles

User modes are isolated at the state/authentication layer to prevent feature creep across contexts.

- **Field Mode**: `FIELD_AG` — full agricultural toolkit (large-scale crop scanning, bulk recommendations, seasonal planning).
- **Garden Mode**: `URBAN_GARDEN` — simplified interface (small-plot disease detection, micro-garden treatment guidance, container planting advice).
- Mode is stored in auth state and used to gate feature visibility and API behavior.