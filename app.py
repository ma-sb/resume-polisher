"""Resume Polisher – Streamlit application."""

import streamlit as st
from pathlib import Path

from core.reader import load_resumes, read_docx_from_bytes, Resume
from core.matcher import PROVIDERS, match_resumes, get_improvements, optimize_resume
from core.exporter import export_pdf

RESUMES_DIR = Path(__file__).parent / "resumes"
OUTPUT_DIR = Path(__file__).parent / "output"

# ── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(page_title="Resume Polisher", page_icon="📄", layout="wide")

st.markdown(
    """
    <style>
    .block-container {padding-top: 2rem;}
    div[data-testid="stMetric"] {
        background: #f8f9fb; border-radius: 8px; padding: 12px 16px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("Resume Polisher")
st.caption("AI-powered resume evaluation, matching, and optimization")

# ── Sidebar – settings ───────────────────────────────────────────────────────

with st.sidebar:
    st.header("Settings")

    provider_name = st.selectbox("Provider", list(PROVIDERS.keys()))
    provider = PROVIDERS[provider_name]

    api_key = st.text_input(
        "API Key",
        type="password",
        help=provider["key_help"],
    )
    active_model = st.selectbox("Model", provider["models"], index=0)

    st.divider()
    company_name = st.text_input("Company name (for PDF filename)", value="Company")
    st.divider()
    st.markdown("**How to use**")
    st.markdown(
        "1. Upload your `.docx` resumes\n"
        "2. Paste the job description\n"
        "3. Click **Match & Score**\n"
        "4. Get improvement suggestions\n"
        "5. Generate optimized resume & review\n"
        "6. Approve → export PDF"
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

st.subheader("3 — Match & Score")

if not api_key:
    st.info("Enter your API key in the sidebar to enable AI features.")

match_btn = st.button(
    f"Match & Score ({len(selected_resumes)} resume{'s' if len(selected_resumes) != 1 else ''})",
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
        icon = "🟢" if score >= 75 else "🟡" if score >= 50 else "🔴"
        with st.container():
            c1, c2 = st.columns([1, 3])
            c1.metric(entry.get("filename", "?"), f"{score}%", label_visibility="visible")
            c2.write(f"{icon} {entry.get('explanation', '')}")

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

    for item in imp.get("improvements", []):
        section = item.get("section", "Unknown section")
        original = item.get("original", "(not provided)")
        rewritten = item.get("rewritten") or item.get("suggested") or item.get("improved") or "(not provided)"
        reason = item.get("reason", "")

        with st.expander(f"📝 {section} — rewrite suggestion"):
            st.markdown("**Original:**")
            st.markdown(f"> {original}")
            st.markdown("**Suggested rewrite:**")
            st.markdown(f"> {rewritten}")
            if reason:
                st.caption(reason)

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
            optimized = optimize_resume(job_desc, selected_resume, api_key, active_model, base_url, json_mode)
            st.session_state["optimized"] = optimized
            st.session_state.pop("pdf_path", None)
            st.session_state["export_approved"] = False
        except Exception as e:
            st.error(f"Error: {e}")

if "optimized" in st.session_state:
    opt = st.session_state["optimized"]

    fit_summary = opt.get("job_fit_summary", "")
    if fit_summary:
        st.success(f"**Job fit:** {fit_summary}")

    with st.expander("Review optimized resume", expanded=True):
        st.markdown(f"### {opt.get('name', '')}")
        for sec in opt.get("sections", []):
            st.markdown(f"**{sec.get('heading', '')}**")
            if sec.get("content"):
                st.write(sec["content"])
            for b in sec.get("bullets", []):
                st.markdown(f"- {b}")

    # ── Approve & Export ─────────────────────────────────────────────────────

    st.subheader("6 — Approve & Export PDF")

    approve_btn = st.button(
        "Approve & Export as PDF",
        use_container_width=True,
        type="primary",
    )

    if approve_btn:
        with st.spinner("Generating PDF…"):
            try:
                pdf_path = export_pdf(opt, OUTPUT_DIR, company_name)
                st.session_state["pdf_path"] = pdf_path
                st.session_state["export_approved"] = True
            except Exception as e:
                st.error(f"Error: {e}")

    if st.session_state.get("export_approved") and "pdf_path" in st.session_state:
        pdf_path: Path = st.session_state["pdf_path"]
        if pdf_path.exists():
            st.success(f"PDF exported: `{pdf_path.name}`")
            with open(pdf_path, "rb") as f:
                st.download_button(
                    label=f"Download {pdf_path.name}",
                    data=f.read(),
                    file_name=pdf_path.name,
                    mime="application/pdf",
                    use_container_width=True,
                )
