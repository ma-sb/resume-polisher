"""Resume Polisher – Streamlit application."""

import streamlit as st
from pathlib import Path

from core.reader import load_resumes, read_docx_from_bytes, Resume
from core.matcher import PROVIDERS, match_resumes, get_improvements, optimize_resume
from core.exporter import export

RESUMES_DIR = Path(__file__).parent / "resumes"
OUTPUT_DIR = Path(__file__).parent / "output"


def _get_saved_key() -> str:
    """Read API key from Streamlit secrets if available."""
    try:
        return st.secrets.get("api_key", "")
    except Exception:
        return ""


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
        margin-bottom: 1.5rem;
    }
    .app-header h1 {
        margin: 0; font-size: 2rem; font-weight: 700; letter-spacing: -0.5px;
    }
    .app-header p {
        margin: 0.4rem 0 0 0; opacity: 0.8; font-size: 0.95rem;
    }

    /* ── Section step labels ─────────────────────────────── */
    div[data-testid="stSubheader"] > div > p,
    .stSubheader {
        border-left: 4px solid #0f3460;
        padding-left: 0.75rem;
    }

    /* ── Metrics / score cards ───────────────────────────── */
    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #f0f4ff 0%, #f8f9fb 100%);
        border-radius: 10px;
        padding: 14px 18px;
        border: 1px solid #e2e8f0;
    }
    div[data-testid="stMetricValue"] > div {
        font-weight: 700; color: #1a1a2e;
    }

    /* ── Expanders ───────────────────────────────────────── */
    details[data-testid="stExpander"] {
        border: 1px solid #e2e8f0 !important;
        border-radius: 8px !important;
        margin-bottom: 0.5rem;
        transition: box-shadow 0.2s ease;
    }
    details[data-testid="stExpander"]:hover {
        box-shadow: 0 2px 8px rgba(15, 52, 96, 0.08);
    }
    details[data-testid="stExpander"] summary {
        font-weight: 500;
    }

    /* ── Buttons ─────────────────────────────────────────── */
    .stButton > button[kind="primary"] {
        border-radius: 8px;
        font-weight: 600;
        letter-spacing: 0.3px;
    }

    /* ── Sidebar ─────────────────────────────────────────── */
    section[data-testid="stSidebar"] {
        background: #fafbfc;
    }
    section[data-testid="stSidebar"] .stSelectbox label,
    section[data-testid="stSidebar"] .stTextInput label {
        font-size: 0.85rem;
        font-weight: 600;
        color: #374151;
    }

    /* ── File uploader ───────────────────────────────────── */
    div[data-testid="stFileUploader"] section {
        border: 2px dashed #cbd5e1 !important;
        border-radius: 10px !important;
        transition: border-color 0.2s ease;
    }
    div[data-testid="stFileUploader"] section:hover {
        border-color: #0f3460 !important;
    }

    /* ── Success / info alerts ───────────────────────────── */
    div[data-testid="stAlert"] {
        border-radius: 8px;
    }

    /* ── Score badge ─────────────────────────────────────── */
    .score-badge {
        display: inline-block;
        padding: 4px 14px;
        border-radius: 20px;
        font-weight: 700;
        font-size: 1.1rem;
        color: white;
        min-width: 60px;
        text-align: center;
    }
    .score-high   { background: linear-gradient(135deg, #059669, #10b981); }
    .score-medium { background: linear-gradient(135deg, #d97706, #f59e0b); }
    .score-low    { background: linear-gradient(135deg, #dc2626, #ef4444); }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="app-header">'
    "<h1>Resume Polisher</h1>"
    "<p>AI-powered resume evaluation, matching, and optimization</p>"
    "</div>",
    unsafe_allow_html=True,
)

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
        st.markdown("**Save your API key**")
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
        "1. Upload your `.docx` resumes\n"
        "2. Paste the job description\n"
        "3. Click **Match Best Resume**\n"
        "4. Get improvement suggestions\n"
        "5. Generate optimized resume & review\n"
        "6. Approve → export"
    )

base_url = provider["base_url"]
json_mode = provider["json_mode"]

# ── Load resumes ─────────────────────────────────────────────────────────────

st.subheader("1 — Job Description")
job_desc = st.text_area(
    "Paste the job description below",
    height=220,
    placeholder="Copy-paste the full job posting here…",
)

st.subheader("2 — Your Resumes")

uploaded_files = st.file_uploader(
    "Upload .docx resumes",
    type=["docx"],
    accept_multiple_files=True,
    help="Drag and drop one or more .docx resume files.",
)

all_resumes: list[Resume] = []

if uploaded_files:
    for uf in uploaded_files:
        try:
            resume = read_docx_from_bytes(uf.getvalue(), uf.name)
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
    st.info("Upload your `.docx` resumes above to get started.")
    selected_resumes = []

# ── Matching & Scoring ───────────────────────────────────────────────────────

st.subheader("3 — Match Best Resume & Fit Score")

if not api_key:
    st.info("Enter your API key in the sidebar to enable AI features.")

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

# ── Improvement Recommendations ──────────────────────────────────────────────

st.subheader("4 — Improvement Recommendations")

resume_names = [r.filename for r in selected_resumes]
selected_resume_name = st.selectbox(
    "Choose a resume to improve",
    resume_names if resume_names else ["(no resumes loaded)"],
)

selected_resume: Resume | None = next(
    (r for r in selected_resumes if r.filename == selected_resume_name), None
)

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
                st.markdown(f"> {rewritten}")
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

# ── Optimize & Review ────────────────────────────────────────────────────────

st.subheader("5 — Optimize & Review")

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
            st.session_state.pop("export_docx_path", None)
            st.session_state.pop("export_pdf_path", None)
            st.session_state["export_approved"] = False
        except Exception as e:
            st.error(f"Error: {e}")

if "optimized" in st.session_state:
    opt = st.session_state["optimized"]

    fit_summary = opt.get("job_fit_summary", "")
    if fit_summary:
        st.success(f"**Job fit:** {fit_summary}")

    with st.expander("Preview optimized resume", expanded=True):
        st.markdown(f"### {opt.get('name', '')}")
        for sec in opt.get("sections", []):
            st.markdown(f"**{sec.get('heading', '')}**")
            if sec.get("content"):
                st.write(sec["content"])
            for b in sec.get("bullets", []):
                st.markdown(f"- {b}")

# ── Export ───────────────────────────────────────────────────────────────────

st.subheader("6 — Export")

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

    if not has_original:
        st.warning("Original .docx bytes not available — export will use a basic format.")

    export_btn = st.button(
        "Export",
        disabled=not (has_original and company_name.strip()),
        use_container_width=True,
        type="primary",
    )

    if export_btn and has_original:
        with st.spinner("Generating files (preserving original formatting)…"):
            try:
                docx_path, pdf_path = export(source_resume.raw_bytes, opt_export, OUTPUT_DIR, company_name.strip())
                st.session_state["export_docx_path"] = docx_path
                st.session_state["export_pdf_path"] = pdf_path
                st.session_state["export_approved"] = True
            except Exception as e:
                st.error(f"Error: {e}")

    if st.session_state.get("export_approved"):
        docx_path: Path | None = st.session_state.get("export_docx_path")
        pdf_path: Path | None = st.session_state.get("export_pdf_path")

        if docx_path and docx_path.exists():
            st.success(f"Exported: `{docx_path.name}`")
            col_dl1, col_dl2 = st.columns(2)
            with col_dl1:
                with open(docx_path, "rb") as f:
                    st.download_button(
                        label="Download .docx",
                        data=f.read(),
                        file_name=docx_path.name,
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True,
                    )
            with col_dl2:
                if pdf_path and pdf_path.exists():
                    with open(pdf_path, "rb") as f:
                        st.download_button(
                            label="Download .pdf",
                            data=f.read(),
                            file_name=pdf_path.name,
                            mime="application/pdf",
                            use_container_width=True,
                        )
                else:
                    st.caption("PDF conversion requires LibreOffice. Download the .docx and convert manually, or install LibreOffice.")
else:
    st.info("Generate an optimized resume in step 5 first.")
