import type { GraphFacts } from '../api/types';

interface Props {
  graphFacts: GraphFacts;
}

/** Mirrors `synthesis/prompts.py::graph_fact_lines`'s ordering: the
 * symbol/manifestation line, then each manifestation interpretant, then
 * each correspondence — plus the sign's and manifestation's own `properties`
 * (structural facts, never fed to retrieval), shown for human context only. */
export function GraphFactsPanel({ graphFacts }: Props) {
  const { sign, manifestation } = graphFacts;

  return (
    <section className="graph-facts">
      <h2>Graph facts</h2>
      <p>
        {'Symbol "'}
        {sign.canonical_name}
        {'" ('}
        {sign.sign_type}
        {'), interpreted in '}
        {manifestation.tradition.name}
        {' as "'}
        {manifestation.display_name}
        {'": '}
        {manifestation.denotation}
      </p>
      {sign.properties.length > 0 && (
        <ul>
          {sign.properties.map((property) => (
            <li key={property.id}>
              Property — {property.key}: {property.value}
            </li>
          ))}
        </ul>
      )}
      {manifestation.properties.length > 0 && (
        <ul>
          {manifestation.properties.map((property) => (
            <li key={property.id}>
              Property — {property.key}: {property.value}
            </li>
          ))}
        </ul>
      )}
      {manifestation.interpretants.length > 0 && (
        <ul>
          {manifestation.interpretants.map((interpretant) => (
            <li key={interpretant.id}>
              Interpretant — {interpretant.type}: {interpretant.value}
            </li>
          ))}
        </ul>
      )}
      {sign.intersemiotic_interpretants.length > 0 && (
        <ul>
          {sign.intersemiotic_interpretants.map((interpretant, index) => {
            const target = interpretant.target_sign;
            const hasTargetFacts = target.properties.length > 0 || interpretant.target_interpretants.length > 0;
            return (
              <li key={`${interpretant.relationship}-${target.slug}-${index}`}>
                Correspondence — {interpretant.relationship}: relates to "{target.canonical_name}", according
                to {interpretant.according_to.name}.
                {hasTargetFacts && (
                  <ul>
                    {target.properties.map((property) => (
                      <li key={property.id}>
                        {target.canonical_name} property — {property.key}: {property.value}
                      </li>
                    ))}
                    {interpretant.target_interpretants.map((targetInterpretant) => (
                      <li key={targetInterpretant.id}>
                        {target.canonical_name} interpretant — {targetInterpretant.type}: {targetInterpretant.value}
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
