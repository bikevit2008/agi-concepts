"""Deterministic local context providers."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Sequence

from src.contracts.context import ContextAnswer, ContextDocument


@dataclass
class StaticContextProvider:
    """In-memory provider useful for tests, fixtures, and curated notes."""

    provider_id: str = "static"
    documents: List[ContextDocument] = field(default_factory=list)

    def query(self, query: str, limit: int = 5) -> ContextAnswer:
        return ContextAnswer(
            query=str(query or ""),
            documents=_rank_documents(self.documents, query=query, limit=limit),
        )


@dataclass
class LocalFileContextProvider:
    """Read-only provider over a bounded set of local text files."""

    root_path: str
    provider_id: str = "local_files"
    allowed_suffixes: Sequence[str] = (".md", ".txt", ".yaml", ".yml")
    max_file_chars: int = 4000

    def query(self, query: str, limit: int = 5) -> ContextAnswer:
        root = Path(self.root_path)
        if not root.exists():
            return ContextAnswer(query=str(query or ""), documents=[])
        documents = list(self._load_documents(root))
        return ContextAnswer(
            query=str(query or ""),
            documents=_rank_documents(documents, query=query, limit=limit),
        )

    def _load_documents(self, root: Path) -> Iterable[ContextDocument]:
        suffixes = {suffix.lower() for suffix in self.allowed_suffixes}
        files = [root] if root.is_file() else sorted(root.rglob("*"))
        for path in files:
            if not path.is_file() or path.suffix.lower() not in suffixes:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            rel = str(path.relative_to(root)) if root.is_dir() else path.name
            yield ContextDocument(
                id=_stable_id(str(path)),
                name=path.name,
                uri=str(path),
                text=text[: self.max_file_chars],
                metadata={"relative_path": rel, "provider": self.provider_id},
            )


def build_local_context_providers(
    root_paths: Sequence[str],
    project_root: str | Path | None = None,
    allowed_suffixes: Sequence[str] = (".md", ".txt", ".yaml", ".yml"),
    max_file_chars: int = 4000,
) -> List[LocalFileContextProvider]:
    """Build local providers from config paths without touching missing roots."""
    base = Path(project_root) if project_root is not None else Path.cwd()
    providers: List[LocalFileContextProvider] = []
    for idx, raw_path in enumerate(root_paths):
        if not str(raw_path).strip():
            continue
        path = Path(str(raw_path))
        if not path.is_absolute():
            path = base / path
        providers.append(
            LocalFileContextProvider(
                root_path=str(path),
                provider_id=f"local_files:{idx}:{path.name or 'root'}",
                allowed_suffixes=tuple(allowed_suffixes),
                max_file_chars=max_file_chars,
            )
        )
    return providers


def _rank_documents(
    documents: Sequence[ContextDocument],
    query: str,
    limit: int,
) -> List[ContextDocument]:
    limit_n = max(0, int(limit or 0))
    if limit_n == 0:
        return []
    query_tokens = _tokens(query)
    ranked = []
    for document in documents:
        document_tokens = _tokens(f"{document.name} {document.text}")
        score = (
            len(query_tokens & document_tokens) / max(1, len(query_tokens))
            if query_tokens
            else 0.0
        )
        ranked.append((score, document))
    ranked.sort(key=lambda item: (item[0], item[1].name), reverse=True)
    return [
        ContextDocument(
            id=document.id,
            name=document.name,
            uri=document.uri,
            text=document.text,
            metadata=dict(document.metadata),
            score=round(score, 4),
        )
        for score, document in ranked[:limit_n]
        if score > 0.0 or not query_tokens
    ]


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[\w\-]+", str(text).lower())
        if len(token) >= 3
    }


def _stable_id(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


__all__ = [
    "LocalFileContextProvider",
    "StaticContextProvider",
    "build_local_context_providers",
]
