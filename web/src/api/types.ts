// Mirrors the fragment-centric query response shape `routes.py`/`query_fragments`
// emit (`core/models.py::FragmentQueryResult`, `.model_dump(mode="json")`) —
// denormalized: every fragment carries its own `source` inline. See
// specs/query-viewer-facet-redesign/plan.md.

export interface Tradition {
  id: string;
  slug: string;
  name: string;
  domain: string;
  description: string;
}

export interface Source {
  id: string;
  domain: string;
  citation_label: string;
  title: string;
  author: string;
  publication_year: number | null;
  license: string;
  uri: string;
  description: string;
  content_hash: string;
  ingested_at: string | null;
}

export interface SignSummary {
  slug: string;
  canonical_name: string;
  sign_type: string;
  semiotic_system: string;
  tradition_slugs: string[];
}

export interface FragmentMatch {
  interpretant: string;
  score: number;
  exact_value: boolean;
}

export interface Fragment {
  chunk_id: string;
  source: Source;
  text: string;
  locator: string;
  chunk_index: number;
  char_start: number;
  char_end: number;
  embedding_model: string;
  matches: FragmentMatch[];
  convergence_count: number;
}

export interface SourceFacet {
  id: string;
  label: string;
  count: number;
}

export interface InterpretantFacet {
  value: string;
  count: number;
}

export interface Facets {
  sources: SourceFacet[];
  interpretants: InterpretantFacet[];
}

export interface FragmentQueryResult {
  facets: Facets;
  fragments: Fragment[];
}
