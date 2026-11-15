<p align="center">
  <img src="frontend/public/icon-192.png" alt="Brandora" width="96" height="96">
</p>

<h1 align="center">Brandora</h1>

<p align="center">
  Turn a one-line product idea into a finished, ready-to-share advertisement:<br>
  copy, photography and a typeset poster in under a minute.
</p>

<p align="center">
  <a href="https://brandora-cs8i.onrender.com"><strong>Live demo</strong></a> ·
  <a href="https://github.com/MohithMohan2004/Brandora/releases/latest"><strong>Download the Android app</strong></a>
</p>

---

## Overview

Brandora is an AI advertising studio. You describe a product in plain words (or speak
it), and Brandora:

1. **Finds the right product** in your catalogue with retrieval-augmented generation (RAG)
   and applies your company's brand guidelines.
2. **Writes the ad**: headline, tagline, body copy, call to action and visual direction.
3. **Shoots the photo**: generates a clean, text-free product image and checks it with a
   vision model, retrying when lettering or clutter slips in.
4. **Designs the poster**: picks fonts that fit the mood, samples colours from the photo
   and places the copy around the product.
5. **Scores the result** against the brief so you can see how relevant the ad is before
   you publish it.

Every poster can be fine-tuned in the built-in editor and downloaded as a PNG.

## Features

| | |
|---|---|
| **Brief from text or voice** | Type a prompt or dictate it; speech is transcribed on the server. |
| **Catalogue-aware copy** | Semantic search over your product catalogue and brand guidelines grounds every ad in real data. |
| **Text-free image generation** | The image model never sees the ad copy, so no garbled lettering ends up in the photo. All words are typeset separately. |
| **Automatic layout** | Subject-aware placement, colours taken from the photo, and font pairings from seven typography moods that don't repeat between ads. |
| **Poster studio** | Edit text, fonts, colours and positions, or upload your own font. Changes are saved on the server. |
| **Relevance score** | Meaning similarity, LLM-judged coverage, catalogue match and photo fit, compared against a bar you set. |
| **History** | Every generation is kept and can be reopened, edited or deleted. |
| **Voice-over** | Generate a spoken version of the ad. |
| **Web, PWA and Android** | Use it in the browser, install it as a PWA, or use the native Android app. |

## Tech stack

- **Frontend:** React + Vite (installable PWA)
- **Backend:** Python, FastAPI, Pillow
- **AI models:** Cloudflare Workers AI (Llama 3.x for writing, FLUX.2 for images, a
  vision model for image checks, Whisper for speech), `embeddinggemma` embeddings via
  Ollama or Cloudflare
- **Typography:** Google Fonts
- **Android:** a native WebView wrapper (Java, min SDK 26) that ships the UI inside the APK
- **Hosting:** Docker on Render

## Getting started

### Requirements

- Python 3.10+ and Node.js 18+
- A [Cloudflare](https://dash.cloudflare.com/) account with Workers AI enabled (the free tier works)
- [Ollama](https://ollama.com/) with the `embeddinggemma` model, for local embeddings
  (optional if you set `EMBED_PROVIDER=cloudflare`)

### Setup

```bash
git clone https://github.com/MohithMohan2004/Brandora.git
cd Brandora
cp .env.example .env        # then fill in your Cloudflare account ID and API token
./start.sh
```

Open **http://localhost:8000**. On first run the script creates a virtual environment,
installs the Python and npm dependencies and builds the frontend. The UI and the API are
served from a single FastAPI process.

| Command | What it does |
|---|---|
| `./start.sh` | Run the app on http://localhost:8000 |
| `./start.sh --dev` | Backend with auto-reload plus the Vite dev server on http://localhost:5173 |
| `./start.sh --lan` | Make the server reachable from other devices on your Wi-Fi |

### Your own catalogue

Replace the CSV files in `backend/data/` with your own:

- `products.csv`: the products Brandora can advertise
- `company_guidelines.csv`: tone, voice and brand rules applied to every ad

## Android app

Download `Brandora.apk` from the [latest release](https://github.com/MohithMohan2004/Brandora/releases/latest)
and install it (you may need to allow installs from unknown sources).

The app connects to the hosted server out of the box. To use your own machine instead,
run `./start.sh --lan` and enter the address it prints on the app's connection screen.

To build it yourself:

```bash
cd frontend && npm run build && cd ..
cd android && ./gradlew assembleDebug
```

## Deployment

The repository includes a `Dockerfile` and a Render Blueprint (`render.yaml`). On
[Render](https://render.com), choose **New > Blueprint**, select this repository and
enter `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` when prompted. The hosted
version uses Cloudflare for embeddings, so it does not need Ollama.

> On Render's free plan the service sleeps when idle, so the first request after a
> quiet period can take up to a minute.

## Project structure

```
Brandora/
├── backend/
│   ├── app.py            # API routes, retrieval, AI model calls, generation storage
│   ├── poster.py         # Poster rendering and layout
│   ├── typography.py     # Font catalogue, typography moods and pairings
│   ├── relevance.py      # Brief-relevance scoring
│   ├── tts_utils.py      # Voice-over
│   ├── evaluate.py       # Evaluation metrics
│   └── data/             # Product catalogue and brand guidelines
├── frontend/             # React + Vite web app (PWA)
├── android/              # Android app
├── eval/                 # Evaluation scripts and datasets
├── Dockerfile
├── render.yaml
└── start.sh
```

## Evaluation

Brandora includes an evaluation suite covering retrieval quality, copy generation,
image checks and poster review:

```bash
venv/bin/python backend/evaluate.py [retrieval|generation|images|review]
```

Results are written to `eval_results/`. The `generation` and `images` modes call
Cloudflare Workers AI and use your daily quota.
