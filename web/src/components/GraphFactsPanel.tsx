import type { GraphFacts } from '../api/types';

interface Props {
  graphFacts: GraphFacts;
}

/** Mirrors `synthesis/prompts.py::graph_fact_lines`'s ordering: the
 * symbol/interpretation line, then each interpretation attribute, then
 * each correspondence. */
export function GraphFactsPanel({ graphFacts }: Props) {
  const { symbol, interpretation } = graphFacts;

  return (
    <section className="graph-facts">
      <h2>Graph facts</h2>
      <p>
        {'Symbol "'}
        {symbol.canonical_name}
        {'" ('}
        {symbol.symbol_type}
        {'), interpreted in '}
        {interpretation.tradition.name}
        {' as "'}
        {interpretation.display_name}
        {'": '}
        {interpretation.summary}
      </p>
      {interpretation.attributes.length > 0 && (
        <ul>
          {interpretation.attributes.map((attribute) => (
            <li key={attribute.id}>
              Attribute — {attribute.key}: {attribute.value}
            </li>
          ))}
        </ul>
      )}
      {symbol.relationships.length > 0 && (
        <ul>
          {symbol.relationships.map((relationship, index) => (
            <li key={`${relationship.relationship_type}-${relationship.target_symbol.slug}-${index}`}>
              Correspondence — {relationship.relationship_type}: relates to "
              {relationship.target_symbol.canonical_name}", according to{' '}
              {relationship.according_to_tradition.name}.
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
