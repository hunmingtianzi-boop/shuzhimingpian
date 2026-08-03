# ruff: noqa: S608 -- every interpolated identifier is whitelist-validated below.
"""Tenant-safe PostgreSQL hybrid retrieval with trigram/vector RRF fusion."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, fields
from typing import Any, Mapping, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import TextClause

from .errors import AIRetrievalError
from .protocols import AsyncSqlExecutor
from .schemas import RetrievalQuery, RetrievedEvidence

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_QUALIFIED_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?$")


@dataclass(frozen=True, slots=True)
class KnowledgeSqlSchema:
    """Explicit, validated identifiers for integration with the DB model layer."""

    documents_table: str = "knowledge_documents"
    versions_table: str = "knowledge_versions"
    chunks_table: str = "knowledge_chunks"
    document_id: str = "id"
    document_tenant_id: str = "tenant_id"
    document_company_id: str = "company_id"
    document_current_version_id: str = "current_version_id"
    document_status: str = "status"
    document_source_type: str = "source_type"
    document_source_id: str = "source_id"
    version_id: str = "id"
    version_tenant_id: str = "tenant_id"
    version_company_id: str = "company_id"
    version_document_id: str = "document_id"
    version_review_status: str = "review_status"
    chunk_id: str = "id"
    chunk_tenant_id: str = "tenant_id"
    chunk_company_id: str = "company_id"
    chunk_document_id: str = "document_id"
    chunk_version_id: str = "version_id"
    chunk_ordinal: str = "ordinal"
    chunk_title: str = "title"
    chunk_text: str = "text"
    chunk_embedding: str = "embedding"
    chunk_embedding_model: str = "embedding_model"
    chunk_visibility: str = "visibility"
    chunk_metadata: str = "metadata"
    chunk_content_hash: str = "content_hash"
    chunk_search_tsv: str = "search_tsv"
    chunk_is_active: str | None = None
    text_search_config: str = "simple"

    def __post_init__(self) -> None:
        table_fields = {"documents_table", "versions_table", "chunks_table"}
        for schema_field in fields(self):
            raw_value = getattr(self, schema_field.name)
            if raw_value is None and schema_field.name == "chunk_is_active":
                continue
            value = str(raw_value)
            pattern = _QUALIFIED_IDENTIFIER if schema_field.name in table_fields else _IDENTIFIER
            if not pattern.fullmatch(value):
                raise ValueError(f"unsafe SQL identifier: {schema_field.name}")


@dataclass(frozen=True, slots=True)
class HybridRetrievalConfig:
    schema: KnowledgeSqlSchema = KnowledgeSqlSchema()
    expected_embedding_dimensions: int | None = 1024
    max_top_k: int = 50
    max_candidate_limit: int = 500
    max_query_chars: int = 4000
    published_review_status: str = "approved"
    public_visibility: str = "public"
    active_document_status: str = "published"
    embedding_model: str | None = None

    def __post_init__(self) -> None:
        if (
            self.expected_embedding_dimensions is not None
            and self.expected_embedding_dimensions <= 0
        ):
            raise ValueError("expected_embedding_dimensions must be positive")
        if self.max_top_k <= 0 or self.max_candidate_limit < self.max_top_k:
            raise ValueError("invalid retrieval limits")
        if self.max_query_chars <= 0:
            raise ValueError("max_query_chars must be positive")
        if self.embedding_model is not None and not self.embedding_model.strip():
            raise ValueError("embedding_model must not be blank")


class SQLAlchemySessionExecutor:
    """Adapter around an externally managed SQLAlchemy AsyncSession."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def fetch_mappings(
        self,
        statement: TextClause,
        parameters: Mapping[str, Any],
    ) -> Sequence[Mapping[str, Any]]:
        result = await self._session.execute(statement, dict(parameters))
        return [dict(row) for row in result.mappings().all()]


class PostgresHybridRetrievalRepository:
    """Run hybrid or lexical-only retrieval over already-published chunks.

    Tenant, company, current-version, review-status and public-visibility
    predicates live in the SQL itself.  Callers cannot accidentally retrieve a
    broad candidate set and filter it later in Python.
    """

    def __init__(
        self,
        executor: AsyncSqlExecutor,
        *,
        config: HybridRetrievalConfig | None = None,
    ) -> None:
        self._executor = executor
        self.config = config or HybridRetrievalConfig()
        self._hybrid_statement = text(_build_hybrid_sql(self.config.schema))
        self._lexical_statement = text(_build_lexical_sql(self.config.schema))
        self._faq_statement = text(_build_faq_match_sql(self.config.schema))

    async def search(self, query: RetrievalQuery) -> Sequence[RetrievedEvidence]:
        self._validate_query(query)
        parameters: dict[str, Any] = {
            "tenant_id": query.tenant_id,
            "company_id": query.company_id,
            "card_id": query.card_id,
            "query_text": query.text,
            "top_k": query.top_k,
            "candidate_limit": query.candidate_limit,
            "trigram_threshold": query.trigram_threshold,
            "rrf_k": query.rrf_k,
            "vector_weight": query.vector_weight,
            "lexical_weight": query.lexical_weight,
            "published_review_status": self.config.published_review_status,
            "public_visibility": self.config.public_visibility,
            "active_document_status": self.config.active_document_status,
            "embedding_model": self.config.embedding_model,
        }
        statement = self._lexical_statement
        if query.embedding is not None:
            parameters["query_embedding"] = _vector_literal(query.embedding)
            statement = self._hybrid_statement

        try:
            rows = await self._executor.fetch_mappings(statement, parameters)
            return tuple(_row_to_evidence(row) for row in rows)
        except AIRetrievalError:
            raise
        except Exception as exc:
            raise AIRetrievalError() from exc

    async def find_faq_match(
        self,
        query: RetrievalQuery,
        *,
        similarity_threshold: float,
    ) -> RetrievedEvidence | None:
        """Return one high-confidence FAQ title/alias match before model calls."""

        self._validate_query(query)
        if not 0 <= similarity_threshold <= 1:
            raise ValueError("similarity_threshold must be between 0 and 1")
        parameters: dict[str, Any] = {
            "tenant_id": query.tenant_id,
            "company_id": query.company_id,
            "card_id": query.card_id,
            "query_text": query.text,
            "faq_similarity_threshold": similarity_threshold,
            "published_review_status": self.config.published_review_status,
            "public_visibility": self.config.public_visibility,
            "active_document_status": self.config.active_document_status,
        }
        try:
            rows = await self._executor.fetch_mappings(self._faq_statement, parameters)
            if not rows:
                return None
            return _row_to_evidence(rows[0])
        except AIRetrievalError:
            raise
        except Exception as exc:
            raise AIRetrievalError() from exc

    def _validate_query(self, query: RetrievalQuery) -> None:
        if not query.tenant_id.strip() or not query.company_id.strip():
            raise ValueError("tenant_id and company_id are required")
        if not query.text.strip() or len(query.text) > self.config.max_query_chars:
            raise ValueError("retrieval query text is empty or too long")
        if not 1 <= query.top_k <= self.config.max_top_k:
            raise ValueError("top_k is outside the configured range")
        if not query.top_k <= query.candidate_limit <= self.config.max_candidate_limit:
            raise ValueError("candidate_limit is outside the configured range")
        if not 0 <= query.trigram_threshold <= 1:
            raise ValueError("trigram_threshold must be between 0 and 1")
        if query.rrf_k <= 0:
            raise ValueError("rrf_k must be positive")
        if query.vector_weight < 0 or query.lexical_weight < 0:
            raise ValueError("retrieval weights must not be negative")
        if query.vector_weight == 0 and query.lexical_weight == 0:
            raise ValueError("at least one retrieval weight must be positive")
        if query.embedding is not None:
            expected = self.config.expected_embedding_dimensions
            if expected is not None and len(query.embedding) != expected:
                raise ValueError("query embedding dimension mismatch")
            if not query.embedding or any(not math.isfinite(value) for value in query.embedding):
                raise ValueError("query embedding contains invalid values")


def _eligible_cte(schema: KnowledgeSqlSchema) -> str:
    active_chunk_predicate = (
        f"\n      AND c.{schema.chunk_is_active} IS TRUE" if schema.chunk_is_active else ""
    )
    return f"""
eligible AS (
    SELECT
        c.{schema.chunk_id}::text AS evidence_id,
        c.{schema.chunk_document_id}::text AS document_id,
        c.{schema.chunk_version_id}::text AS version_id,
        c.{schema.chunk_ordinal} AS ordinal,
        COALESCE(c.{schema.chunk_title}, '') AS title,
        c.{schema.chunk_text} AS evidence_text,
        d.{schema.document_source_type} AS source_type,
        c.{schema.chunk_embedding} AS embedding,
        c.{schema.chunk_embedding_model} AS embedding_model,
        c.{schema.chunk_metadata} AS metadata,
        c.{schema.chunk_content_hash} AS content_hash,
        c.{schema.chunk_search_tsv} AS search_tsv
    FROM {schema.chunks_table} AS c
    JOIN {schema.documents_table} AS d
      ON d.{schema.document_id} = c.{schema.chunk_document_id}
    JOIN {schema.versions_table} AS v
      ON v.{schema.version_id} = c.{schema.chunk_version_id}
     AND v.{schema.version_document_id} = d.{schema.document_id}
     AND v.{schema.version_tenant_id} = CAST(:tenant_id AS uuid)
     AND v.{schema.version_company_id} = CAST(:company_id AS uuid)
    WHERE d.{schema.document_tenant_id} = CAST(:tenant_id AS uuid)
      AND d.{schema.document_company_id} = CAST(:company_id AS uuid)
      AND c.{schema.chunk_tenant_id} = CAST(:tenant_id AS uuid)
      AND c.{schema.chunk_company_id} = CAST(:company_id AS uuid)
      AND d.{schema.document_current_version_id} = c.{schema.chunk_version_id}
      AND d.{schema.document_status} = :active_document_status
      AND v.{schema.version_review_status} = :published_review_status
      AND c.{schema.chunk_visibility} = :public_visibility
    AND (
        d.{schema.document_source_type} NOT IN ('product', 'case_study')
        OR (
          d.{schema.document_source_type} = 'product'
          AND EXISTS (
            SELECT 1 FROM products AS product
            WHERE product.id::text = d.{schema.document_source_id}
              AND product.tenant_id = CAST(:tenant_id AS uuid)
              AND product.company_id = CAST(:company_id AS uuid)
              AND product.status = 'published'
              AND product.visibility = 'public'
              AND product.deleted_at IS NULL
          )
        )
        OR (
          d.{schema.document_source_type} = 'case_study'
          AND EXISTS (
            SELECT 1 FROM case_studies AS case_study
            WHERE case_study.id::text = d.{schema.document_source_id}
              AND case_study.tenant_id = CAST(:tenant_id AS uuid)
              AND case_study.company_id = CAST(:company_id AS uuid)
              AND case_study.status = 'published'
              AND case_study.visibility = 'public'
              AND case_study.deleted_at IS NULL
          )
        )
      ){active_chunk_predicate}
      AND (
        CAST(:card_id AS uuid) IS NULL
        OR (
          NOT EXISTS (
            SELECT 1
            FROM enterprise_content_distributions AS distribution
            WHERE distribution.tenant_id = CAST(:tenant_id AS uuid)
              AND distribution.company_id = CAST(:company_id AS uuid)
              AND distribution.resource_type = CASE
                WHEN d.{schema.document_source_type} IN ('product', 'case_study')
                  THEN d.{schema.document_source_type}
                ELSE 'knowledge_document'
              END
              AND distribution.resource_id::text = CASE
                WHEN d.{schema.document_source_type} IN ('product', 'case_study')
                  THEN d.{schema.document_source_id}
                ELSE d.{schema.document_id}::text
              END
              AND distribution.is_default_visible IS FALSE
          )
          AND NOT EXISTS (
            SELECT 1
            FROM card_content_overrides AS override
            WHERE override.tenant_id = CAST(:tenant_id AS uuid)
              AND override.company_id = CAST(:company_id AS uuid)
              AND override.card_id = CAST(:card_id AS uuid)
              AND override.resource_type = CASE
                WHEN d.{schema.document_source_type} IN ('product', 'case_study')
                  THEN d.{schema.document_source_type}
                ELSE 'knowledge_document'
              END
              AND override.resource_id::text = CASE
                WHEN d.{schema.document_source_type} IN ('product', 'case_study')
                  THEN d.{schema.document_source_id}
                ELSE d.{schema.document_id}::text
              END
              AND override.mode = 'hidden'
          )
        )
      )
)
""".strip()


def _build_hybrid_sql(schema: KnowledgeSqlSchema) -> str:
    eligible = _eligible_cte(schema)
    metadata_score = _metadata_hint_score_sql("e")
    metadata_match = _metadata_hint_match_sql("e")
    return f"""
WITH {eligible},
vector_candidates AS (
    SELECT
        e.*,
        e.embedding <=> CAST(:query_embedding AS vector) AS vector_distance,
        1.0 - (e.embedding <=> CAST(:query_embedding AS vector)) AS vector_score
    FROM eligible AS e
    WHERE e.embedding IS NOT NULL
      AND (
        CAST(:embedding_model AS text) IS NULL
        OR e.embedding_model = CAST(:embedding_model AS text)
      )
    ORDER BY e.embedding <=> CAST(:query_embedding AS vector), e.evidence_id
    LIMIT :candidate_limit
),
vector_ranked AS (
    SELECT
        vc.*,
        ROW_NUMBER() OVER (ORDER BY vc.vector_distance, vc.evidence_id) AS vector_rank
    FROM vector_candidates AS vc
),
lexical_candidates AS (
    SELECT
        e.*,
        GREATEST(
            COALESCE(
                ts_rank_cd(
                    e.search_tsv,
                    websearch_to_tsquery('{schema.text_search_config}', :query_text)
                ),
                0.0
            ),
            similarity(e.evidence_text, :query_text),
            similarity(e.title, :query_text),
            {metadata_score}
        ) AS lexical_score
    FROM eligible AS e
    WHERE e.search_tsv @@ websearch_to_tsquery(
              '{schema.text_search_config}', :query_text
          )
       OR similarity(e.evidence_text, :query_text) >= :trigram_threshold
       OR similarity(e.title, :query_text) >= :trigram_threshold
       OR {metadata_match}
    ORDER BY lexical_score DESC, e.evidence_id
    LIMIT :candidate_limit
),
lexical_ranked AS (
    SELECT
        lc.*,
        ROW_NUMBER() OVER (ORDER BY lc.lexical_score DESC, lc.evidence_id) AS lexical_rank
    FROM lexical_candidates AS lc
),
fused AS (
    SELECT
        COALESCE(v.evidence_id, l.evidence_id) AS evidence_id,
        COALESCE(v.document_id, l.document_id) AS document_id,
        COALESCE(v.version_id, l.version_id) AS version_id,
        COALESCE(v.ordinal, l.ordinal) AS ordinal,
        COALESCE(v.title, l.title) AS title,
        COALESCE(v.evidence_text, l.evidence_text) AS evidence_text,
        COALESCE(v.embedding_model, l.embedding_model) AS embedding_model,
        COALESCE(v.metadata, l.metadata) AS metadata,
        COALESCE(v.content_hash, l.content_hash) AS content_hash,
        v.vector_score AS vector_score,
        l.lexical_score AS lexical_score,
        (
            :vector_weight * COALESCE(1.0 / (:rrf_k + v.vector_rank), 0.0)
          + :lexical_weight * COALESCE(1.0 / (:rrf_k + l.lexical_rank), 0.0)
        ) AS fused_score
    FROM vector_ranked AS v
    FULL OUTER JOIN lexical_ranked AS l USING (evidence_id)
)
SELECT
    evidence_id,
    document_id,
    version_id,
    ordinal,
    title,
    evidence_text,
    embedding_model,
    metadata,
    content_hash,
    vector_score,
    lexical_score,
    fused_score
FROM fused
ORDER BY fused_score DESC, evidence_id
LIMIT :top_k
""".strip()


def _build_lexical_sql(schema: KnowledgeSqlSchema) -> str:
    eligible = _eligible_cte(schema)
    metadata_score = _metadata_hint_score_sql("e")
    metadata_match = _metadata_hint_match_sql("e")
    return f"""
WITH {eligible},
lexical_candidates AS (
    SELECT
        e.*,
        GREATEST(
            COALESCE(
                ts_rank_cd(
                    e.search_tsv,
                    websearch_to_tsquery('{schema.text_search_config}', :query_text)
                ),
                0.0
            ),
            similarity(e.evidence_text, :query_text),
            similarity(e.title, :query_text),
            {metadata_score}
        ) AS lexical_score
    FROM eligible AS e
    WHERE e.search_tsv @@ websearch_to_tsquery(
              '{schema.text_search_config}', :query_text
          )
       OR similarity(e.evidence_text, :query_text) >= :trigram_threshold
       OR similarity(e.title, :query_text) >= :trigram_threshold
       OR {metadata_match}
    ORDER BY lexical_score DESC, e.evidence_id
    LIMIT :candidate_limit
),
lexical_ranked AS (
    SELECT
        lc.*,
        ROW_NUMBER() OVER (ORDER BY lc.lexical_score DESC, lc.evidence_id) AS lexical_rank
    FROM lexical_candidates AS lc
)
SELECT
    evidence_id,
    document_id,
    version_id,
    ordinal,
    title,
    evidence_text,
    embedding_model,
    metadata,
    content_hash,
    NULL::double precision AS vector_score,
    lexical_score,
    :lexical_weight * (1.0 / (:rrf_k + lexical_rank)) AS fused_score
FROM lexical_ranked
ORDER BY fused_score DESC, evidence_id
LIMIT :top_k
""".strip()


def _build_faq_match_sql(schema: KnowledgeSqlSchema) -> str:
    eligible = _eligible_cte(schema)
    return f"""
WITH {eligible},
faq_scored AS (
    SELECT
        e.*,
        btrim(
            lower(e.title),
            E' \\t\\r\\n?!.,;:，。！？；：“”‘’（）()[]【】<>《》'
        ) = btrim(
            lower(:query_text),
            E' \\t\\r\\n?!.,;:，。！？；：“”‘’（）()[]【】<>《》'
        ) AS exact_match,
        GREATEST(
            similarity(e.title, :query_text),
            COALESCE(
                (
                    SELECT MAX(similarity(alias.value, :query_text))
                    FROM jsonb_array_elements_text(
                        CASE
                            WHEN jsonb_typeof(e.metadata -> 'aliases') = 'array'
                                THEN e.metadata -> 'aliases'
                            ELSE '[]'::jsonb
                        END
                    ) AS alias(value)
                ),
                0.0
            )
        ) AS match_score
    FROM eligible AS e
    WHERE e.source_type = 'faq'
),
faq_match AS (
    SELECT *
    FROM faq_scored
    WHERE exact_match IS TRUE
       OR match_score >= :faq_similarity_threshold
    ORDER BY exact_match DESC, match_score DESC, evidence_id
    LIMIT 1
)
SELECT
    evidence_id,
    document_id,
    version_id,
    ordinal,
    title,
    evidence_text,
    embedding_model,
    COALESCE(metadata, '{{}}'::jsonb) || jsonb_build_object(
        'source_type', source_type,
        'faq_exact', exact_match,
        'faq_match_score', match_score
    ) AS metadata,
    content_hash,
    NULL::double precision AS vector_score,
    match_score AS lexical_score,
    match_score AS fused_score
FROM faq_match
""".strip()


def _metadata_hint_values_sql(alias: str) -> str:
    return f"""
(
    CASE
        WHEN jsonb_typeof({alias}.metadata -> 'aliases') = 'array'
            THEN {alias}.metadata -> 'aliases'
        ELSE '[]'::jsonb
    END
    ||
    CASE
        WHEN jsonb_typeof({alias}.metadata -> 'tags') = 'array'
            THEN {alias}.metadata -> 'tags'
        ELSE '[]'::jsonb
    END
)
""".strip()


def _metadata_hint_score_sql(alias: str) -> str:
    values = _metadata_hint_values_sql(alias)
    return f"""
COALESCE(
    (
        SELECT MAX(similarity(hint.value, :query_text))
        FROM jsonb_array_elements_text({values}) AS hint(value)
    ),
    0.0
)
""".strip()


def _metadata_hint_match_sql(alias: str) -> str:
    values = _metadata_hint_values_sql(alias)
    return f"""
EXISTS (
    SELECT 1
    FROM jsonb_array_elements_text({values}) AS hint(value)
    WHERE similarity(hint.value, :query_text) >= :trigram_threshold
)
""".strip()


def _vector_literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(format(float(value), ".12g") for value in vector) + "]"


def _row_to_evidence(row: Mapping[str, Any]) -> RetrievedEvidence:
    raw_metadata = row.get("metadata")
    if isinstance(raw_metadata, str):
        try:
            decoded = json.loads(raw_metadata)
        except json.JSONDecodeError:
            decoded = {}
        metadata = decoded if isinstance(decoded, Mapping) else {}
    elif isinstance(raw_metadata, Mapping):
        metadata = dict(raw_metadata)
    else:
        metadata = {}

    return RetrievedEvidence(
        evidence_id=str(row["evidence_id"]),
        document_id=str(row["document_id"]),
        version_id=str(row["version_id"]),
        ordinal=int(row.get("ordinal") or 0),
        title=str(row.get("title") or "Untitled source"),
        text=str(row["evidence_text"]),
        score=float(row.get("fused_score") or 0.0),
        vector_score=(float(row["vector_score"]) if row.get("vector_score") is not None else None),
        lexical_score=(
            float(row["lexical_score"]) if row.get("lexical_score") is not None else None
        ),
        content_hash=(str(row["content_hash"]) if row.get("content_hash") else None),
        embedding_model=(str(row["embedding_model"]) if row.get("embedding_model") else None),
        metadata=metadata,
    )
