"""Document-scoped, auditable tools shared by CLI and API VQA agents."""

import argparse
import json
import math
from pathlib import Path


class DocumentTools:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.document = json.loads((self.root / "document.json").read_text())
        self.pages = json.loads((self.root / "page_text.json").read_text())
        self.text_pages_read = set()
        self.image_pages_read = set()
        self.searches = []
        self.calculations = []

    def overview(self):
        return {
            "document_id": self.document["id"],
            "title": self.document["title"],
            "page_count": len(self.pages),
            "content_page_count": self.document.get("content_page_count"),
            "sha256": self.document["sha256"],
            "page_indexing": "zero-based PDF indices",
            "pages": [
                {"page": p["page"], "characters": len(p["text"]), "preview": p["text"][:350]} for p in self.pages
            ],
        }

    def search(self, terms, max_hits=30):
        if (
            not isinstance(terms, list)
            or not 1 <= len(terms) <= 12
            or any(not isinstance(t, str) or not 1 <= len(t) <= 200 for t in terms)
        ):
            raise ValueError("Provide 1–12 non-empty literal search terms, each at most 200 characters")
        max_hits = min(50, max(1, int(max_hits)))
        hits = []
        for p in self.pages:
            lowered = p["text"].casefold()
            for term in terms:
                start = 0
                while (pos := lowered.find(term.casefold(), start)) >= 0:
                    hits.append(
                        {
                            "page": p["page"],
                            "term": term,
                            "offset": pos,
                            "context": p["text"][max(0, pos - 150) : pos + len(term) + 250],
                        }
                    )
                    start = pos + max(1, len(term))
        self.searches.append({"terms": terms, "match_count": len(hits)})
        return {
            "scanned_text_pages": list(range(len(self.pages))),
            "match_count": len(hits),
            "hits": hits[:max_hits],
            "truncated_results": len(hits) > max_hits,
            "note": "A zero literal-match count does not prove semantic or visual absence.",
        }

    def read(self, pages, images=True):
        if (
            not isinstance(pages, list)
            or not 1 <= len(pages) <= 8
            or any(type(p) is not int or not 0 <= p < len(self.pages) for p in pages)
        ):
            raise ValueError("Read 1–8 valid zero-based page indices per call")
        result = []
        for index in dict.fromkeys(pages):
            page = self.pages[index]
            item = {"page": index, "text": page["text"], "text_complete": True}
            self.text_pages_read.add(index)
            if images:
                item["image_path"] = str(self.root / "pages" / f"page{index:03d}.png")
                self.image_pages_read.add(index)
            result.append(item)
        return {
            "document_id": self.document["id"],
            "pages": result,
            "note": "Image paths must actually be opened by the CLI; the API driver delivers requested images.",
        }

    def calculate(self, operator, operands):
        if (
            not isinstance(operands, list)
            or not 1 <= len(operands) <= 100
            or any(type(x) not in (int, float) or not math.isfinite(x) or abs(x) > 1e15 for x in operands)
        ):
            raise ValueError("Provide at most 100 finite numeric operands")
        if operator == "+":
            result = sum(operands)
        elif operator == "-" and len(operands) == 2:
            result = operands[0] - operands[1]
        elif operator == "*":
            result = math.prod(operands)
        elif operator == "/" and len(operands) == 2:
            result = operands[0] / operands[1]
        elif operator == "min":
            result = min(operands)
        elif operator == "max":
            result = max(operands)
        else:
            raise ValueError("Supported operators: +, -, *, /, min, max; subtraction/division need two operands")
        if not math.isfinite(result):
            raise ValueError("Non-finite result")
        record = {"operator": operator, "operands": operands, "result": result}
        self.calculations.append(record)
        return record

    def call(self, name, arguments):
        if name == "document_overview":
            return self.overview()
        if name == "search_document":
            return self.search(**arguments)
        if name == "read_pages":
            return self.read(**arguments)
        if name == "calculate":
            return self.calculate(**arguments)
        raise ValueError("Unknown document tool")


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "document_overview",
            "description": "Get full-document page count, identity, source hash and page previews.",
            "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_document",
            "description": "Search every page's extracted text for literal terms, including synonyms in separate terms. This does not prove visual absence.",
            "parameters": {
                "type": "object",
                "properties": {
                    "terms": {"type": "array", "items": {"type": "string"}},
                    "max_hits": {"type": "integer"},
                },
                "required": ["terms"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_pages",
            "description": "Read full text and request actual page images for up to eight zero-based PDF pages; use the images for tables and figures.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pages": {"type": "array", "items": {"type": "integer"}},
                    "images": {"type": "boolean"},
                },
                "required": ["pages"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Execute arithmetic on observed numeric operands. Establish operand provenance from document pages first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "operator": {"type": "string", "enum": ["+", "-", "*", "/", "min", "max"]},
                    "operands": {"type": "array", "items": {"type": "number"}},
                },
                "required": ["operator", "operands"],
                "additionalProperties": False,
            },
        },
    },
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("tool", choices=["document_overview", "search_document", "read_pages", "calculate"])
    parser.add_argument("arguments", nargs="?", default="{}", help="Tool arguments as JSON")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        result = DocumentTools(args.root).call(args.tool, json.loads(args.arguments))
    except Exception as exc:
        result = {"error": type(exc).__name__, "message": str(exc)}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
