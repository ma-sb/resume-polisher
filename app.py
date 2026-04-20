"""Resume Polisher – Streamlit application."""

import base64
import streamlit as st
from pathlib import Path

from core.reader import load_resumes, read_resume_from_bytes, Resume
from core.matcher import PROVIDERS, match_resumes, get_improvements, optimize_resume
from core.exporter import export_docx, _convert_to_pdf
from core.cover_letter import (
    resume_payload_from_source,
    generate_cover_letter,
    revise_cover_letter_with_feedback,
    build_export_letter,
    export_cover_letter_docx,
)

RESUMES_DIR = Path(__file__).parent / "resumes"
OUTPUT_DIR = Path(__file__).parent / "output"

STEP_LABELS = [
    "Job Description",
    "Your Resumes",
    "Match & Score",
    "Improvements",
    "Optimize & Review",
    "Export",
    "Cover Letter",
]

STEP_TOOLTIPS = {
    1: "Paste the full job posting so the AI knows what to optimize for.",
    2: "Upload one or more resume versions (.docx, .pdf, .doc) — the AI will compare them.",
    3: "The AI scores each resume against the job and picks the best match.",
    4: "Get bullet-by-bullet rewrite suggestions with keywords from the job.",
    5: "Generate a fully optimized resume and preview it before exporting.",
    6: "Enter the company name and download the final .docx / .pdf files.",
    7: "Optionally generate, edit, improve, and export a tailored cover letter.",
}

SAMPLE_JD = """Data Scientist, New York, NY - BCG X

What You'll Do

Our BCG X teams own the full analytics value-chain end to end: framing new business challenges, designing innovative algorithms, implementing, and deploying scalable solutions, and enabling colleagues and clients to fully embrace AI. Our product offerings span from fully custom-builds to industry specific leading edge AI software solutions. 

As a Data Scientist and Senior Data Scientist, you'll be part of our rapidly growing team. You'll have the chance to apply data science methods and analytics to real-world business situations across a variety of industries to drive significant business impact. You'll have the chance to partner with clients in a variety of BCG regions and industries, and on key topics like climate change, enabling them to design, build, and deploy new and innovative solutions. 

Additional responsibilities will include developing and delivering thought leadership in scientific communities and papers as well as leading conferences on behalf of BCG X. Successful candidates are intellectually curious builders who are biased toward action, scrappy, and communicative. 


We are looking for talented individuals with a passion for data science, statistics, operations research and transforming organizations into AI led innovative companies. Successful candidates possess the following: 

    Comfortable in a client-facing role with the ambition to lead teams 

    Likes to distill complex results or processes into simple, clear visualizations 

    Explain sophisticated data science concepts in an understandable manner 

    Love building things and are comfortable working with modern development tools and writing code collaboratively (bonus points if you have a software development or DevOps experience) 

    Significant experience applying advanced analytics to a variety of business situations and a proven ability to synthesize complex data 

    Deep understanding of modern machine learning techniques and their mathematical underpinnings, and can translate this into business implications for our clients 

    Have strong project management skills 
    Master's degree or PhD in relevant field of study - please provide all academic certificates showing the final grades (A-level, Bachelor, Master) """


def _get_saved_key() -> str:
    try:
        return st.secrets.get("api_key", "")
    except Exception:
        return ""


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _estimate_cost(n_resumes: int, job_tokens: int, resume_tokens: int, model: str) -> str:
    total_input = job_tokens + resume_tokens * n_resumes + 500
    total_output = 800 * n_resumes
    if "gpt-4o-mini" in model or "flash" in model or "haiku" in model:
        cost = total_input * 0.15 / 1_000_000 + total_output * 0.6 / 1_000_000
    elif "gpt-4o" in model or "pro" in model or "sonnet" in model:
        cost = total_input * 2.5 / 1_000_000 + total_output * 10.0 / 1_000_000
    else:
        cost = total_input * 5.0 / 1_000_000 + total_output * 15.0 / 1_000_000
    if cost < 0.01:
        return f"~{total_input + total_output:,} tokens · < $0.01"
    return f"~{total_input + total_output:,} tokens · ~${cost:.2f}"


def _current_step() -> int:
    """Determine the furthest completed step."""
    if st.session_state.get("cover_letter_generated"):
        return 7
    if st.session_state.get("export_approved"):
        return 6
    if "optimized" in st.session_state:
        return 5
    if "improvements" in st.session_state:
        return 4
    if "match_results" in st.session_state:
        return 3
    return 1


# ── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(page_title="Resume Polisher", page_icon="📄", layout="wide")

st.markdown(
    """
    <style>
    /* ── Global ──────────────────────────────────────────── */
    .block-container {padding-top: 1.5rem; max-width: 960px;}

    /* ── Header banner ───────────────────────────────────── */
    .app-header {
        background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
        color: white;
        padding: 2rem 2.5rem;
        border-radius: 12px;
        margin-bottom: 0.5rem;
    }
    .app-header h1 {
        margin: 0; font-size: 2rem; font-weight: 700; letter-spacing: -0.5px;
    }
    .app-header p {
        margin: 0.4rem 0 0 0; opacity: 0.8; font-size: 0.95rem;
    }

    /* ── Progress stepper ────────────────────────────────── */
    .stepper {
        display: flex; justify-content: space-between; align-items: center;
        padding: 1rem 0.5rem; margin-bottom: 1rem;
    }
    .step {
        display: flex; flex-direction: column; align-items: center;
        flex: 1; position: relative;
    }
    .step-circle {
        width: 32px; height: 32px; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        font-size: 0.8rem; font-weight: 700;
        border: 2px solid #cbd5e1; color: #94a3b8; background: white;
        transition: all 0.3s ease; z-index: 1;
    }
    .step-circle.active {
        border-color: #0f3460; color: white; background: #0f3460;
    }
    .step-circle.done {
        border-color: #059669; color: white; background: #059669;
    }
    .step-label {
        font-size: 0.7rem; margin-top: 4px; color: #94a3b8;
        text-align: center; white-space: nowrap;
    }
    .step-label.active, .step-label.done { color: #1a1a2e; font-weight: 600; }

    /* connector lines */
    .step:not(:last-child)::after {
        content: ''; position: absolute;
        top: 16px; left: calc(50% + 20px); right: calc(-50% + 20px);
        height: 2px; background: #e2e8f0; z-index: 0;
    }
    .step.done:not(:last-child)::after { background: #059669; }

    /* ── Section step labels ─────────────────────────────── */
    div[data-testid="stSubheader"] > div > p,
    .stSubheader {
        border-left: 4px solid #0f3460;
        padding-left: 0.75rem;
    }

    /* ── Metrics / score cards ───────────────────────────── */
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #f0f4ff 0%, #f8f9fb 100%);
        border-radius: 10px; padding: 14px 18px; border: 1px solid #e2e8f0;
    }
    div[data-testid="stMetricValue"] > div { font-weight: 700; color: #1a1a2e; }

    /* ── Expanders ───────────────────────────────────────── */
    details[data-testid="stExpander"] {
        border: 1px solid #e2e8f0 !important;
        border-radius: 8px !important; margin-bottom: 0.5rem;
        transition: box-shadow 0.2s ease;
    }
    details[data-testid="stExpander"]:hover {
        box-shadow: 0 2px 8px rgba(15, 52, 96, 0.08);
    }
    details[data-testid="stExpander"] summary { font-weight: 500; }

    /* ── Buttons ─────────────────────────────────────────── */
    .stButton > button[kind="primary"] {
        border-radius: 8px; font-weight: 600; letter-spacing: 0.3px;
    }

    /* ── Sidebar ─────────────────────────────────────────── */
    section[data-testid="stSidebar"] { background: #fafbfc; }
    section[data-testid="stSidebar"] .stSelectbox label,
    section[data-testid="stSidebar"] .stTextInput label {
        font-size: 0.85rem; font-weight: 600; color: #374151;
    }

    /* ── File uploader ───────────────────────────────────── */
    div[data-testid="stFileUploader"] section {
        border: 2px dashed #cbd5e1 !important; border-radius: 10px !important;
        transition: border-color 0.2s ease;
    }
    div[data-testid="stFileUploader"] section:hover { border-color: #0f3460 !important; }

    /* ── Alerts ──────────────────────────────────────────── */
    div[data-testid="stAlert"] { border-radius: 8px; }

    /* ── Score badge ─────────────────────────────────────── */
    .score-badge {
        display: inline-block; padding: 4px 14px; border-radius: 20px;
        font-weight: 700; font-size: 1.1rem; color: white;
        min-width: 60px; text-align: center;
    }
    .score-high   { background: linear-gradient(135deg, #059669, #10b981); }
    .score-medium { background: linear-gradient(135deg, #d97706, #f59e0b); }
    .score-low    { background: linear-gradient(135deg, #dc2626, #ef4444); }

    /* ── Token estimate badge ────────────────────────────── */
    .token-est {
        display: inline-block; font-size: 0.78rem; color: #64748b;
        background: #f1f5f9; padding: 3px 10px; border-radius: 6px;
        margin-bottom: 0.5rem;
    }

    /* ── Filename preview ────────────────────────────────── */
    .filename-preview {
        font-family: monospace; font-size: 0.85rem; color: #475569;
        background: #f8fafc; border: 1px solid #e2e8f0;
        border-radius: 6px; padding: 6px 12px; margin: 0.3rem 0 0.8rem 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Header ───────────────────────────────────────────────────────────────────

st.markdown(
    '<div class="app-header">'
    "<h1>Resume Polisher</h1>"
    "<p>AI-powered resume evaluation, matching, and optimization</p>"
    "</div>",
    unsafe_allow_html=True,
)

# ── Progress stepper ─────────────────────────────────────────────────────────

current = _current_step()
stepper_html = '<div class="stepper">'
for i, label in enumerate(STEP_LABELS, 1):
    if i < current:
        cls = "done"
        circle = "✓"
    elif i == current:
        cls = "active"
        circle = str(i)
    else:
        cls = ""
        circle = str(i)
    stepper_html += (
        f'<div class="step {cls}">'
        f'<div class="step-circle {cls}">{circle}</div>'
        f'<div class="step-label {cls}">{label}</div>'
        f'</div>'
    )
stepper_html += '</div>'
st.markdown(stepper_html, unsafe_allow_html=True)

# ── Sidebar – settings ───────────────────────────────────────────────────────

with st.sidebar:
    st.header("Settings")

    provider_name = st.selectbox("Provider", list(PROVIDERS.keys()), key="provider")
    provider = PROVIDERS[provider_name]

    saved_key = _get_saved_key()
    api_key = st.text_input(
        "API Key",
        value=saved_key,
        type="password",
        help=provider["key_help"],
        key="api_key_input",
    )
    active_model = st.selectbox("Model", provider["models"], index=0, key="model")

    if not saved_key:
        st.divider()
        st.markdown("**Save your LLM API key**")
        st.markdown(
            "Create a file at\n"
            "`resume_polisher/.streamlit/secrets.toml`\n"
            "with this content:"
        )
        st.code('api_key = "paste-your-key-here"', language="toml")
        st.caption("The key stays on your machine and is never uploaded.")

    st.divider()
    st.markdown("**How to use**")
    st.markdown(
        "1. Upload your `.docx`, `.pdf`, or `.doc` resumes\n"
        "2. Paste the job description\n"
        "3. Click **Match Best Resume**\n"
        "4. Get improvement suggestions\n"
        "5. Generate optimized resume & review\n"
        "6. Export\n"
        "7. Generate and export a cover letter"
    )

base_url = provider["base_url"]
json_mode = provider["json_mode"]

# ── Step 1 — Job Description ─────────────────────────────────────────────────

st.subheader("1 — Job Description", help=STEP_TOOLTIPS[1])

def _fill_sample():
    st.session_state["job_desc_input"] = SAMPLE_JD

col_jd, col_sample = st.columns([4, 1])
with col_sample:
    st.button("Try sample", on_click=_fill_sample, use_container_width=True)

job_desc = st.text_area(
    "Paste the job description below",
    height=220,
    placeholder="Copy-paste the full job posting here…",
    key="job_desc_input",
)

# ── Step 2 — Your Resumes ────────────────────────────────────────────────────

st.subheader("2 — Your Resumes", help=STEP_TOOLTIPS[2])

uploaded_files = st.file_uploader(
    "Upload resumes (.docx, .pdf, .doc)",
    type=["docx", "pdf", "doc"],
    accept_multiple_files=True,
    help="Drag and drop one or more .docx, .pdf, or .doc resume files.",
)

all_resumes: list[Resume] = []

if uploaded_files:
    for uf in uploaded_files:
        try:
            resume = read_resume_from_bytes(uf.getvalue(), uf.name)
            all_resumes.append(resume)
        except Exception as e:
            st.warning(f"Could not parse {uf.name}: {e}")

folder_resumes = load_resumes(RESUMES_DIR)
for r in folder_resumes:
    if r.filename not in [ar.filename for ar in all_resumes]:
        all_resumes.append(r)

if all_resumes:
    st.success(f"**{len(all_resumes)}** resume(s) loaded")
    selected_filenames = st.multiselect(
        "Select resumes to use",
        options=[r.filename for r in all_resumes],
        default=[r.filename for r in all_resumes],
        help="Only selected resumes will be sent to the API.",
    )
    selected_resumes: list[Resume] = [r for r in all_resumes if r.filename in selected_filenames]
    with st.expander("Preview loaded resumes"):
        for r in selected_resumes:
            st.markdown(f"**{r.filename}** — *{r.name}*")
            st.text(r.full_text[:500] + ("…" if len(r.full_text) > 500 else ""))
            st.divider()
else:
    st.info("Upload your `.docx`, `.pdf`, or `.doc` resumes above to get started.")
    selected_resumes = []

# ── Step 3 — Match & Score ───────────────────────────────────────────────────

st.subheader("3 — Match Best Resume & Fit Score", help=STEP_TOOLTIPS[3])

if not api_key:
    st.info("Enter your API key in the sidebar to enable AI features.")

if job_desc and selected_resumes:
    jt = _estimate_tokens(job_desc)
    rt = sum(_estimate_tokens(r.full_text) for r in selected_resumes)
    est = _estimate_cost(len(selected_resumes), jt, rt, active_model)
    st.markdown(f'<div class="token-est">Estimated: {est}</div>', unsafe_allow_html=True)

match_btn = st.button(
    f"Match Best Resume Version & Provide Fit Score ({len(selected_resumes)} resume{'s' if len(selected_resumes) != 1 else ''})",
    disabled=not (api_key and job_desc and selected_resumes),
    use_container_width=True,
    type="primary",
)

if match_btn:
    with st.spinner("Analyzing resumes against the job description…"):
        try:
            results = match_resumes(job_desc, selected_resumes, api_key, active_model, base_url, json_mode)
            st.session_state["match_results"] = results
        except Exception as e:
            st.error(f"Error during matching: {e}")

if "match_results" in st.session_state:
    results = st.session_state["match_results"]
    best = results.get("best_resume", "")

    st.markdown(f"**Best resume:** `{best}`")
    st.markdown(f"*{results.get('recommendation', '')}*")

    for entry in results.get("results", []):
        score = entry.get("score", 0)
        css_class = "score-high" if score >= 75 else "score-medium" if score >= 50 else "score-low"
        with st.container():
            c1, c2 = st.columns([1, 3])
            c1.markdown(
                f'<span class="score-badge {css_class}">{score}%</span>',
                unsafe_allow_html=True,
            )
            c1.caption(entry.get("filename", "?"))
            c2.write(entry.get("explanation", ""))

# ── Step 4 — Improvement Recommendations ─────────────────────────────────────

st.subheader("4 — Improvement Recommendations", help=STEP_TOOLTIPS[4])

resume_names = [r.filename for r in selected_resumes]
best_resume_name = ""
if "match_results" in st.session_state:
    best_resume_name = st.session_state["match_results"].get("best_resume", "")

if resume_names:
    if best_resume_name in resume_names:
        selected_resume_name = best_resume_name
        st.info(f"Auto-selected best match from Step 3: `{selected_resume_name}`")
    else:
        selected_resume_name = resume_names[0]
        st.caption(f"No Step 3 best-match result found yet. Using `{selected_resume_name}`.")
else:
    selected_resume_name = "(no resumes loaded)"

selected_resume: Resume | None = next(
    (r for r in selected_resumes if r.filename == selected_resume_name), None
)

if job_desc and selected_resume:
    jt = _estimate_tokens(job_desc)
    rt = _estimate_tokens(selected_resume.full_text)
    est = _estimate_cost(1, jt, rt, active_model)
    st.markdown(f'<div class="token-est">Estimated: {est}</div>', unsafe_allow_html=True)

improve_btn = st.button(
    "Get Improvement Suggestions",
    disabled=not (api_key and job_desc and selected_resume),
    use_container_width=True,
)

if improve_btn and selected_resume:
    with st.spinner("Generating improvement suggestions…"):
        try:
            improvements = get_improvements(job_desc, selected_resume, api_key, active_model, base_url, json_mode)
            st.session_state["improvements"] = improvements
        except Exception as e:
            st.error(f"Error: {e}")

if "improvements" in st.session_state:
    imp = st.session_state["improvements"]

    kw = imp.get("keywords", {})
    if kw:
        with st.expander("Keywords extracted from job description", expanded=True):
            cols = st.columns(4)
            for col, (label, key) in zip(cols, [
                ("Hard Skills", "hard_skills"),
                ("Soft Skills", "soft_skills"),
                ("Domain Terms", "domain_terms"),
                ("Action Verbs", "action_verbs"),
            ]):
                items = kw.get(key, [])
                col.markdown(f"**{label}**")
                col.markdown(", ".join(f"`{k}`" for k in items) if items else "*none*")

    if imp.get("overall_tips"):
        st.info(f"**Tips:** {imp['overall_tips']}")

    n_items = len(imp.get("improvements", []))

    def _toggle_all():
        val = st.session_state["select_all_rewrites"]
        for i in range(n_items):
            st.session_state[f"rewrite_{i}"] = val

    sel_all_col1, sel_all_col2 = st.columns([4, 1])
    with sel_all_col2:
        st.checkbox("Select all", value=True, key="select_all_rewrites", on_change=_toggle_all)

    approved_rewrites: list[dict] = []
    for idx, item in enumerate(imp.get("improvements", [])):
        section = item.get("section", "Unknown section")
        original = item.get("original", "(not provided)")
        rewritten = item.get("rewritten") or item.get("suggested") or item.get("improved") or "(not provided)"
        reason = item.get("reason", "")

        col_left, col_right = st.columns([4, 1])
        with col_left:
            with st.expander(f"📝 {section} — rewrite suggestion"):
                st.markdown("**Original:**")
                st.markdown(f"> {original}")
                st.markdown("**Suggested rewrite:**")
                st.markdown(f'<blockquote style="color: #111; border-left: 4px solid #0f3460;">{rewritten}</blockquote>', unsafe_allow_html=True)
                if reason:
                    st.caption(reason)
        with col_right:
            checked = st.checkbox("Accept suggestion", value=True, key=f"rewrite_{idx}")

        if checked:
            approved_rewrites.append({
                "section": section,
                "original": original,
                "rewritten": rewritten,
            })

    st.session_state["approved_rewrites"] = approved_rewrites
    count = len(approved_rewrites)
    total = len(imp.get("improvements", []))
    st.caption(f"{count} of {total} rewrites selected for optimization.")

    if imp.get("bullets_to_remove"):
        st.markdown("---")
        st.markdown("**Bullets to consider removing** (least relevant):")
        for rm in imp["bullets_to_remove"]:
            st.markdown(f"- ~~{rm.get('bullet', '?')}~~ ({rm.get('section', '?')}) — {rm.get('reason', '')}")

# ── Step 5 — Optimize & Review ───────────────────────────────────────────────

st.subheader("5 — Optimize & Review", help=STEP_TOOLTIPS[5])

if job_desc and selected_resume:
    jt = _estimate_tokens(job_desc)
    rt = _estimate_tokens(selected_resume.full_text)
    est = _estimate_cost(1, jt, rt, active_model)
    st.markdown(f'<div class="token-est">Estimated: {est}</div>', unsafe_allow_html=True)

optimize_btn = st.button(
    "Generate Optimized Resume",
    disabled=not (api_key and job_desc and selected_resume),
    use_container_width=True,
    type="primary",
)

if optimize_btn and selected_resume:
    with st.spinner("Optimizing resume…"):
        try:
            approved = st.session_state.get("approved_rewrites", [])
            optimized = optimize_resume(job_desc, selected_resume, api_key, active_model, base_url, json_mode, approved)
            st.session_state["optimized"] = optimized
            st.session_state["optimized_source_resume"] = selected_resume
            st.session_state["export_approved"] = False

            if selected_resume.raw_bytes:
                preview_docx = export_docx(selected_resume.raw_bytes, optimized, OUTPUT_DIR, "Preview")
                preview_pdf = _convert_to_pdf(preview_docx)
                st.session_state["preview_docx_path"] = preview_docx
                st.session_state["preview_pdf_path"] = preview_pdf
        except Exception as e:
            st.error(f"Error: {e}")

if "optimized" in st.session_state:
    opt = st.session_state["optimized"]

    fit_score = opt.get("job_fit_score", 0)
    fit_summary = opt.get("job_fit_summary", "")
    if fit_summary or fit_score:
        score_css = "score-high" if fit_score >= 75 else "score-medium" if fit_score >= 50 else "score-low"
        col_score, col_summary = st.columns([1, 4])
        with col_score:
            st.markdown(
                f'<span class="score-badge {score_css}">{fit_score}%</span>',
                unsafe_allow_html=True,
            )
        with col_summary:
            st.success(f"**Job fit:** {fit_summary}")

    preview_pdf: Path | None = st.session_state.get("preview_pdf_path")
    preview_docx: Path | None = st.session_state.get("preview_docx_path")

    if preview_pdf and preview_pdf.exists():
        pdf_bytes = preview_pdf.read_bytes()
        b64 = base64.b64encode(pdf_bytes).decode()
        st.markdown(
            f'<iframe src="data:application/pdf;base64,{b64}" '
            f'width="100%" height="700" style="border: 1px solid #e2e8f0; border-radius: 8px;"></iframe>',
            unsafe_allow_html=True,
        )
    elif preview_docx and preview_docx.exists():
        st.info("PDF preview not available (LibreOffice required). Showing text preview instead.")
        with st.expander("Preview optimized resume", expanded=True):
            st.markdown(f"### {opt.get('name', '')}")
            for sec in opt.get("sections", []):
                st.markdown(f"**{sec.get('heading', '')}**")
                if sec.get("content"):
                    st.write(sec["content"])
                for b in sec.get("bullets", []):
                    st.markdown(f"- {b}")
    else:
        with st.expander("Preview optimized resume", expanded=True):
            st.markdown(f"### {opt.get('name', '')}")
            for sec in opt.get("sections", []):
                st.markdown(f"**{sec.get('heading', '')}**")
                if sec.get("content"):
                    st.write(sec["content"])
                for b in sec.get("bullets", []):
                    st.markdown(f"- {b}")

# ── Step 6 — Export ──────────────────────────────────────────────────────────

st.subheader("6 — Export", help=STEP_TOOLTIPS[6])

if "optimized" in st.session_state:
    opt_export = st.session_state["optimized"]
    source_resume: Resume | None = st.session_state.get("optimized_source_resume")
    has_original = source_resume and source_resume.raw_bytes

    company_name = st.text_input(
        "Company name (used in the exported filename)",
        value="",
        placeholder="e.g. Google, McKinsey, Tesla…",
        key="company_name_export",
    )

    if company_name.strip():
        cand_name = opt_export.get("name", "Candidate").strip()
        parts = cand_name.split()
        first, last = (parts[0], parts[-1]) if len(parts) >= 2 else (cand_name, "")
        safe = lambda s: s.replace(" ", "_").replace("/", "_")
        preview_stem = f"{safe(first)}_{safe(last)}_Resume_{safe(company_name.strip())}"
        st.markdown(
            f'<div class="filename-preview">📁 {preview_stem}.docx &nbsp;/&nbsp; {preview_stem}.pdf</div>',
            unsafe_allow_html=True,
        )

    if not has_original:
        st.warning(
            "A .docx template is required for export-preserving formatting. "
            "Use a .docx resume (or a .doc that can be converted) for full export."
        )

    col_exp_word, col_exp_pdf = st.columns(2)

    with col_exp_word:
        word_btn = st.button(
            "Export to Word",
            disabled=not (has_original and company_name.strip()),
            use_container_width=True,
            type="primary",
        )

    with col_exp_pdf:
        pdf_btn = st.button(
            "Export to PDF",
            disabled=not (has_original and company_name.strip()),
            use_container_width=True,
            type="primary",
        )

    if word_btn and has_original:
        with st.spinner("Generating Word file…"):
            try:
                docx_path = export_docx(source_resume.raw_bytes, opt_export, OUTPUT_DIR, company_name.strip())
                st.session_state["export_docx_path"] = docx_path
                st.session_state["export_word_done"] = True
                st.session_state["export_word_celebrated"] = False
            except Exception as e:
                st.error(f"Error: {e}")

    if pdf_btn and has_original:
        with st.spinner("Generating PDF…"):
            try:
                docx_path = export_docx(source_resume.raw_bytes, opt_export, OUTPUT_DIR, company_name.strip())
                pdf_path = _convert_to_pdf(docx_path)
                st.session_state["export_docx_path"] = docx_path
                st.session_state["export_pdf_path"] = pdf_path
                st.session_state["export_pdf_done"] = True
                st.session_state["export_pdf_celebrated"] = False
            except Exception as e:
                st.error(f"Error: {e}")

    if st.session_state.get("export_word_done"):
        docx_path: Path | None = st.session_state.get("export_docx_path")
        if docx_path and docx_path.exists():
            if not st.session_state.get("export_word_celebrated", False):
                st.balloons()
                st.session_state["export_word_celebrated"] = True
            st.success(f"Ready: `{docx_path.name}`")
            with open(docx_path, "rb") as f:
                st.download_button(
                    label="Download .docx",
                    data=f.read(),
                    file_name=docx_path.name,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                )

    if st.session_state.get("export_pdf_done"):
        pdf_path: Path | None = st.session_state.get("export_pdf_path")
        if pdf_path and pdf_path.exists():
            if not st.session_state.get("export_pdf_celebrated", False):
                st.balloons()
                st.session_state["export_pdf_celebrated"] = True
            st.success(f"Ready: `{pdf_path.name}`")
            with open(pdf_path, "rb") as f:
                st.download_button(
                    label="Download .pdf",
                    data=f.read(),
                    file_name=pdf_path.name,
                    mime="application/pdf",
                    use_container_width=True,
                )
        else:
            st.warning("PDF conversion requires LibreOffice. Try exporting to Word instead.")
else:
    st.info("Generate an optimized resume in step 5 first.")

# ── Step 7 — Cover Letter ────────────────────────────────────────────────────

st.subheader("7 — Cover Letter", help=STEP_TOOLTIPS[7])

if "cover_letter_company_name" not in st.session_state:
    st.session_state["cover_letter_company_name"] = st.session_state.get("company_name_export", "")
if "cover_letter_chat_open" not in st.session_state:
    st.session_state["cover_letter_chat_open"] = False
if "cover_letter_chat_history" not in st.session_state:
    st.session_state["cover_letter_chat_history"] = []

optimized_source = st.session_state.get("optimized")
fallback_resume: Resume | None = None
fallback_name = ""

if not optimized_source and "match_results" in st.session_state:
    best_name = st.session_state["match_results"].get("best_resume", "")
    # Use the Step 3 best match even if it is not currently selected in Step 2.
    fallback_resume = next((r for r in all_resumes if r.filename == best_name), None)
    fallback_name = best_name

source_label, source_candidate_name, source_resume_text = resume_payload_from_source(
    optimized_source, fallback_resume
)

if source_label == "optimized_resume_step_5":
    st.success("Using optimized resume from Step 5 as cover letter source.")
elif source_label == "best_resume_step_3":
    st.info(f"Using best matched resume from Step 3: `{fallback_name}`.")
else:
    st.warning(
        "No source resume available yet. Generate an optimized resume in Step 5, "
        "or run Step 3 matching so the best resume can be used."
    )

if source_label:
    st.session_state["cover_letter_source_meta"] = {
        "source": source_label,
        "candidate_name": source_candidate_name,
        "fallback_resume_filename": fallback_name,
    }

col_tone, col_length = st.columns(2)
with col_tone:
    tone = st.selectbox(
        "Tone / style",
        ["Professional", "Confident", "Warm", "Concise", "Technical", "Casual"],
        key="cover_letter_tone",
    )
with col_length:
    length = st.selectbox(
        "Length",
        ["Short (150)", "Standard (250)", "Long (400-500)"],
        key="cover_letter_length",
    )

col_hm, col_job = st.columns(2)
with col_hm:
    hiring_manager_name = st.text_input(
        "Hiring manager name (optional)",
        key="cover_letter_hiring_manager_name",
        placeholder="e.g. Alex Johnson",
    )
with col_job:
    job_title_cl = st.text_input(
        "Job title (optional)",
        key="cover_letter_job_title",
        placeholder="e.g. Senior Data Scientist",
    )

company_name_cl = st.text_input(
    "Company name (optional for draft; required for export filename)",
    key="cover_letter_company_name",
    placeholder="e.g. Google",
)
why_company = st.text_area(
    "Why this company (optional)",
    key="cover_letter_why_company",
    height=90,
    placeholder="Optional: mention what attracts you to this company.",
)
why_position = st.text_area(
    "Why this position (optional)",
    key="cover_letter_why_position",
    height=90,
    placeholder="Optional: mention why this role is a strong fit.",
)

generate_disabled = not (api_key and job_desc and source_label)

col_gen, col_regen, col_improve = st.columns(3)
with col_gen:
    gen_btn = st.button(
        "Generate Cover Letter",
        disabled=generate_disabled,
        use_container_width=True,
        type="primary",
    )
with col_regen:
    regen_btn = st.button(
        "Regenerate",
        disabled=generate_disabled,
        use_container_width=True,
    )
with col_improve:
    improve_draft_btn = st.button(
        "Improve This Draft",
        disabled=generate_disabled or not st.session_state.get("cover_letter_edited_draft"),
        use_container_width=True,
    )

if gen_btn or regen_btn:
    with st.spinner("Generating cover letter…"):
        try:
            cl_result = generate_cover_letter(
                job_description=job_desc,
                resume_text=source_resume_text,
                api_key=api_key,
                model=active_model,
                base_url=base_url,
                json_mode=json_mode,
                tone=tone,
                length=length,
                hiring_manager_name=hiring_manager_name,
                job_title=job_title_cl,
                company_name=company_name_cl,
                why_company=why_company,
                why_position=why_position,
                existing_draft="",
                improve_mode=False,
            )
            draft = (cl_result.get("draft") or "").strip()
            st.session_state["cover_letter_generated"] = draft
            st.session_state["cover_letter_edited_draft"] = draft
            st.session_state["cover_letter_soft_skills_used"] = cl_result.get("soft_skills_used", [])
            st.session_state["cover_letter_chat_history"] = []
            st.session_state["cover_letter_chat_open"] = False
        except Exception as e:
            st.error(f"Error generating cover letter: {e}")

if improve_draft_btn:
    st.session_state["cover_letter_chat_open"] = True

if st.session_state.get("cover_letter_generated"):
    if st.session_state.get("cover_letter_soft_skills_used"):
        skills = st.session_state["cover_letter_soft_skills_used"]
        st.caption("Soft skills emphasized: " + ", ".join(f"`{s}`" for s in skills))

    st.text_area(
        "Edit your cover letter draft (modern simplified format)",
        key="cover_letter_edited_draft",
        height=320,
    )

    if st.session_state.get("cover_letter_chat_open"):
        st.markdown("### Cover letter revision chat")
        st.caption("Give concrete feedback (e.g., make it shorter, add stronger leadership language).")

        for msg in st.session_state.get("cover_letter_chat_history", []):
            with st.chat_message("user" if msg.get("role") == "user" else "assistant"):
                st.write(msg.get("content", ""))

        feedback = st.text_area(
            "How should the draft be improved?",
            key="cover_letter_feedback_input",
            height=90,
            placeholder="E.g., make it shorter, emphasize leadership, and reduce generic phrasing.",
        )
        send_feedback = st.button(
            "Apply Feedback",
            key="cover_letter_apply_feedback_btn",
            use_container_width=True,
        )
        if send_feedback and feedback.strip():
            st.session_state["cover_letter_chat_history"].append({
                "role": "user",
                "content": feedback.strip(),
            })
            with st.spinner("Revising draft with your feedback…"):
                try:
                    cl_result = revise_cover_letter_with_feedback(
                        job_description=job_desc,
                        resume_text=source_resume_text,
                        current_draft=st.session_state.get("cover_letter_edited_draft", ""),
                        feedback=feedback.strip(),
                        api_key=api_key,
                        model=active_model,
                        base_url=base_url,
                        json_mode=json_mode,
                        tone=tone,
                        length=length,
                        hiring_manager_name=hiring_manager_name,
                        job_title=job_title_cl,
                        company_name=company_name_cl,
                        why_company=why_company,
                        why_position=why_position,
                        chat_history=st.session_state.get("cover_letter_chat_history", []),
                    )
                    draft = (cl_result.get("draft") or "").strip()
                    st.session_state["cover_letter_generated"] = draft
                    st.session_state["cover_letter_edited_draft"] = draft
                    st.session_state["cover_letter_soft_skills_used"] = cl_result.get("soft_skills_used", [])
                    st.session_state["cover_letter_chat_history"].append({
                        "role": "assistant",
                        "content": draft,
                    })
                    st.rerun()
                except Exception as e:
                    st.error(f"Error improving draft: {e}")
        elif send_feedback:
            st.warning("Enter feedback before applying changes.")

    export_ready = bool(st.session_state.get("cover_letter_edited_draft", "").strip() and company_name_cl.strip())
    if not company_name_cl.strip():
        st.caption("Add company name to enable cover letter export.")

    cexp_docx, cexp_pdf = st.columns(2)
    with cexp_docx:
        export_cl_docx_btn = st.button(
            "Export Cover Letter to Word",
            disabled=not export_ready,
            use_container_width=True,
            type="primary",
        )
    with cexp_pdf:
        export_cl_pdf_btn = st.button(
            "Export Cover Letter to PDF",
            disabled=not export_ready,
            use_container_width=True,
            type="primary",
        )

    if export_cl_docx_btn:
        with st.spinner("Generating cover letter .docx…"):
            try:
                business_text = build_export_letter(
                    draft_body=st.session_state["cover_letter_edited_draft"],
                    candidate_name=source_candidate_name,
                    hiring_manager_name=hiring_manager_name,
                    job_title=job_title_cl,
                    company_name=company_name_cl,
                )
                cl_docx = export_cover_letter_docx(
                    cover_letter_text=business_text,
                    candidate_name=source_candidate_name,
                    company_name=company_name_cl,
                    output_dir=OUTPUT_DIR,
                )
                st.session_state["cover_letter_docx_path"] = cl_docx
                st.session_state["cover_letter_export_docx_done"] = True
            except Exception as e:
                st.error(f"Export error: {e}")

    if export_cl_pdf_btn:
        with st.spinner("Generating cover letter PDF…"):
            try:
                business_text = build_export_letter(
                    draft_body=st.session_state["cover_letter_edited_draft"],
                    candidate_name=source_candidate_name,
                    hiring_manager_name=hiring_manager_name,
                    job_title=job_title_cl,
                    company_name=company_name_cl,
                )
                cl_docx = export_cover_letter_docx(
                    cover_letter_text=business_text,
                    candidate_name=source_candidate_name,
                    company_name=company_name_cl,
                    output_dir=OUTPUT_DIR,
                )
                cl_pdf = _convert_to_pdf(cl_docx)
                st.session_state["cover_letter_docx_path"] = cl_docx
                st.session_state["cover_letter_pdf_path"] = cl_pdf
                st.session_state["cover_letter_export_pdf_done"] = True
            except Exception as e:
                st.error(f"Export error: {e}")

    if st.session_state.get("cover_letter_export_docx_done"):
        cl_docx_path: Path | None = st.session_state.get("cover_letter_docx_path")
        if cl_docx_path and cl_docx_path.exists():
            with open(cl_docx_path, "rb") as f:
                st.download_button(
                    label="Download Cover Letter (.docx)",
                    data=f.read(),
                    file_name=cl_docx_path.name,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                )

    if st.session_state.get("cover_letter_export_pdf_done"):
        cl_pdf_path: Path | None = st.session_state.get("cover_letter_pdf_path")
        if cl_pdf_path and cl_pdf_path.exists():
            with open(cl_pdf_path, "rb") as f:
                st.download_button(
                    label="Download Cover Letter (.pdf)",
                    data=f.read(),
                    file_name=cl_pdf_path.name,
                    mime="application/pdf",
                    use_container_width=True,
                )
        else:
            st.warning("PDF conversion requires LibreOffice. Try exporting to Word instead.")
