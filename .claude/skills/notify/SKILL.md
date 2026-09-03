---
name: notify
description: Send a coordination/feedback note to another local project's inbox. Resolves a target repo by name anywhere under the Koding/ workspace root, composes a message file per the inbox schema, and drops it in that repo's inbox/unread/ (creating the folder if missing).
---

# notify

Deliver a message to a sibling project's inbox so its maintainer/agent picks it
up on their next `read-inbox`. Input: a **target repo** (name or path) and the
**message** (topic + body; compose from the conversation if not given).

The most frequent target is **`KGLite`** — the engine this graph is built on.
A blueprint, ontology, Cypher, index or save/load limitation a prep or a query
hits is kglite's to fix; send it there rather than working around it silently
(CLAUDE.md "Working style"). `docs/model.md` §8 is the running list of those
asks and is worth quoting in the note.

This skill **only sends**. It never touches our own inbox.

## 1. Resolve the target repo path

The workspace root is **`/Volumes/EksternalHome/Koding`**. Sibling projects sit
under category folders — `Rust/` (KGLite, kglite-datasets, doctrine, sonagram,
codingest, …), `Python/`, `mcp-servers/` — at depth 1–2. Search by name,
case-insensitively:

```bash
KODING="${PWD%%/Koding/*}/Koding"
find "$KODING" -maxdepth 3 -type d -iname '<name>' \
  -not -path '*/node_modules/*' -not -path '*/.git/*' \
  -not -path '*/__pycache__/*' -not -path '*/target/*' \
  -not -path '*/.venv/*' -not -path '*/data/*' \
  -not -path '*/mcp-servers/*'
```

- **`mcp-servers/` is one externally-managed project, not a tree of repos.**
  Its subdirs (`code_review/`, `legal/`, `open_source/`, …) are components, not
  notify targets — which is why they are excluded above. To reach that
  ecosystem, target **`mcp-servers`** itself → its single `inbox/unread/`.
- **`doctrine`** is the estate's rules repo. A rule that needs changing, or a
  registration gap in `rules/conform.py`, goes there — not into a local
  workaround.
- **Exactly one match** → use it. **Several** → prefer a git repo (has
  `.git/`); if still ambiguous, ask the user, showing the candidates.
  **None** → widen to `-maxdepth 4`, then ask.
- If the caller gave an absolute path, skip the search.

Confirm the resolved path before writing if there was any ambiguity — this
writes into another project's working tree.

## 2. Ensure the inbox exists

```bash
mkdir -p "<target>/inbox/unread"
```

Expected for a first note to a project that has no inbox yet.

## 3. Compose the message (the schema)

Filename: **`<YYYY-MM-DD>-from-microbiomekg-<topic-slug>.md`** (date = session
date, kebab-case topic). Body:

```markdown
# <Short title>

- **From:** microbiomekg
- **To:** <target repo>
- **Date:** <YYYY-MM-DD>
- **Type:** feedback | bug | coordination | heads-up | request
- **Re:** <optional — version, file, prior message it responds to>

<1–3 paragraphs: what happened / what is needed and why.>

## Ask / action requested
- <concrete, actionable item(s) — or "FYI, no action needed">

## References
- <file paths, commit SHAs, versions, the query that shows it — optional>
```

For an engine ask, include the **reproduction**: the smallest blueprint or
Cypher that shows it, the kglite version it was seen on, and what this repo
does instead today. An ask without a reproduction costs the engine a
round-trip.

Keep it actionable: file a note only if there is something for them to do or
genuinely useful to know (CLAUDE.md "Route to the party who can act").

## 4. Write + report

Write to `<target>/inbox/unread/<filename>` and report the full path.

## Notes

- Under 400 tokens.
- This is the send side; `read-inbox` is the receive side. Same filename schema
  both ways, so the recipient's triage just works with no per-pair wiring.
- A local inbox note is a **file**, not a publication. Anything that leaves this
  machine under the user's identity — a GitHub issue, a comment, an email — is
  governed by `R6` and needs in-the-moment approval of the exact text.
