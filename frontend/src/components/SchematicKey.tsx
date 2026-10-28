import { LEGEND } from "@/data/key";

// Collapsed key for the schematic below: what U, J, TP and R mean, and the tags. For closer readers; the intro above
// is the plain-language version.
export function SchematicKey() {
  return (
    <details className="key">
      <summary className="silk">How to read the schematic</summary>
      <dl>
        {LEGEND.map((l) => (
          <div key={l.term}>
            <dt>{l.term}</dt>
            <dd>{l.means}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}
