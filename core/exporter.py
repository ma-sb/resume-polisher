"""Export an optimized resume to a formatted PDF."""

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
from reportlab.lib.colors import HexColor


def _build_styles():
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle(
        "ResumeName",
        parent=ss["Title"],
        fontSize=18,
        leading=22,
        alignment=TA_CENTER,
        spaceAfter=4,
        textColor=HexColor("#1a1a2e"),
    ))
    ss.add(ParagraphStyle(
        "SectionHeading",
        parent=ss["Heading2"],
        fontSize=12,
        leading=15,
        spaceBefore=10,
        spaceAfter=4,
        textColor=HexColor("#16213e"),
        borderWidth=0,
    ))
    ss.add(ParagraphStyle(
        "BulletItem",
        parent=ss["BodyText"],
        fontSize=10,
        leading=13,
        leftIndent=18,
        bulletIndent=6,
        spaceBefore=2,
        spaceAfter=2,
        textColor=HexColor("#2c2c2c"),
    ))
    ss.add(ParagraphStyle(
        "SectionText",
        parent=ss["BodyText"],
        fontSize=10,
        leading=13,
        spaceBefore=2,
        spaceAfter=2,
        textColor=HexColor("#2c2c2c"),
    ))
    return ss


def export_pdf(
    optimized: dict,
    output_dir: str | Path,
    company_name: str = "Company",
) -> Path:
    """
    Export optimized resume dict to PDF.

    Args:
        optimized: dict with "name" and "sections" keys (from optimizer)
        output_dir: folder to save the PDF
        company_name: used in the filename

    Returns:
        Path to the created PDF file.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    name = optimized.get("name", "Candidate").strip()
    parts = name.split()
    if len(parts) >= 2:
        first, last = parts[0], parts[-1]
    else:
        first, last = name, ""

    safe = lambda s: s.replace(" ", "_").replace("/", "_")
    filename = f"{safe(first)}_{safe(last)}_Resume_{safe(company_name)}.pdf"
    filepath = output_dir / filename

    styles = _build_styles()
    doc = SimpleDocTemplate(
        str(filepath),
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
    )

    story: list = []

    story.append(Paragraph(name, styles["ResumeName"]))
    story.append(Spacer(1, 4))
    story.append(HRFlowable(
        width="100%", thickness=1, color=HexColor("#16213e"),
        spaceBefore=2, spaceAfter=8,
    ))

    for section in optimized.get("sections", []):
        heading = section.get("heading", "")
        content = section.get("content", "")
        bullets = section.get("bullets", [])

        story.append(Paragraph(heading.upper(), styles["SectionHeading"]))
        story.append(HRFlowable(
            width="100%", thickness=0.5, color=HexColor("#cccccc"),
            spaceBefore=0, spaceAfter=4,
        ))

        if content:
            story.append(Paragraph(content, styles["SectionText"]))

        for bullet in bullets:
            story.append(Paragraph(
                f"• {bullet}",
                styles["BulletItem"],
            ))

    doc.build(story)
    return filepath
