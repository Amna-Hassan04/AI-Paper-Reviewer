---
title: Arch Paper Reviewer
emoji: 🔬
colorFrom: indigo
colorTo: blue
sdk: gradio
app_file: app.py
pinned: false
---

# Computer Architecture Paper Reviewer

Gradio + OpenAI app that reviews research papers against strict computer-architecture
(ISCA/MICRO/HPCA/ASPLOS) standards, shows the review on screen, and saves it as a `.txt` file.

## Deploy on Hugging Face Spaces
1. Create a new Space → SDK: **Gradio** (blank; ZeroGPU hardware is fine). Upload `app.py`,
   `requirements.txt`, and this `README.md` (replace the auto-generated one).
2. Space → Settings → **Variables and secrets**:
   - `OPENAI_API_KEY` (secret, required)
   - `OPENAI_MODEL` (variable, optional; default `gpt-4o`)
   - `HF_TOKEN` (secret, optional; a **write** token) + `HF_REPO_ID` (e.g. `your-username/arch-reviews`)
     to save reviews permanently in the `reviews/` folder of that repo.
   - `HF_REPO_TYPE` (optional): `dataset` (default) or `space`.

## Where reviews are saved
- `reviews/` inside the running Space — erased when the Space restarts.
- `reviews/` in the Hub repo `HF_REPO_ID` — permanent (private dataset repo recommended).

## Run locally
```bash
pip install gradio -r requirements.txt
export OPENAI_API_KEY=sk-...
python app.py
```