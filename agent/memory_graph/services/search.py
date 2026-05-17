"""Search Indexer — FTS search across memory content.

Provides search document management and query functionality.
Search documents are derived from active memories + their path entries.
"""

from typing import Optional, Dict, Any, List
import logging

from sqlalchemy import select, delete, text, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import Memory, Edge, Path, SearchDocument, GlossaryKeyword, Node
from ..db import get_session
from .search_terms import SearchTokenizer, expand_query_terms, build_document_search_terms

logger = logging.getLogger(__name__)


def _build_search_terms(content: str, keywords: List[str] = None, path: str = "", uri: str = "", disclosure: str = None) -> str:
    """Build search terms from content + glossary keywords with CJK segmentation."""
    glossary_text = " ".join(keywords) if keywords else ""
    return build_document_search_terms(
        path=path or "",
        uri=uri or "",
        content=content,
        disclosure=disclosure,
        glossary_text=glossary_text,
    )


def _format_snippet(content: str, query: str, context_chars: int = 80) -> str:
    """Extract a snippet around the first match of query in content."""
    if not content:
        return ""
    content_lower = content.lower()
    query_lower = query.lower()
    pos = content_lower.find(query_lower)
    if pos < 0:
        for token in query_lower.split():
            pos = content_lower.find(token)
            if pos >= 0:
                break
    if pos < 0:
        return content[:context_chars * 2] + ("..." if len(content) > context_chars * 2 else "")

    start = max(0, pos - context_chars)
    end = min(len(content), pos + len(query) + context_chars)
    snippet = content[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(content):
        snippet = snippet + "..."
    return snippet


class SearchIndexer:
    """Manages search document lifecycle and query execution."""

    def __init__(self, session_factory=None):
        self._session_factory = session_factory or get_session

    async def refresh_search_documents_for_node(self, node_uuid: str,
                                                  namespace: str = "") -> int:
        """Rebuild search documents for a node's active memory across all its paths."""
        async with self._session_factory() as session:
            # Get active memory
            mem_result = await session.execute(
                select(Memory).where(Memory.node_uuid == node_uuid, Memory.deprecated == False)
                .order_by(Memory.created_at.desc())
            )
            memory = mem_result.scalars().first()
            if not memory:
                # No active memory — delete search docs
                await session.execute(
                    delete(SearchDocument).where(SearchDocument.node_uuid == node_uuid)
                )
                await session.commit()
                return 0

            # Get glossary keywords
            kw_result = await session.execute(
                select(GlossaryKeyword.keyword).where(GlossaryKeyword.node_uuid == node_uuid)
            )
            keywords = [r[0] for r in kw_result.all()]

            # Delete existing search docs for this node
            await session.execute(
                delete(SearchDocument).where(SearchDocument.node_uuid == node_uuid)
            )

            # Get all paths for this node
            path_stmt = select(Path).where(Path.node_uuid == node_uuid)
            if namespace:
                path_stmt = path_stmt.where(Path.namespace == namespace)
            path_result = await session.execute(path_stmt)

            count = 0
            for path_obj in path_result.scalars().all():
                uri = f"{path_obj.domain}://{path_obj.path}"

                # Get disclosure from edge
                disclosure = None
                if path_obj.edge_id:
                    edge_result = await session.execute(
                        select(Edge.disclosure).where(Edge.id == path_obj.edge_id)
                    )
                    edge_row = edge_result.first()
                    if edge_row:
                        disclosure = edge_row[0]

                search_terms = _build_search_terms(
                    memory.content, keywords,
                    path=path_obj.path, uri=uri, disclosure=disclosure,
                )

                doc = SearchDocument(
                    node_uuid=node_uuid,
                    namespace=path_obj.namespace,
                    domain=path_obj.domain,
                    path=path_obj.path,
                    uri=uri,
                    content=memory.content,
                    search_terms=search_terms,
                    memory_id=memory.id,
                    disclosure=disclosure,
                    priority=0,
                )
                session.add(doc)
                count += 1

            await session.commit()
            return count

    async def search(self, query: str, domain: Optional[str] = None,
                      namespace: Optional[str] = None,
                      limit: int = 20) -> List[Dict[str, Any]]:
        """Search across all search documents."""
        if not query or not query.strip():
            return []

        async with self._session_factory() as session:
            # Use CJK-aware tokenization for query
            tokens = SearchTokenizer.tokenize(query.strip())
            if not tokens:
                return []

            conditions = []
            for token in tokens:
                conditions.append(SearchDocument.search_terms.ilike(f"%{token}%"))

            if not conditions:
                return []

            stmt = select(SearchDocument).where(and_(*conditions))
            if domain:
                stmt = stmt.where(SearchDocument.domain == domain)
            if namespace is not None:
                stmt = stmt = stmt.where(SearchDocument.namespace == namespace)
            stmt = stmt.order_by(SearchDocument.priority.desc()).limit(limit)

            result = await session.execute(stmt)
            docs = result.scalars().all()

            return [
                {
                    "node_uuid": doc.node_uuid,
                    "domain": doc.domain,
                    "path": doc.path,
                    "uri": doc.uri or f"{doc.domain}://{doc.path}",
                    "snippet": _format_snippet(doc.content, query),
                    "content_length": len(doc.content) if doc.content else 0,
                }
                for doc in docs
            ]

    async def get_node_uuids_for_prefix(self, domain: str, path_prefix: str,
                                          namespace: str = "") -> List[str]:
        """Get all node UUIDs whose path starts with a prefix."""
        async with self._session_factory() as session:
            stmt = select(Path.node_uuid).where(
                Path.domain == domain, Path.path.like(f"{escape_like_literal(path_prefix)}%")
            )
            if namespace:
                stmt = stmt.where(Path.namespace == namespace)
            result = await session.execute(stmt)
            return [r[0] for r in result.all()]
