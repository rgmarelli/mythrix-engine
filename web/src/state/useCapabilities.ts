import { useEffect, useState } from 'react';
import { fetchCapabilities } from '../api/client';
import type { AgentCapabilities } from '../api/types';

export type CapabilitiesStatus = 'loading' | 'ready' | 'unavailable';

/** The backend's declaration of what this build offers
 * (specs/interfaces/agent-capabilities.md), fetched once per application load
 * (FR-CAP-03) — it describes the running build, not a tab or a session, which
 * is why it lives at app level rather than inside `useTabs`.
 *
 * A failed fetch is `unavailable`, not an error state: the viewer degrades
 * (no command listing, instructions reported rather than run) but ordinary
 * turns keep working (FR-CAP-14). */
export function useCapabilities() {
  const [capabilities, setCapabilities] = useState<AgentCapabilities | null>(null);
  const [status, setStatus] = useState<CapabilitiesStatus>('loading');

  useEffect(() => {
    let active = true;
    fetchCapabilities()
      .then((result) => {
        if (!active) return;
        setCapabilities(result);
        setStatus('ready');
      })
      .catch(() => {
        if (!active) return;
        setStatus('unavailable');
      });
    return () => {
      active = false;
    };
  }, []);

  return { capabilities, status };
}
