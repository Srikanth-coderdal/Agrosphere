# Agrosphere

Agrosphere is a modular AI-powered agricultural application containing a Next.js/React frontend and a FastAPI backend powered by the Google GenAI SDK.

## Architecture

```
├── frontend/         # Next.js / React application
├── backend/          # Python / FastAPI application
├── .agents/          # Antigravity agent configuration folder
│   └── rules/        # Workspace rules for persistent context
│       └── stack.md  # Architecture map for @-mentions & stack guidelines
├── .env.example      # Template for environment variables
├── .gitignore        # Ignores sensitive keys, node_modules, and python cache
└── README.md         # Full project documentation & workflow guides
```

## Getting Started

### Prerequisites
- Node.js (v24 or later)
- Python (3.12 or later)

### Setup Backend
1. Navigate to the backend directory:
   ```bash
   cd backend
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   # Windows:
   .\venv\Scripts\activate
   # macOS/Linux:
   source venv/bin/activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy the environment variables template and add your Gemini API key:
   ```bash
   cp ../.env.example .env
   ```
5. Run the development server:
   ```bash
   uvicorn main:app --reload --port 8000
   ```

### Setup Frontend
1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Run the development server:
   ```bash
   npm run dev
   ```
