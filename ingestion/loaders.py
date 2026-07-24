"""Phase 1 — Chargement du corpus AWS (PDF officiels + Markdown résiduel).

CHANGEMENT vs version initiale : les dépôts GitHub awsdocs ont été vidés de
leur contenu par Amazon (seuls les README subsistent). Le corpus provient
désormais des PDF officiels docs.aws.amazon.com, plus complets.

POURQUOI le découpage par groupe de pages : un PDF de 1500 pages chargé en un
seul document est ingérable. On garde les numéros de page en métadonnée — ce
qui permettra aux agents de citer précisément ("IAM User Guide, p. 412").

Usage :
    python ingestion/loaders.py          # stats du corpus
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import RAW_DIR

PDF_META = {
    "wellarchitected-framework":                     ("Well-Architected", "Architecture"),
    "wellarchitected-security-pillar":               ("Well-Architected", "Security"),
    "wellarchitected-reliability-pillar":            ("Well-Architected", "Reliability"),
    "wellarchitected-cost-optimization-pillar":      ("Well-Architected", "Cost"),
    "wellarchitected-performance-efficiency-pillar": ("Well-Architected", "Performance"),
    "wellarchitected-operational-excellence-pillar": ("Well-Architected", "Operations"),
    "vpc-ug":       ("VPC", "Networking"),
    "iam-ug":       ("IAM", "Security"),
    "s3-userguide": ("S3", "Storage"),
    "lambda-dg":    ("Lambda", "Compute"),
    "ec2-ug":       ("EC2", "Compute"),
    "rds-ug":       ("RDS", "Database"),
}

PAGES_PER_DOC = 6
MIN_CHARS = 400
MAX_CHARS = 60_000


@dataclass
class RawDocument:
    content: str
    source_file: str
    service: str
    category: str
    title: str
    doc_type: str


def _clean_pdf_text(text: str) -> str:
    """Nettoyage du bruit propre aux PDF AWS.

    Sans ce nettoyage, les embeddings sont pollués par les en-têtes répétés et
    le retrieval remonte des pages de sommaire au lieu du contenu technique.
    """
    text = re.sub(r"^[A-Z][A-Za-z0-9 ]{5,60}(User Guide|Developer Guide|"
                  r"Framework|Pillar)\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^.{3,80}\.{4,}\s*\d+\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d{1,4}\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _guess_meta(stem: str) -> tuple[str, str]:
    for key, (service, category) in PDF_META.items():
        if key in stem:
            return service, category
    return "AWS", "General"


def load_pdf_corpus(raw_dir: Path = RAW_DIR) -> list[RawDocument]:
    wp_dir = raw_dir / "whitepapers"
    if not wp_dir.exists():
        return []

    import fitz  # pymupdf

    docs: list[RawDocument] = []
    for pdf_path in sorted(wp_dir.glob("*.pdf")):
        service, category = _guess_meta(pdf_path.stem)
        doc_type = "whitepaper" if "wellarchitected" in pdf_path.stem else "user_guide"
        with fitz.open(pdf_path) as pdf:
            n_pages = len(pdf)
            for start in range(0, n_pages, PAGES_PER_DOC):
                end = min(start + PAGES_PER_DOC, n_pages)
                text = "\n".join(pdf[p].get_text() for p in range(start, end))
                text = _clean_pdf_text(text)
                if not (MIN_CHARS <= len(text) <= MAX_CHARS):
                    continue
                docs.append(RawDocument(
                    content=text,
                    source_file=f"whitepapers/{pdf_path.name}#p{start+1}-{end}",
                    service=service,
                    category=category,
                    title=f"{pdf_path.stem} (p. {start+1}-{end})",
                    doc_type=doc_type,
                ))
    return docs


def _clean_markdown(text: str) -> str:
    text = re.sub(r"\{[#:][^}]*\}", "", text)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"</?(?:div|span|a|img)[^>]*>", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def load_markdown_corpus(raw_dir: Path = RAW_DIR) -> list[RawDocument]:
    """Markdown résiduel — aws-lambda-developer-guide conserve du contenu utile."""
    skip = {"README.MD", "CONTRIBUTING.MD", "CODE_OF_CONDUCT.MD",
            "LICENSE.MD", "LICENSE-SUMMARY.MD", "LICENSE-SAMPLECODE.MD"}
    docs: list[RawDocument] = []
    for md in raw_dir.rglob("*.md"):
        if md.name.upper() in skip:
            continue
        text = _clean_markdown(md.read_text(encoding="utf-8", errors="ignore"))
        if not (MIN_CHARS <= len(text) <= MAX_CHARS):
            continue
        repo = md.relative_to(raw_dir).parts[0]
        service, category = _guess_meta(repo)
        if service == "AWS" and "lambda" in repo.lower():
            service, category = "Lambda", "Compute"
        m = re.search(r"^#\s+(.+)$", text, flags=re.MULTILINE)
        docs.append(RawDocument(
            content=text,
            source_file=str(md.relative_to(raw_dir)),
            service=service,
            category=category,
            title=m.group(1).strip() if m else md.stem,
            doc_type="user_guide",
        ))
    return docs


def load_corpus() -> list[RawDocument]:
    docs = load_pdf_corpus() + load_markdown_corpus()
    if not docs:
        raise RuntimeError(
            f"Aucun document dans {RAW_DIR}.\n"
            "Télécharge les PDF AWS dans data/raw/whitepapers/ (voir README)."
        )
    return docs


if __name__ == "__main__":
    from collections import Counter
    docs = load_corpus()
    total = sum(len(d.content) for d in docs)
    print(f"Documents chargés : {len(docs)}")
    print(f"Volume            : {total/1e6:.1f} M caractères")
    print(f"Taille moyenne    : {total//len(docs)} caractères\n")
    for svc, n in Counter(d.service for d in docs).most_common():
        print(f"  {svc:<18} {n:>5} docs")
    print("\nExemple de métadonnées :")
    print({k: v for k, v in asdict(docs[0]).items() if k != "content"})
    print("\nExtrait :")
    print(docs[len(docs)//2].content[:400])
