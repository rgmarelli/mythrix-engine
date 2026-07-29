// SPDX-FileCopyrightText: 2026 Guido Marelli
// SPDX-License-Identifier: AGPL-3.0-or-later

import { findAndReplace } from 'mdast-util-find-and-replace';
import type { Root } from 'mdast';

// react-markdown's default `urlTransform` blanks any `href` whose scheme
// isn't in its safe-protocol allowlist (http(s)/irc(s)/mailto/xmpp), so a
// region id cannot travel as the link's `url`. It travels as a hast property
// instead — `data.hProperties` merges onto the rendered `<a>` regardless of
// `url` (mdast-util-to-hast's `applyData`) — with `url: '#'` kept only so the
// node renders as a real anchor.
export const REGION_ID_ATTRIBUTE = 'data-region-id';

const MARKER_PATTERN = /\[R\d+\]/g;

// Rewrites the AST rather than the raw markdown string so text inside code
// spans is left untouched (`findAndReplace` only visits text nodes).
export function remarkRegionMarkers(regionMarkers: Record<string, string> = {}) {
  return (tree: Root) => {
    findAndReplace(tree, [
      [
        MARKER_PATTERN,
        (marker: string) => {
          const regionId = regionMarkers[marker];
          if (!regionId) return false;
          return {
            type: 'link',
            url: '#',
            data: { hProperties: { [REGION_ID_ATTRIBUTE]: regionId } },
            children: [{ type: 'text', value: marker }],
          };
        },
      ],
    ]);
  };
}
