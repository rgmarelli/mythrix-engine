# SPDX-FileCopyrightText: 2026 Guido Marelli
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Domain-agnostic error types raised across the Mythrix core library.

All Mythrix-specific errors subclass `MythrixError` so callers (notably the CLI) can
catch a single base type while still inspecting the specific failure for a tailored
message or exit code.
"""

from __future__ import annotations


class MythrixError(Exception):
    """Base class for all Mythrix-specific errors."""


class SignNotFoundError(MythrixError):
    """Raised when a query names a sign that doesn't exist in the Sign Graph."""

    def __init__(self, sign_slug: str) -> None:
        self.sign_slug = sign_slug
        super().__init__(f"No sign found with slug {sign_slug!r}.")


class TraditionNotFoundError(MythrixError):
    """Raised when a query names a tradition that doesn't exist in the Sign Graph."""

    def __init__(self, tradition_slug: str) -> None:
        self.tradition_slug = tradition_slug
        super().__init__(f"No tradition found with slug {tradition_slug!r}.")


class SourceNotFoundError(MythrixError):
    """Raised when a document is ingested for a source that hasn't been declared
    (via the structured-data loader) in the Sign Graph yet."""

    def __init__(self, source_id: str) -> None:
        self.source_id = source_id
        super().__init__(f"No source found with id {source_id!r}. Load it via the structured-data loader first.")


class ManifestationNotFoundError(MythrixError):
    """Raised when both the sign and tradition exist, but the sign has no
    manifestation recorded within that specific tradition."""

    def __init__(self, sign_slug: str, tradition_slug: str) -> None:
        self.sign_slug = sign_slug
        self.tradition_slug = tradition_slug
        super().__init__(f"Sign {sign_slug!r} has no manifestation in tradition {tradition_slug!r}.")


class IngestValidationError(MythrixError):
    """Raised when structured data fails schema or referential-integrity validation
    during loading, including an unresolvable target semiotic system (FR-SD-03).
    Nothing is written to the graph when this is raised (FR-SD-02)."""

    def __init__(self, message: str, *, source_path: str | None = None) -> None:
        self.source_path = source_path
        located = f"{source_path}: {message}" if source_path else message
        super().__init__(located)


class CitationValidationError(MythrixError):
    """Raised when generated text contains a citation marker that doesn't refer
    to material present in the retrieved context (FR-RT-04). Not raised by the
    `query` path, which invokes no generation model (FR-RT-10) — retained for the
    planned conversational agent loop, which will need the same guarantee
    over its own output."""

    def __init__(self, invalid_markers: tuple[str, ...]) -> None:
        self.invalid_markers = invalid_markers
        markers = ", ".join(invalid_markers)
        super().__init__(f"Citation marker(s) not found in retrieved context: {markers}")


class ModelUnavailableError(MythrixError):
    """Raised specifically when Ollama reports the model itself isn't installed
    (a 404 from the daemon) — as opposed to `EmbeddingRequestError`, which covers
    every other way a request to an installed model can fail."""

    def __init__(self, model: str) -> None:
        self.model = model
        super().__init__(f"Model {model!r} is not available locally. Run `ollama pull {model}` and try again.")


class ModelRequestError(MythrixError):
    """Raised when a request to an installed model (embedding or generation)
    fails for a reason other than the model being missing — e.g. the daemon
    rejected an oversized batch, ran out of memory, or the connection dropped.
    Surfaces the real cause instead of masking every failure as
    `ModelUnavailableError` (which would tell the user to `ollama pull` a model
    that's already installed)."""

    def __init__(self, model: str, *, cause: str) -> None:
        self.model = model
        self.cause = cause
        super().__init__(f"Request to model {model!r} failed: {cause}")


class AdhocQueryValidationError(MythrixError):
    """Raised when an ad-hoc query's term list fails validation — empty, or a
    term naming a directive other than `"exact"`/`"filter"` (`specs/interfaces/agnostic-query.md`
    FR-AQ-03)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class EmbeddingModelMismatchError(MythrixError):
    """Raised when the embedding model in use at query time differs from the one a
    retrieved chunk was embedded with at ingestion time — similarity scores would be
    meaningless across mismatched embedding spaces."""

    def __init__(self, ingested_with: str, querying_with: str) -> None:
        self.ingested_with = ingested_with
        self.querying_with = querying_with
        super().__init__(
            f"Chunk was embedded with {ingested_with!r} but the query is using {querying_with!r}. "
            "Re-run load-documents with the current embedding model, or reconfigure to match."
        )
