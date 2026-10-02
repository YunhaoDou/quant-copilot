"""Compliance Q&A over a small corpus of internal reference docs (data/compliance/*.md —
plain-language summaries of well-known public FINRA/SEC rules: PDT, Reg T margin, options
approval tiers, suitability). Retrieval is a from-scratch TF-IDF cosine search — no vector
DB, no embeddings API, no new dependency — grounded strictly in the retrieved excerpts: if
nothing in the corpus is relevant enough, the question is answered "not covered" WITHOUT
calling the LLM, so the model is never given a chance to invent an answer from nothing.
"""
import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError
from redis.asyncio import Redis

from app.config import settings
from app.schemas.compliance import ComplianceAnswerSchema
from app.services.i18n import DEFAULT_LANG, language_instruction
from app.services.llm_research import LLMClient

NOT_COVERED_MESSAGE = {
    "en": "This isn't covered by the compliance corpus on file. Escalate to a compliance officer.",
    "zh": "合规知识库中未收录此问题,请上报给合规专员处理。",
}

CORPUS_DIR = Path(__file__).resolve().parent.parent / "data" / "compliance"
TOP_K = 3
MIN_SIMILARITY = 0.10
MAX_RETRIES = 2
TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = frozenset(
    "a an the is are was were be been being to of in on for and or if than then "
    "this that these those it its as at by with from not no can may will would "
    "should could do does did have has had i you he she they we what which who "
    "when where why how".split()
)

SYSTEM_PROMPT = (
    "You are a compliance reference assistant. You are given one or more excerpts from an "
    "internal compliance corpus, each tagged with its source document id. Answer the "
    "question using ONLY information found in the excerpts — never use outside knowledge, "
    "never speculate. Write a complete, self-contained answer of at least one full sentence "
    "that actually explains the relevant rule in your own words — never just restate a "
    "heading or excerpt title verbatim. If the excerpts don't fully answer the question, "
    "say so explicitly in the answer. Respond with ONLY a JSON object: "
    '{"answer": str, "citations": [source_doc_id, ...]}. citations must list every source '
    "doc id you actually drew on, using exactly the ids given. No prose outside the JSON."
)


@dataclass
class Chunk:
    doc_id: str
    heading: str
    text: str
    term_freq: Counter


def _tokenize(text: str) -> list[str]:
    return [t for t in TOKEN_RE.findall(text.lower()) if len(t) > 1 and t not in STOPWORDS]


def _load_corpus() -> list[Chunk]:
    """One chunk per whole document, not per heading. A tiny 4-doc corpus with short user
    questions needs every doc's full vocabulary (its intro framing plus every subsection)
    available for matching — splitting by "## " section starved each fragment of the
    shared context words (e.g. a query naming "naked calls" but not "uncovered" only
    matches the "Level 4" subsection's exact wording, missing the doc's own intro that
    would otherwise pull it in). Citations are already doc-level, so nothing is lost."""
    chunks: list[Chunk] = []
    for path in sorted(CORPUS_DIR.glob("*.md")):
        raw = path.read_text()
        lines = raw.splitlines()
        title = lines[0].lstrip("#").strip() if lines and lines[0].startswith("#") else path.stem
        body = "\n".join(lines[1:]).strip()
        chunks.append(Chunk(doc_id=path.name, heading=title, text=body, term_freq=Counter(_tokenize(body))))
    return chunks


_CHUNKS = _load_corpus()
_DOC_FREQ = Counter()
for _c in _CHUNKS:
    _DOC_FREQ.update(set(_c.term_freq))
_N_DOCS = len(_CHUNKS)


def _idf(term: str) -> float:
    return math.log((_N_DOCS + 1) / (_DOC_FREQ.get(term, 0) + 1)) + 1.0


def _vector(term_freq: Counter) -> dict[str, float]:
    vec = {term: freq * _idf(term) for term, freq in term_freq.items()}
    norm = math.sqrt(sum(w * w for w in vec.values())) or 1.0
    return {term: w / norm for term, w in vec.items()}


_CHUNK_VECTORS = [_vector(c.term_freq) for c in _CHUNKS]


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    shared = set(a) & set(b)
    return sum(a[t] * b[t] for t in shared)


def retrieve(question: str, top_k: int = TOP_K) -> list[dict]:
    """Pure function: question -> ranked list of {doc_id, heading, text, score} above the
    minimum-similarity bar. Empty list means the corpus has nothing relevant."""
    query_vec = _vector(Counter(_tokenize(question)))
    scored = [
        {"doc_id": c.doc_id, "heading": c.heading, "text": c.text, "score": _cosine(query_vec, cv)}
        for c, cv in zip(_CHUNKS, _CHUNK_VECTORS)
    ]
    scored.sort(key=lambda s: s["score"], reverse=True)
    return [s for s in scored[:top_k] if s["score"] >= MIN_SIMILARITY]


def _build_prompt(question: str, hits: list[dict]) -> str:
    excerpts = "\n\n".join(f"[{h['doc_id']}] {h['heading']}\n{h['text']}" for h in hits)
    return f"Excerpts:\n{excerpts}\n\nQuestion: {question}\n\nAnswer now."


def _cache_key(question: str, lang: str) -> str:
    digest = hashlib.sha256(question.strip().lower().encode()).hexdigest()
    return f"compliance_qa:{digest}:{lang}"


async def answer_question(
    redis: Redis, question: str, client: LLMClient | None = None, lang: str = DEFAULT_LANG
) -> dict:
    cached = await redis.get(_cache_key(question, lang))
    if cached:
        payload = json.loads(cached)
        payload["cache_hit"] = True
        return payload

    hits = retrieve(question)
    if not hits:
        return {
            "question": question,
            "answer": NOT_COVERED_MESSAGE.get(lang, NOT_COVERED_MESSAGE[DEFAULT_LANG]),
            "citations": [],
            "grounded": False,
            "cache_hit": False,
        }

    client = client or LLMClient()
    system_prompt = SYSTEM_PROMPT + language_instruction(lang)
    known_doc_ids = {h["doc_id"] for h in hits}
    prompt = _build_prompt(question, hits)
    last_error: Exception | None = None

    for _attempt in range(MAX_RETRIES + 1):
        text, _in_tok, _out_tok = client.complete(prompt, system_prompt=system_prompt)
        try:
            data = json.loads(text)
            validated = ComplianceAnswerSchema.model_validate(data)
            bogus = set(validated.citations) - known_doc_ids
            if bogus:
                raise ValueError(f"cited unknown source doc id(s): {sorted(bogus)}")
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_error = exc
            prompt = _build_prompt(question, hits) + (
                f"\n\nYour previous response was invalid: {exc}\n"
                f"citations must be a subset of {sorted(known_doc_ids)}. Return ONLY the corrected JSON object."
            )
            continue

        payload = {
            "question": question,
            "answer": validated.answer,
            "citations": validated.citations,
            "grounded": True,
            "cache_hit": False,
        }
        await redis.set(_cache_key(question, lang), json.dumps(payload), ex=settings.LLM_CACHE_TTL_HOURS * 3600)
        return payload

    raise ValueError(f"LLM failed to produce a grounded, schema-valid answer after {MAX_RETRIES} retries: {last_error}")
