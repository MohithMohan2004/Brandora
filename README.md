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

## Run (one command)

```bash
./start.sh
```

Open http://localhost:8000. The script creates `venv/` and installs the Python and
npm packages when they are missing, rebuilds the React app when `frontend/src`
changed, and then serves the UI and the API from one FastAPI process.

While working on the code, `./start.sh --dev` runs the backend with auto-reload
and the Vite dev server at http://localhost:5173.

Keys live in `.env` at the repo root (copy `.env.example`). Ollama must be running
with the embedding model (`embeddinggemma`) for catalogue retrieval.

## How it works

- **Writer:** Cloudflare Workers AI (`llama-3.3-70b-instruct-fp8-fast`, then
  `llama-3.1-8b-instruct-fast`) writes the brief in ~5s. Local Ollama is only a fallback.
- **Image (text-free):** the image model never sees the ad copy. A fast model rewrites
  the visual direction as a plain photo description, with any mention of words, logos
  or layout removed, and asks for an uncluttered scene with empty space above and below
  the product. FLUX.2 klein draws it, and a vision model checks for stray lettering or
  clutter, retrying up to 3 times.
- **Poster design:** each image gets a font pairing that matches the brief's
  typography mood (minimal, elegant, bold, playful, organic, tech, retro). The fonts
  come from Google Fonts and are downloaded into `backend/fonts/google/`.
  `backend/fonts/pairing_history.json` keeps new ads from reusing a recent pairing.
  Text, band and button colours are sampled from the image. The layout finds where the
  product sits and keeps the headline above it and the copy below it.
- **Saving:** "Keep changes" in the poster studio stores your edits on the server
  (`backend/generations/<id>/`). They come back when you return to the step, reload
  the page, or restart the app.
