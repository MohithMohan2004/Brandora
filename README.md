# Brandora AI — RAG + Image Generation Prototype

A local proof of concept for prompt-based advertisement copy grounded in product and company CSVs, with optional cloud image generation through Cloudflare Workers AI.

## What it does

1. Loads `data/products.csv` and `data/company_guidelines.csv`.
2. Uses local Ollama embeddings to retrieve relevant product facts and guidelines.
3. Includes all mandatory guidelines in the generation context.
4. Uses a local Ollama language model to draft the headline, ad copy, CTA and visual direction.
5. Sends the visual direction plus retrieved product facts to Cloudflare Workers AI (FLUX.1 schnell) when you click **Generate image with Cloudflare**.
6. Shows the generated image in Streamlit and provides downloads for the copy and image.

The generated image is product/lifestyle visual artwork, not guaranteed to reproduce an exact product SKU or logo. The app asks the image model not to render text; use the approved copy separately for a more reliable final advertisement layout.

## Requirements

- Python 3.10+
- Ollama installed and running
- A Cloudflare account with Workers AI access for image generation
- Internet connection for the Cloudflare image request

## 1. Download the Ollama models

```bash
ollama pull llama3.2:3b
ollama pull embeddinggemma
```

## 2. Create a Python environment

From this project directory on Linux Mint:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If `venv` is missing:

```bash
sudo apt install python3-venv
```

## 3. Configure Cloudflare image generation

1. Sign in to the [Cloudflare dashboard](https://dash.cloudflare.com/).
2. Open **Workers AI** and choose **Use REST API**.
3. Create a Workers AI API token and copy your account ID. The token needs Workers AI permissions.
4. In this project folder, create your private environment file:

   ```bash
   cp .env.example .env
   xed .env
   ```

   If `xed` is unavailable, open `.env` in your preferred text editor.
5. Replace `your_cloudflare_account_id` and `your_cloudflare_api_token` with your actual values. Do not share or commit `.env`.

The default image model is `@cf/black-forest-labs/flux-1-schnell`. Cloudflare Workers AI has a free daily allowance, but limits and model availability can change; monitor usage in the Cloudflare dashboard. Requests may fail when the quota or permissions are insufficient.

Official guides:
- [Workers AI REST API setup](https://developers.cloudflare.com/workers-ai/get-started/rest-api/)
- [FLUX.1 schnell model](https://developers.cloudflare.com/workers-ai/models/flux-1-schnell/)
- [Workers AI pricing and daily allowance](https://developers.cloudflare.com/workers-ai/platform/pricing/)

## 4. Run Brandora

Make sure Ollama is running, then from the project folder:

```bash
streamlit run app.py
```

Open the local URL Streamlit prints, usually `http://localhost:8501`.

## 5. Use the app

1. Enter a campaign brief and click **Generate advertisement**.
2. Review the ad copy and visual direction.
3. Click **Generate image with Cloudflare**.
4. Review the image and click **Download generated image** if you want to save it.

## Important: catalogue data status

The expanded `data/products.csv` contains **100 synthetic demonstration records** across apparel, footwear, accessories, skincare, and electronics (20 per category). Product names, prices, materials, features, and specifications are illustrative, not verified claims about real products. Several entries deliberately include verification restrictions. Replace or verify every record against a real catalogue before using generated advertisements publicly. The `data_status` and `advertising_restrictions` columns are included in the RAG context so the model can see this warning.

## CSV knowledge base

- `data/products.csv`: product IDs, names, price, features, audience and variants.
- `data/company_guidelines.csv`: brand voice, prohibited claims and mandatory rules.

Keep facts explicit. Add one product or guideline per row and use stable IDs.

## Streamlit in one sentence

Streamlit is a Python framework that turns Python scripts into interactive browser-based apps. It handles the interface widgets (text areas, sliders, buttons, image previews and download buttons), so this prototype doesn't need a separate HTML/JavaScript frontend.

## Known limitations

- Retrieval embeddings are recomputed for each generation; this is suitable for a small prototype, not a large catalogue.
- This is not a multi-user production deployment; add authentication and secure secret management before deployment.
- The image model may alter product details and does not reliably render accurate text or logos. Treat the result as a visual concept unless it has been checked against the actual product.
- Prompt-based guardrails are not a guarantee; review generated copy before publishing.


## Voice prompt input

Brandora includes a microphone button above the campaign brief. Click the microphone, allow browser microphone access, speak your brief, and the recognized words will be inserted into the prompt field. Recognition support depends on your browser and may use the browser's speech service; if it is unavailable, type the prompt normally.

Install the new dependency after updating:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```
