"""Resume Polisher – Streamlit application."""

import streamlit as st
from pathlib import Path

from core.reader import load_resumes, Resume
from core.matcher import match_resumes, get_improvements, optimize_resume
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
    api_key = st.text_input("OpenAI API Key", type="password", help="Your key is never stored.")
    model = st.selectbox("Model", ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo"], index=0)
    resumes_folder = st.text_input(
        "Resumes folder",
        value=str(RESUMES_DIR),
        help="Absolute path to a folder containing .docx resumes.",
    )
    company_name = st.text_input("Company name (for PDF filename)", value="Company")
    st.divider()
    st.markdown("**How to use**")
    st.markdown(
        "1. Put your `.docx` resumes in the resumes folder\n"
        "2. Paste the job description\n"
        "3. Click **Match Best Resume**\n"
        "4. Review suggestions and export"
    )

# ── Load resumes ─────────────────────────────────────────────────────────────

resumes_path = Path(resumes_folder)
resumes: list[Resume] = load_resumes(resumes_path)

st.subheader("1 — Job Description")
job_desc = st.text_area(
    "Paste the job description below",
    height=220,
    placeholder="Copy-paste the full job posting here…",
)

st.subheader("2 — Your Resumes")
if resumes:
    st.success(f"Found **{len(resumes)}** resume(s) in `{resumes_path}`")
    with st.expander("Preview loaded resumes"):
        for r in resumes:
            st.markdown(f"**{r.filename}** — *{r.name}*")
            st.text(r.full_text[:500] + ("…" if len(r.full_text) > 500 else ""))
            st.divider()
else:
    st.warning(f"No `.docx` files found in `{resumes_path}`. Add your resumes and reload.")

# ── Matching & Scoring ───────────────────────────────────────────────────────

st.subheader("3 — Match & Score")

if not api_key:
    st.info("Enter your OpenAI API key in the sidebar to enable AI features.")

col_match, col_improve = st.columns(2)

with col_match:
    match_btn = st.button(
        "Match & Score All Resumes",
        disabled=not (api_key and job_desc and resumes),
        use_container_width=True,
        type="primary",
    )

if match_btn:
    with st.spinner("Analyzing resumes against the job description…"):
        try:
            results = match_resumes(job_desc, resumes, api_key, model)
            st.session_state["match_results"] = results
        except Exception as e:
            st.error(f"Error during matching: {e}")

if "match_results" in st.session_state:
    results = st.session_state["match_results"]
    best = results.get("best_resume", "")

    st.markdown(f"**Best resume:** `{best}`")
    st.markdown(f"*{results.get('recommendation', '')}*")

    for entry in results.get("results", []):
        score = entry["score"]
        icon = "🟢" if score >= 75 else "🟡" if score >= 50 else "🔴"
        with st.container():
            c1, c2 = st.columns([1, 3])
            c1.metric(entry["filename"], f"{score}%", label_visibility="visible")
            c2.write(f"{icon} {entry['explanation']}")

# ── Improvement Recommendations ──────────────────────────────────────────────

st.subheader("4 — Improvement Recommendations")

resume_names = [r.filename for r in resumes]
selected_resume_name = st.selectbox(
    "Choose a resume to improve",
    resume_names if resume_names else ["(no resumes loaded)"],
)

selected_resume: Resume | None = next(
    (r for r in resumes if r.filename == selected_resume_name), None
)

improve_btn = st.button(
    "Get Improvement Suggestions",
    disabled=not (api_key and job_desc and selected_resume),
    use_container_width=True,
)

if improve_btn and selected_resume:
    with st.spinner("Generating improvement suggestions…"):
        try:
            improvements = get_improvements(job_desc, selected_resume, api_key, model)
            st.session_state["improvements"] = improvements
        except Exception as e:
            st.error(f"Error: {e}")

if "improvements" in st.session_state:
    imp = st.session_state["improvements"]

    if imp.get("overall_tips"):
        st.info(f"**Tips:** {imp['overall_tips']}")

    for item in imp.get("improvements", []):
        with st.expander(f"📝 {item['section']} — rewrite suggestion"):
            st.markdown("**Original:**")
            st.markdown(f"> {item['original']}")
            st.markdown("**Suggested rewrite:**")
            st.markdown(f"> {item['rewritten']}")
            st.caption(item.get("reason", ""))

    if imp.get("bullets_to_remove"):
        st.markdown("---")
        st.markdown("**Bullets to consider removing** (least relevant):")
        for rm in imp["bullets_to_remove"]:
            st.markdown(f"- ~~{rm['bullet']}~~ ({rm['section']}) — {rm['reason']}")

# ── Optimize & Export ────────────────────────────────────────────────────────

st.subheader("5 — Optimize & Export PDF")

optimize_btn = st.button(
    "Optimize & Export as PDF",
    disabled=not (api_key and job_desc and selected_resume),
    use_container_width=True,
    type="primary",
)

if optimize_btn and selected_resume:
    with st.spinner("Optimizing resume and generating PDF…"):
        try:
            optimized = optimize_resume(job_desc, selected_resume, api_key, model)
            st.session_state["optimized"] = optimized

            pdf_path = export_pdf(optimized, OUTPUT_DIR, company_name)
            st.session_state["pdf_path"] = pdf_path
            st.success(f"PDF exported: `{pdf_path.name}`")
        except Exception as e:
            st.error(f"Error: {e}")

if "pdf_path" in st.session_state:
    pdf_path: Path = st.session_state["pdf_path"]
    if pdf_path.exists():
        with open(pdf_path, "rb") as f:
            st.download_button(
                label=f"Download {pdf_path.name}",
                data=f.read(),
                file_name=pdf_path.name,
                mime="application/pdf",
                use_container_width=True,
            )

if "optimized" in st.session_state:
    with st.expander("Preview optimized resume"):
        opt = st.session_state["optimized"]
        st.markdown(f"### {opt.get('name', '')}")
        for sec in opt.get("sections", []):
            st.markdown(f"**{sec['heading']}**")
            if sec.get("content"):
                st.write(sec["content"])
            for b in sec.get("bullets", []):
                st.markdown(f"- {b}")
