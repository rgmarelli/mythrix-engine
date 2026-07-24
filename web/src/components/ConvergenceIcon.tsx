/** The "convergence" motif (concentric circles closing in on a point) reused
 * across empty states — matches the brand mark's idea of interpretants
 * converging on one hotspot. */
export function ConvergenceIcon() {
  return (
    <svg className="empty-icon" viewBox="0 0 48 48" fill="none">
      <circle cx="24" cy="24" r="20" stroke="currentColor" strokeWidth="1.4" opacity="0.45" />
      <circle cx="24" cy="24" r="13" stroke="currentColor" strokeWidth="1.4" opacity="0.7" />
      <circle cx="24" cy="24" r="3" fill="currentColor" />
    </svg>
  );
}
