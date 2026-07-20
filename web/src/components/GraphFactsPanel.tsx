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
      {symbol.properties.length > 0 && (
        <ul>
          {symbol.properties.map((property) => (
            <li key={property.id}>
              Property — {property.key}: {property.value}
            </li>
          ))}
        </ul>
      )}
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
          {symbol.relationships.map((relationship, index) => {
            const target = relationship.target_symbol;
            const hasTargetFacts = target.properties.length > 0 || relationship.target_semantic_facts.length > 0;
            return (
              <li key={`${relationship.relationship_type}-${target.slug}-${index}`}>
                Correspondence — {relationship.relationship_type}: relates to "{target.canonical_name}", according
                to {relationship.according_to_tradition.name}.
                {hasTargetFacts && (
                  <ul>
                    {target.properties.map((property) => (
                      <li key={property.id}>
                        {target.canonical_name} property — {property.key}: {property.value}
                      </li>
                    ))}
                    {relationship.target_semantic_facts.map((fact) => (
                      <li key={fact.id}>
                        {target.canonical_name} attribute — {fact.key}: {fact.value}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
