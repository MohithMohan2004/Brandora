# Brandora AI — React + FastAPI

```
brandora/
├── backend/            # Python (replaces the Streamlit app)
│   ├── app.py          # FastAPI: RAG, Ollama, Cloudflare, API routes  (imports poster + tts_utils)
│   ├── poster.py       # poster rendering, fonts, config validation, review_log.jsonl
│   ├── tts_utils.py    # pyttsx3 voice-over (used by POST /api/generations/{id}/speech)
│   ├── data/           # put products.csv and company_guidelines.csv here (same as before)
│   ├── requirements.txt
│   └── .env.example    # copy to .env
└── frontend/           # React (Vite)
```

## Run (two terminals)

```bash
# 1. backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # add Cloudflare keys
uvicorn app:app --reload --port 8000

# 2. frontend
cd frontend
npm install
npm run dev                     # http://localhost:5173  (proxies /api to :8000)
```

Single-port option: `npm run build` in `frontend/`, then run only uvicorn and open http://localhost:8000.

Ollama must be running with your chat and embedding models, as before.
