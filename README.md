<div align="center">
  <img
    src="https://capsule-render.vercel.app/api?type=waving&color=0:1B4332,50:2D6A4F,100:52B788&height=220&section=header&text=Agrosphere&fontSize=64&fontColor=ffffff&fontAlignY=35&desc=AI%20%C3%97%20Agriculture%20%C3%97%20Telemetry&descAlignY=55&descSize=18&animation=fadeIn"
    alt="Agrosphere — AI-powered agricultural intelligence"
    width="100%"
  />

  <br />

  <!-- Tech Stack Badges — official brand colors -->
  <a href="https://nextjs.org/"><img src="https://img.shields.io/badge/Next.js-15-000000?style=for-the-badge&logo=nextdotjs&logoColor=white" alt="Next.js 15" /></a>
  <a href="https://fastapi.tiangolo.com/"><img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" /></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=FFD43B" alt="Python 3.12" /></a>
  <a href="https://nodejs.org/"><img src="https://img.shields.io/badge/Node.js-v24-339933?style=for-the-badge&logo=nodedotjs&logoColor=white" alt="Node.js v24" /></a>
  <a href="https://ai.google.dev/"><img src="https://img.shields.io/badge/Google%20GenAI-SDK-4285F4?style=for-the-badge&logo=google&logoColor=white" alt="Google GenAI SDK" /></a>
  <a href="./.agents/rules/"><img src="https://img.shields.io/badge/Antigravity-Rules-7C3AED?style=for-the-badge&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0id2hpdGUiPjxwYXRoIGQ9Ik0xMiAyTDIgN2wxMCA1IDEwLTV6Ii8+PHBhdGggZD0iTTIgMTd2MmwxMCA1IDEwLTV2LTJsLTEwIDV6Ii8+PHBhdGggZD0iTTIgMTJ2MmwxMCA1IDEwLTV2LTJsLTEwIDV6Ii8+PC9zdmc+" alt="Antigravity Rules" /></a>

  <br /><br />

  <h3>
    <em>Crop intelligence that scans, predicts, irrigates — and never sleeps.</em>
  </h3>

  <p>
    Modular AI agriculture stack: Next.js frontend · FastAPI brain · Gemini vision · agent-ready workspace rules.
  </p>

  <p>
    <a href="#-quick-start"><strong>Get Started →</strong></a>
    &nbsp;·&nbsp;
    <a href="#-architecture"><strong>Architecture</strong></a>
    &nbsp;·&nbsp;
    <a href="#-agentic-context"><strong>Agentic Context</strong></a>
  </p>
</div>

---

## ⚡ Core Intelligence Stack

<p align="left">
  <em>Agrosphere isn't your average tech stack—it's a full-on AI copilot for the soil. Expand any module below to peek under the hood.</em>
</p>

<details open>
<summary><strong>🔬 01. Crop Disease Scanner</strong> &nbsp;<code>[Gemini Vision]</code> <code>[Multimodal]</code></summary>
<br />

> **The Vibe:** Snap a pic of a sick leaf, get an instant diagnosis before the blight takes over.

- 👁️ **Visual Pathogen Engine:** Feeds leaf micro-imagery straight to `Gemini Vision` to catch blights, rusts, and nutrient bugs in milliseconds.
- ✍️ **Farmer Context Overlay:** Drop in quick text notes (watering history, weird symptoms) so the model fine-tunes its diagnostic confidence.
- 🌐 **Bilingual Output Engine:** Delivers immediate, crystal-clear remediation steps in both English and Tamil.

</details>

<br />

<details open>
<summary><strong>💧 02. Smart Irrigation Engine</strong> &nbsp;<code>[Telemetry Engine]</code> <code>[Hydration Logic]</code></summary>
<br />

> **The Vibe:** Stop drowning your crops. Precision watering backed by real field telemetry.

- 📡 **Field Telemetry Matrix:** Ingests soil composition, growth stages, and real-time climate vectors instead of using lazy static guesses.
- ⏱️ **AI Hydro-Scheduling:** Calculates high-efficiency watering windows designed to completely kill off surface runoff and evaporation.
- 🌿 **Water-Thrift Protocol:** Maximizes your Water-Use Efficiency (WUE) so you save resources without frying crop yield.

</details>

<br />

<details open>
<summary><strong>📊 03. Yield Prediction Matrix</strong> &nbsp;<code>[Agro-Analytics]</code> <code>[Predictive ML]</code></summary>
<br />

> **The Vibe:** Simulated harvest forecasts so you know your numbers before the seed even hits the dirt.

- 🧮 **Harvest Simulator:** Crunches acreage, seed variants, and input schedules to throw out accurate tonnage estimates.
- 📈 **Growth Driver Engine:** Pinpoints exact yield bottlenecks and outputs custom stage-by-stage fertigation directives.
- 🎯 **Pre-Season Simulation:** Test-drive different resource allocation models to maximize ROI way before planting day.

</details>

<br />

<details open>
<summary><strong>🏙️ 04. Urban Gardening Hub</strong> &nbsp;<code>[Micro-Farming]</code> <code>[Space-Aware]</code></summary>
<br />

> **The Vibe:** Balcony-to-rooftop playbooks for city growers who mean business.

- 🪴 **Micro-Footprint Tactics:** Customized agricultural playbooks built explicitly for small plots, balconies, and vertical setups.
- 🧠 **AI Plant Copilot:** Tailor-fit care strategies optimized for exact pot volumes, sunlight hours, and container flora.
- 🔐 **Zero-Trust Access:** Clean session management and state persistence for city growers and community garden admins.

</details>

---

## 🏗 Architecture

Live system map — frontend, backend APIs, Gemini, and agent rules:

```mermaid
flowchart TB
  subgraph CLIENT["🖥️ Client"]
    FE["Next.js 15 / React<br/>TypeScript · Tailwind"]
  end

  subgraph API["⚙️ FastAPI Backend"]
    MAIN["main.py · Uvicorn"]
    AUTH["/api/v1/auth"]
    SCAN["/api/scan"]
    IRR["/api/irrigation"]
    YIELD["/api/v1/yield-estimator"]
    URBAN["/api/v1/urban-gardening"]
  end

  subgraph AI["🔮 Intelligence"]
    GEM["Google GenAI SDK<br/>Gemini Vision"]
  end

  subgraph AGENTS["🤖 Agentic Layer"]
    RULES[".agents/rules/<br/>stack.md"]
  end

  FE -->|"REST / CORS"| MAIN
  MAIN --> AUTH
  MAIN --> SCAN
  MAIN --> IRR
  MAIN --> YIELD
  MAIN --> URBAN
  SCAN --> GEM
  IRR --> GEM
  YIELD --> GEM
  URBAN --> GEM
  RULES -.->|"persistent context"| FE
  RULES -.->|"persistent context"| MAIN

  classDef frontend fill:#1E40AF,stroke:#93C5FD,color:#FFFFFF,stroke-width:2px
  classDef backend fill:#166534,stroke:#86EFAC,color:#FFFFFF,stroke-width:2px
  classDef agents fill:#6B21A8,stroke:#D8B4FE,color:#FFFFFF,stroke-width:2px
  classDef intel fill:#0F766E,stroke:#5EEAD4,color:#FFFFFF,stroke-width:2px

  class FE frontend
  class MAIN,AUTH,SCAN,IRR,YIELD,URBAN backend
  class RULES agents
  class GEM intel
```

### 📂 Workspace Tree

```text
agrosphere/
├── 🎨 frontend/              # Next.js · React · Tailwind · TypeScript
│   └── app/                  # App Router pages & lib (scan, irrigation, yield, urban)
├── 🐍 backend/               # FastAPI · Uvicorn · Pydantic · SQLAlchemy
│   ├── routers/              # Auth · Irrigation · Yield · Urban Gardening
│   ├── services/             # Gemini + domain business logic
│   ├── schemas/              # Request / response contracts
│   └── models/               # ORM models
├── 🤖 .agents/               # Antigravity agent configuration
│   └── rules/
│       └── stack.md          # Architecture map & @-mention guidelines
├── 🔐 .env.example           # Gemini API key template
└── 📖 README.md              # You are here
```

---

## 🚀 Quick Start

<details>
<summary><strong>✅ Prerequisites</strong> — click to expand</summary>

<br />

| Tool | Version | Why |
|------|---------|-----|
| **Node.js** | v24+ | Next.js frontend runtime |
| **Python** | 3.12+ | FastAPI + GenAI SDK |
| **Gemini API Key** | — | Vision & telemetry intelligence |

</details>

<details>
<summary><strong>🐍 Backend</strong> — FastAPI on port <code>8000</code></summary>

<br />

```bash
# Jump into the API workspace
cd backend

# Spin up an isolated Python environment
python -m venv venv

# Activate it (pick your OS)
# Windows:
.\venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate

# Install the FastAPI + GenAI stack
pip install -r requirements.txt

# Drop in your secrets (edit GEMINI_API_KEY after copy)
cp ../.env.example .env

# Launch hot-reload API — http://localhost:8000
uvicorn main:app --reload --port 8000
```

> Health check: `GET http://localhost:8000/api/health`

</details>

<details>
<summary><strong>🎨 Frontend</strong> — Next.js on port <code>3000</code></summary>

<br />

```bash
# Enter the UI workspace
cd frontend

# Install dependencies (Node v24+)
npm install

# Fire up the App Router — http://localhost:3000
npm run dev
```

> CORS is pre-wired for `http://localhost:3000` → FastAPI.

</details>

<details>
<summary><strong>🔑 Environment</strong> — Gemini key</summary>

<br />

```bash
# Root template (.env.example)
GEMINI_API_KEY="YOUR_GEMINI_API_KEY_HERE"

# Copy into backend before first run
cp .env.example backend/.env
# Then replace the placeholder with your real key from Google AI Studio
```

</details>

---

## 🤖 Agentic Context

Autonomous coding tools (**Cursor**, **Copilot**, **Antigravity**, and friends) should treat this repo as agent-first:

1. **Read** [`.agents/rules/stack.md`](./.agents/rules/stack.md) before touching architecture — it is the persistent source of truth for runtimes, frameworks, and `@backend` / `@frontend` / `@env` mappings.
2. **Respect** the stack contract: Python 3.12 + FastAPI + `google-genai` on the server; Node.js v24 + Next.js + TypeScript + Tailwind on the client.
3. **Prefer** existing routers/services/schemas over inventing parallel layers — the folder map above is the law.

Ship faster. Hallucinate less. Keep the harvest green. 🌾

---

<div align="center">
  <img
    src="https://capsule-render.vercel.app/api?type=waving&color=0:52B788,50:2D6A4F,100:1B4332&height=120&section=footer&animation=fadeIn"
    alt=""
    width="100%"
  />
  <p><strong>Agrosphere</strong> — open source · AI-native · built for the field</p>
  <p><sub>Contributions welcome. Star the repo if this helps your next season.</sub></p>
</div>
