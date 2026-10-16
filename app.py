"""
Computer Architecture Paper Reviewer — Hugging Face Space (Gradio + OpenAI)

Upload a research paper (PDF/TXT), get a strict microarchitecture-expert review,
see it on screen, and save it as a .txt file:
  1) locally in ./reviews/ inside the Space, and
  2) (optional, persistent) in the reviews/ folder of a Hugging Face repo.

Secrets / variables (Space -> Settings -> Variables and secrets):
  OPENAI_API_KEY   (required, secret)
  OPENAI_MODEL     (optional, default "gpt-4o")
  HF_TOKEN         (optional, secret, write access) -> enables persistent saving
  HF_REPO_ID       (optional, e.g. "your-username/arch-reviews")
  HF_REPO_TYPE     (optional, "dataset" (default) or "space")
"""

import os
import re
from datetime import datetime, timezone
from pathlib import Path

import gradio as gr
import pymupdf
from huggingface_hub import HfApi
from openai import OpenAI

# ======================================================= ZeroGPU
# Free Spaces run on ZeroGPU hardware, which refuses to start unless at least one
# function is decorated with @spaces.GPU. This app does no GPU work (OpenAI runs the
# model), so we register a tiny placeholder that is never called and uses no GPU quota.
try:
    import spaces

    @spaces.GPU
    def _zerogpu_placeholder():
        return None
except ImportError:  # running locally without the 'spaces' package
    pass

# ======================================================= reviewer prompts
SYSTEM_PROMPT = """You are a senior reviewer on the program committee of top computer architecture
venues (ISCA, MICRO, HPCA, ASPLOS). You have deep expertise in microarchitecture:
out-of-order cores, branch prediction, cache hierarchies and replacement policies,
prefetching, memory controllers and DRAM, coherence and consistency, NoCs, accelerators,
and microarchitectural security (side channels, transient execution).

You review with strict, evidence-based standards. Rules you never break:
- Every criticism and every praise must cite specific evidence from the paper
  (section, figure, table, equation, or quoted claim). If the paper does not contain
  something, say explicitly "The paper does not report ...".
- State the evidence first, then your conclusion, and make the link explicit
  ("Figure 7 shows X; therefore ...").
- Keep observations, hypotheses, and conclusions clearly separated. Never invent
  results, numbers, or related work that are not in the paper. If you mention prior
  work from your own knowledge, label it as "Reviewer's note (prior work)".
- Be direct and constructive. Do not inflate scores.
"""

RUBRIC = """Evaluate the paper against these computer-architecture standards:

1. Problem & Motivation: Is the problem real and quantified (e.g., limit study, oracle
   study, characterization showing headroom)? Is the motivation data from the same
   methodology used in the evaluation?
2. Novelty & Prior Work: What is new versus the closest prior work? Are the
   state-of-the-art baselines included (e.g., for LLC replacement: SHiP, Hawkeye,
   Glider, Mockingjay; for prefetching: SPP, Bingo, IPCP, Berti; for branch prediction:
   TAGE-SC-L)? Missing or strawman baselines are a major weakness.
3. Mechanism Design: Is the design described precisely enough to implement? Are corner
   cases (coherence, context switches, multi-core interference, wrong-path effects)
   handled?
4. Methodology: Simulator and its fidelity (gem5 / ChampSim / Sniper / ZSim / RTL),
   core and memory configuration table, warm-up and simulation length, SimPoints or
   sampling, workload selection (SPEC CPU2017, GAP, CloudSuite, etc.) and whether
   workloads were cherry-picked (e.g., only memory-intensive). Are multi-core mixes
   and their selection described?
5. Results & Metrics: Correct metrics (IPC speedup, weighted/harmonic speedup for
   multi-core, MPKI, energy). Geometric mean for ratios. Per-workload results, not
   only averages. Are slowdowns reported and explained? Is variance/statistical
   significance addressed?
6. Hardware Cost & Feasibility: Storage budget (KB) compared fairly with baselines at
   iso-storage, area/power/energy (CACTI, McPAT, synthesis), latency and critical path
   impact, and whether the mechanism fits within cycle-time constraints.
7. Sensitivity & Robustness: Sensitivity to cache size, associativity, core count,
   memory bandwidth, prefetcher on/off, and key design parameters.
8. Security (if applicable): Threat model, attacker capabilities, leakage analysis,
   performance cost of the defense, and whether known attacks/variants are covered.
9. Reproducibility: Artifacts, configurations, and enough detail to reproduce.
10. Writing & Claims: Are claims supported by the evidence presented? Are conclusions
   distinguishable from speculation? Are figures readable and self-contained?
"""

OUTPUT_FORMAT = """Write the review in exactly this structure (plain text / Markdown):

## Paper Summary
(3-5 sentences: problem, key idea, main claimed results.)

## Key Contributions (as claimed vs. as supported)
(Bullet each claimed contribution and state whether the evidence supports it.)

## Strengths
(Numbered; each with cited evidence.)

## Weaknesses
(Numbered; label each [Major] or [Minor]; each with cited evidence and why it matters.)

## Detailed Evaluation
(One short subsection per rubric item 1-10. Write "N/A" where truly not applicable.)

## Questions for the Authors
(Numbered, specific, answerable in a rebuttal.)

## Suggestions for Improvement
(Concrete experiments, baselines, or analyses that would change your assessment.)

## Scores
- Novelty: x/5
- Technical Soundness: x/5
- Methodology & Evaluation Rigor: x/5
- Hardware Feasibility: x/5
- Clarity: x/5
- Overall Merit: one of [Strong Reject, Weak Reject, Weak Accept, Accept, Strong Accept]
- Reviewer Confidence: x/5

## Justification of Overall Merit
(Evidence first, then the conclusion, linked explicitly.)
"""

STRICTNESS = {
    "Standard": "Apply normal top-venue standards.",
    "Strict": "Apply strict top-venue standards (acceptance rate ~20%). "
              "Missing state-of-the-art baselines or iso-storage comparisons are Major weaknesses.",
    "Very strict": "Act as the most critical reviewer on the PC. Assume the paper must "
                   "clearly beat the best published work under fair, iso-cost comparison "
                   "with rigorous methodology; otherwise recommend rejection.",
}


def build_user_prompt(paper_text: str, venue: str, strictness: str, extra: str) -> str:
    parts = [
        f"Target venue: {venue}",
        f"Strictness: {STRICTNESS[strictness]}",
        RUBRIC,
        OUTPUT_FORMAT,
    ]
    if extra.strip():
        parts.append(f"Additional reviewer instructions:\n{extra.strip()}")
    parts.append("=== PAPER TEXT START ===\n" + paper_text + "\n=== PAPER TEXT END ===")
    return "\n\n".join(parts)

# =======================================================

REVIEWS_DIR = Path("reviews")
REVIEWS_DIR.mkdir(exist_ok=True)
MAX_CHARS = 300_000  # ~75k tokens; longer papers are truncated
VENUES = ["ISCA", "MICRO", "HPCA", "ASPLOS", "IEEE CAL", "DAC", "Workshop"]


# ---------------------------------------------------------------- helpers
def extract_text(path: str) -> str:
    if path.lower().endswith(".pdf"):
        with pymupdf.open(path) as doc:
            return "\n".join(page.get_text() for page in doc)
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).stem)[:80] or "paper"


def save_local(text: str, paper_name: str) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = REVIEWS_DIR / f"{ts}_{safe_name(paper_name)}_review.txt"
    path.write_text(text, encoding="utf-8")
    return path


def save_to_hub(local_path: Path) -> str | None:
    """Upload the review into 'reviews/' of a HF repo. Returns URL, or None if not configured."""
    token, repo_id = os.getenv("HF_TOKEN"), os.getenv("HF_REPO_ID")
    if not (token and repo_id):
        return None
    repo_type = os.getenv("HF_REPO_TYPE", "dataset")
    api = HfApi(token=token)
    api.create_repo(repo_id, repo_type=repo_type, private=True, exist_ok=True)
    api.upload_file(
        path_or_fileobj=str(local_path),
        path_in_repo=f"reviews/{local_path.name}",
        repo_id=repo_id,
        repo_type=repo_type,
        commit_message=f"Add review {local_path.name}",
    )
    prefix = {"dataset": "datasets/", "space": "spaces/"}.get(repo_type, "")
    return f"https://huggingface.co/{prefix}{repo_id}/blob/main/reviews/{local_path.name}"


def list_saved():
    return [str(p) for p in sorted(REVIEWS_DIR.glob("*.txt"), reverse=True)]


# ---------------------------------------------------------------- main action
def review_paper(file, api_key, model, venue, strictness, temperature, extra):
    """Generator: streams (review_markdown, status, download_file, saved_files)."""
    api_key = os.getenv("OPENAI_API_KEY") or (api_key or "").strip()
    if file is None:
        yield "", "⚠️ Please upload a paper.", None, list_saved()
        return
    if not api_key:
        yield "", "⚠️ Set OPENAI_API_KEY as a Space secret or enter it above.", None, list_saved()
        return

    paper_name = Path(file).name
    paper_text = extract_text(file)
    if len(paper_text.strip()) < 500:
        yield "", "⚠️ Could not extract enough text (is the PDF scanned images?).", None, list_saved()
        return
    status = ""
    if len(paper_text) > MAX_CHARS:
        paper_text = paper_text[:MAX_CHARS]
        status = f"Paper truncated to first {MAX_CHARS:,} characters. "

    prompt = build_user_prompt(paper_text, venue, strictness, extra or "")
    client = OpenAI(api_key=api_key)
    review = ""
    try:
        stream = client.chat.completions.create(
            model=model.strip() or "gpt-4o",
            temperature=temperature,
            stream=True,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                review += chunk.choices[0].delta.content
                yield review, status + "✍️ Writing review...", None, list_saved()
    except Exception as e:  # bad key, wrong model name, quota, etc.
        yield review, f"❌ OpenAI API error: {e}", None, list_saved()
        return

    header = (
        f"Paper: {paper_name}\nVenue: {venue}\nStrictness: {strictness}\nModel: {model}\n"
        f"Generated (UTC): {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}\n" + "=" * 70 + "\n\n"
    )
    local_path = save_local(header + review, paper_name)
    status += f"✅ Saved to Space folder: {local_path}"
    try:
        url = save_to_hub(local_path)
        if url:
            status += f"\n✅ Saved to Hugging Face repo: {url}"
    except Exception as e:
        status += f"\n⚠️ Hub upload failed (saved locally only): {e}"

    yield review, status, str(local_path), list_saved()


# ---------------------------------------------------------------- UI
hub_on = bool(os.getenv("HF_TOKEN") and os.getenv("HF_REPO_ID"))

with gr.Blocks(title="Arch Paper Reviewer") as demo:
    gr.Markdown(
        "# 🔬 Computer Architecture Paper Reviewer\n"
        "Upload a paper and get a strict, evidence-based review from a microarchitecture expert reviewer.  \n"
        f"Persistent Hub saving: **{'ON → ' + os.getenv('HF_REPO_ID') if hub_on else 'OFF (set HF_TOKEN and HF_REPO_ID)'}**"
    )
    with gr.Row():
        with gr.Column(scale=1):
            paper = gr.File(label="Research paper (PDF or TXT)",
                            file_types=[".pdf", ".txt", ".md", ".tex"], type="filepath")
            api_key = gr.Textbox(label="OpenAI API key (leave blank if set as Space secret)",
                                 type="password", visible=not os.getenv("OPENAI_API_KEY"))
            model = gr.Textbox(label="Model", value=os.getenv("OPENAI_MODEL", "gpt-4o"))
            venue = gr.Dropdown(VENUES, value="MICRO", label="Target venue")
            strictness = gr.Radio(list(STRICTNESS), value="Strict", label="Strictness")
            temperature = gr.Slider(0.0, 1.0, value=0.2, step=0.05, label="Temperature")
            extra = gr.Textbox(label="Extra instructions (optional)", lines=3,
                               placeholder="e.g. Focus on the comparison against Mockingjay.")
            btn = gr.Button("Generate review", variant="primary")
        with gr.Column(scale=2):
            status = gr.Textbox(label="Status", interactive=False)
            review_md = gr.Markdown(label="Review")
            download = gr.File(label="Download review (.txt)")
            saved = gr.Files(label="All saved reviews in this Space", value=list_saved)

    btn.click(
        review_paper,
        inputs=[paper, api_key, model, venue, strictness, temperature, extra],
        outputs=[review_md, status, download, saved],
    )

if __name__ == "__main__":
    demo.launch()