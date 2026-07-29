// SPDX-FileCopyrightText: 2026 Guido Marelli
// SPDX-License-Identifier: AGPL-3.0-or-later

import { fetchBoundRegions } from './client';
import type {
  AgentCapabilities,
  AgentInstruction,
  HotspotQueryResult,
  InstructionBinding,
  ResultKind,
} from './types';

// Executing an agent instruction (specs/interfaces/agent-capabilities.md
// FR-CAP-07–FR-CAP-14). Dispatch is keyed on the binding's `result` kind, never
// on the instruction's `type`: the backend can introduce an instruction type
// that reuses a kind implemented here and it works with no change to this file.
export type ExecutionOutcome =
  | { kind: 'regions'; result: HotspotQueryResult }
  | { kind: 'unexecutable'; reason: string };

/** Runs one instruction against the declared capabilities.
 *
 * Returns `null` when the instruction is declared with no binding — there is
 * nothing to execute and nothing has gone wrong; the consumer handles it
 * itself (e.g. a `confirm_query` affordance). An undeclared type, a binding
 * dropped at the client seam, or a failed request all return `unexecutable`,
 * which callers surface rather than retry. */
export async function executeInstruction(
  instruction: AgentInstruction,
  capabilities: AgentCapabilities | null,
): Promise<ExecutionOutcome | null> {
  if (!capabilities) {
    return { kind: 'unexecutable', reason: `Can't run "${instruction.type}" — no capabilities loaded.` };
  }
  if (!(instruction.type in capabilities.bindings)) {
    return { kind: 'unexecutable', reason: `This build doesn't know how to run "${instruction.type}".` };
  }

  const binding = capabilities.bindings[instruction.type];
  if (binding === null) return null;

  try {
    return await RESULT_HANDLERS[binding.result](binding, instruction.payload);
  } catch (error) {
    return {
      kind: 'unexecutable',
      reason: error instanceof Error ? error.message : `Running "${instruction.type}" failed.`,
    };
  }
}

// One entry per result kind. `Record<ResultKind, …>` is what keeps this
// exhaustive: adding a kind to the vocabulary in `types.ts` without a handler
// here is a compile error, which is the type-level half of FR-CAP-10.
const RESULT_HANDLERS: Record<
  ResultKind,
  (binding: InstructionBinding, payload: Record<string, unknown>) => Promise<ExecutionOutcome>
> = {
  regions: async (binding, payload) => ({ kind: 'regions', result: await fetchBoundRegions(binding, payload) }),
};
