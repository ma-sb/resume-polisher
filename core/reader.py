"""Read and parse .docx resume files."""

from pathlib import Path
from dataclasses import dataclass, field
from docx import Document


@dataclass
class ResumeSection:
    heading: str
    bullets: list[str] = field(default_factory=list)
    text: str = ""


@dataclass
class Resume:
    filepath: Path
    filename: str
    full_text: str
    sections: list[ResumeSection] = field(default_factory=list)
    name: str = ""

    @property
    def display_name(self) -> str:
        return self.name or self.filename


def read_docx(filepath: Path) -> Resume:
    """Parse a .docx file into a Resume object with sections and bullet points."""
    doc = Document(str(filepath))
    full_lines: list[str] = []
    sections: list[ResumeSection] = []
    current_section: ResumeSection | None = None
    candidate_name = ""

    for i, para in enumerate(doc.paragraphs):
        text = para.text.strip()
        if not text:
            continue

        full_lines.append(text)

        if i == 0 and not candidate_name:
            candidate_name = text

        is_heading = (
            para.style.name.startswith("Heading")
            or (para.runs and all(r.bold for r in para.runs if r.text.strip()))
        )

        if is_heading and len(text) < 80:
            current_section = ResumeSection(heading=text)
            sections.append(current_section)
        elif current_section is not None:
            if para.style.name.startswith("List") or text.startswith(("•", "-", "–", "◦", "▪")):
                bullet = text.lstrip("•-–◦▪ ")
                current_section.bullets.append(bullet)
            else:
                current_section.text += (" " + text) if current_section.text else text

    return Resume(
        filepath=filepath,
        filename=filepath.name,
        full_text="\n".join(full_lines),
        sections=sections,
        name=candidate_name,
    )


def load_resumes(folder: Path) -> list[Resume]:
    """Load all .docx resumes from a folder."""
    folder = Path(folder)
    if not folder.exists():
        return []
    resumes = []
    for f in sorted(folder.rglob("*.docx")):
        if f.name.startswith("~$"):
            continue
        try:
            resumes.append(read_docx(f))
        except Exception as e:
            print(f"Warning: could not read {f.name}: {e}")
    return resumes
