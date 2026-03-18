#!/usr/bin/env python3
"""
Convert a journal/digest markdown file to a beautifully formatted PDF
with color highlights for the reMarkable Paper Pro Color.

Usage:
    python3 journal_to_pdf.py input.md output.pdf [--title "Custom Title"]
"""

import argparse
import re
import sys
from pathlib import Path

import markdown


def classify_line(line: str) -> str:
    """Classify a line for color highlighting."""
    lower = line.lower()

    # Action items / todos
    if any(k in lower for k in [
        "action item", "todo", "to-do", "need to", "needs to",
        "should", "must", "follow up", "follow-up", "schedule",
        "don't forget", "remember to", "blocked by", "blocking",
    ]):
        return "action"

    # Decisions
    if any(k in lower for k in [
        "decision:", "decided", "chose", "choosing", "went with",
        "approach:", "strategy:", "agreed",
    ]):
        return "decision"

    # Meetings / people
    if any(k in lower for k in [
        "meeting with", "call with", "spoke with", "talked to",
        "discussed with", "demo", "sprint review", "standup",
        "workshop",
    ]):
        return "meeting"

    # Warnings / concerns
    if any(k in lower for k in [
        "warning", "concern", "risk", "careful", "watch out",
        "honest note", "tension", "struggling", "blocker",
        "not sexy", "drains", "urgent",
    ]):
        return "warning"

    # Wins / accomplishments
    if any(k in lower for k in [
        "loved it", "awesome", "badass", "nailed it", "proud",
        "shipped", "deployed", "fixed", "solved", "completed",
        "impressed", "shine",
    ]):
        return "win"

    return ""


HIGHLIGHT_COLORS = {
    "action": {"bg": "#E8F5E9", "border": "#4CAF50", "label": "ACTION"},
    "decision": {"bg": "#FFF3E0", "border": "#FF9800", "label": "DECISION"},
    "meeting": {"bg": "#E3F2FD", "border": "#2196F3", "label": "MEETING"},
    "warning": {"bg": "#FBE9E7", "border": "#F44336", "label": "ATTENTION"},
    "win": {"bg": "#F3E5F5", "border": "#9C27B0", "label": "WIN"},
}

CSS = """
@page {
    size: 1620px 2160px;
    margin: 80px 100px;
}

body {
    font-family: 'Georgia', 'Times New Roman', serif;
    font-size: 28px;
    line-height: 1.6;
    color: #1a1a1a;
    max-width: 1420px;
}

h1 {
    font-family: 'Helvetica Neue', 'Arial', sans-serif;
    font-size: 48px;
    font-weight: 700;
    color: #212121;
    border-bottom: 4px solid #333;
    padding-bottom: 16px;
    margin-top: 0;
    margin-bottom: 32px;
}

h2 {
    font-family: 'Helvetica Neue', 'Arial', sans-serif;
    font-size: 38px;
    font-weight: 600;
    color: #333;
    margin-top: 48px;
    margin-bottom: 16px;
    border-bottom: 2px solid #ccc;
    padding-bottom: 8px;
}

h3 {
    font-family: 'Helvetica Neue', 'Arial', sans-serif;
    font-size: 32px;
    font-weight: 600;
    color: #444;
    margin-top: 32px;
}

p {
    margin-bottom: 16px;
}

em {
    color: #666;
}

strong {
    color: #000;
}

ul, ol {
    padding-left: 40px;
}

li {
    margin-bottom: 8px;
}

hr {
    border: none;
    border-top: 2px solid #ddd;
    margin: 40px 0;
}

blockquote {
    border-left: 6px solid #ccc;
    margin-left: 0;
    padding: 12px 24px;
    background: #f9f9f9;
    color: #555;
}

code {
    font-family: 'SF Mono', 'Menlo', monospace;
    font-size: 24px;
    background: #f0f0f0;
    padding: 2px 8px;
    border-radius: 4px;
}

pre {
    background: #f5f5f5;
    padding: 20px;
    border-radius: 8px;
    overflow-x: auto;
    font-size: 22px;
    line-height: 1.4;
}

.highlight {
    padding: 12px 20px;
    margin: 16px 0;
    border-radius: 8px;
    border-left: 8px solid;
    position: relative;
}

.highlight-label {
    font-family: 'Helvetica Neue', sans-serif;
    font-size: 18px;
    font-weight: 700;
    letter-spacing: 1px;
    text-transform: uppercase;
    position: absolute;
    top: -10px;
    right: 16px;
    padding: 2px 10px;
    border-radius: 4px;
    color: white;
}

.highlight-action {
    background: #E8F5E9;
    border-color: #4CAF50;
}
.highlight-action .highlight-label {
    background: #4CAF50;
}

.highlight-decision {
    background: #FFF3E0;
    border-color: #FF9800;
}
.highlight-decision .highlight-label {
    background: #FF9800;
}

.highlight-meeting {
    background: #E3F2FD;
    border-color: #2196F3;
}
.highlight-meeting .highlight-label {
    background: #2196F3;
}

.highlight-warning {
    background: #FBE9E7;
    border-color: #F44336;
}
.highlight-warning .highlight-label {
    background: #F44336;
}

.highlight-win {
    background: #F3E5F5;
    border-color: #9C27B0;
}
.highlight-win .highlight-label {
    background: #9C27B0;
}

.legend {
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
    margin: 16px 0 32px 0;
    padding: 16px;
    background: #fafafa;
    border-radius: 8px;
}

.legend-item {
    display: flex;
    align-items: center;
    gap: 8px;
    font-family: 'Helvetica Neue', sans-serif;
    font-size: 20px;
}

.legend-dot {
    width: 16px;
    height: 16px;
    border-radius: 4px;
}
"""


def highlight_paragraphs(html: str) -> str:
    """Wrap paragraphs that match highlight patterns."""
    lines = html.split("\n")
    result = []

    for line in lines:
        # Only highlight <p> and <li> tags
        if line.strip().startswith(("<p>", "<li>")):
            # Strip HTML tags for classification
            text = re.sub(r"<[^>]+>", "", line)
            cls = classify_line(text)
            if cls:
                color = HIGHLIGHT_COLORS[cls]
                label = color["label"]
                wrapped = (
                    f'<div class="highlight highlight-{cls}">'
                    f'<span class="highlight-label">{label}</span>'
                    f"{line}</div>"
                )
                result.append(wrapped)
                continue
        result.append(line)

    return "\n".join(result)


def add_legend(html: str) -> str:
    """Add color legend after the first h1."""
    legend = '<div class="legend">'
    for cls, info in HIGHLIGHT_COLORS.items():
        legend += (
            f'<span class="legend-item">'
            f'<span class="legend-dot" style="background:{info["border"]}"></span>'
            f'{info["label"]}'
            f"</span>"
        )
    legend += "</div>"

    # Insert after first </h1>
    return html.replace("</h1>", f"</h1>\n{legend}", 1)


def md_to_pdf(input_path: str, output_path: str, title: str = None):
    """Convert markdown to highlighted PDF."""
    md_content = Path(input_path).read_text()

    # Convert markdown to HTML
    html_body = markdown.markdown(
        md_content,
        extensions=["tables", "fenced_code", "nl2br"],
    )

    # Apply highlights
    html_body = highlight_paragraphs(html_body)
    html_body = add_legend(html_body)

    # Build full HTML
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>{CSS}</style>
</head>
<body>
{html_body}
</body>
</html>"""

    # Save HTML for debugging
    html_path = output_path.replace(".pdf", ".html")
    Path(html_path).write_text(html)

    # Convert to PDF with weasyprint
    from weasyprint import HTML
    HTML(string=html).write_pdf(output_path)
    print(f"PDF: {output_path} ({Path(output_path).stat().st_size // 1024}KB)")


def main():
    parser = argparse.ArgumentParser(description="Convert journal markdown to highlighted PDF")
    parser.add_argument("input", help="Input markdown file")
    parser.add_argument("output", help="Output PDF file")
    parser.add_argument("--title", help="Custom title")
    args = parser.parse_args()

    md_to_pdf(args.input, args.output, args.title)


if __name__ == "__main__":
    main()
