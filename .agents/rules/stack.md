# Agrosphere Stack Rules & Context Mapping

This file defines project architecture rules and context mappings to help Antigravity index and reason about different components within Agrosphere.

## Workspace Context Mappings

Use these tags to refer to specific folders and scopes in discussions:

- `@backend` maps to: `c:/Users/Admin/Desktop/agrosphere/backend`
- `@frontend` maps to: `c:/Users/Admin/Desktop/agrosphere/frontend`
- `@env` maps to: `c:/Users/Admin/Desktop/agrosphere/.env` & `c:/Users/Admin/Desktop/agrosphere/.env.example`

## Backend Architecture Rules
- **Runtime**: Python 3.12
- **Framework**: FastAPI (built on Uvicorn web server)
- **Settings**: Loaded via Pydantic Settings or `python-dotenv` from the root or local `.env` file.
- **AI Integration**: Use the new `google-genai` SDK for Gemini API calls.

## Frontend Architecture Rules
- **Runtime**: Node.js v24 (or later)
- **Framework**: Next.js with React
- **Styling**: Tailwind CSS
- **TypeScript**: Strictly enforced across all code blocks and pages.
