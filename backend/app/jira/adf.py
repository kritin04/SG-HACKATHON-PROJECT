"""Jira rich text (Atlassian Document Format, "ADF") <-> plain text.

Jira Cloud REST API v3 returns descriptions and comments as ADF: a JSON tree of nodes such as
{"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Hello"}]}]}.
"""
from __future__ import annotations


def adf_to_text(node) -> str:
    """Flatten ADF to readable text: paragraphs on new lines, list items as '- item'."""
    if node is None:
        return ""
    if isinstance(node, str):                      # Jira Server / API v2 returns plain text
        return node
    out: list[str] = []

    def walk(n, depth=0):
        t = n.get("type")
        if t == "text":
            out.append(n.get("text", ""))
        elif t == "hardBreak":
            out.append("\n")
        elif t in ("bulletList", "orderedList"):
            for i, item in enumerate(n.get("content", []), 1):
                out.append("\n" + ("  " * depth) + ("- " if t == "bulletList" else f"{i}. "))
                for c in item.get("content", []):
                    for cc in c.get("content", []) if c.get("type") == "paragraph" else [c]:
                        walk(cc, depth + 1)
            out.append("\n")
        else:
            for c in n.get("content", []) or []:
                walk(c, depth)
            if t in ("paragraph", "heading"):
                out.append("\n")

    walk(node)
    text = "".join(out)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    return text.strip()


def text_to_adf(text: str, bullets: list[str] | None = None, heading: str | None = None) -> dict:
    """Plain text (+ optional bullet list under a heading) -> ADF document."""
    content = [{"type": "paragraph", "content": [{"type": "text", "text": p}]} for p in text.split("\n\n") if p.strip()]
    if bullets:
        if heading:
            content.append({"type": "heading", "attrs": {"level": 3}, "content": [{"type": "text", "text": heading}]})
        content.append({"type": "bulletList", "content": [
            {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": b}]}]}
            for b in bullets]})
    return {"type": "doc", "version": 1, "content": content}
