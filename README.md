# Resume Polisher

AI-powered resume evaluation, matching, and optimization tool.

## Features

1. **Read job descriptions** — paste any job posting directly into the app
2. **Load resumes** — reads all `.docx` files from a configurable folder
3. **Match & score** — ranks every resume against the job and recommends the best fit
4. **Improvement suggestions** — identifies weak bullet points and rewrites them with relevant keywords
5. **Optimize & export** — generates a fully tailored resume and exports it as a clean PDF  
   (`FirstName_LastName_Resume_Company.pdf`)

## Quick start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Drop your .docx resumes into the resumes/ folder

# 3. Run the app
streamlit run app.py
```

Enter your **OpenAI API key** in the sidebar when prompted.

## Project structure

```
resume_polisher/
├── app.py               # Streamlit UI
├── core/
│   ├── reader.py        # .docx parsing
│   ├── matcher.py       # AI scoring, improvements, optimization
│   └── exporter.py      # PDF generation
├── resumes/             # Place .docx resumes here
├── output/              # Exported PDFs land here
└── requirements.txt
```
