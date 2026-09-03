---
name: read-inbox
description: Process inbox/unread/ — read each message, lift durable info into a dev-docs/ detail file, add a lean backlink to dev-docs/todos.md, route actionable items to the right project's inbox, append a Status footer and move the message to inbox/read/, and auto-purge inbox/read/ entries older than 7 days.
---

# read-inbox

Triage `inbox/unread/` (feedback / bug / coordination notes, named
`YYYY-MM-DD-from-<sender>-<topic>.md`). The goal: nothing important stays
trapped in a message — it lands as a durable `dev-docs/` note plus a lean
`todos.md` backlink — and `unread/` ends empty. See AGENTS.md "Inbox hygiene"
and the layout map `inbox/README.md`.

## 1. Auto-purge the read archive (always first)

Hard-delete `inbox/read/` entries that are **both** older than 7 days **and**
carry the `## Status (microbiomekg, …)` footer step 5 appends. The footer is
the marker that the message went through triage and its durable record now
lives in `dev-docs/`; age alone is not evidence of that (`R4`: purge by an
explicit marker, not by age).

```bash
grep -rls '^## Status (microbiomekg' inbox/read \
  | while IFS= read -r f; do
      [ -n "$(find "$f" -type f -mtime +7)" ] && printf '%s\n' "$f" && rm "$f"
    done
```

Anything in `inbox/read/` **without** the footer was archived by hand and may
be the only copy of that coordination — list it for the user, never delete it.
Report what was purged, or "nothing aged out".

## 2. Read every unread message

List `inbox/unread/`. Read each file fully. For each: does it carry durable
info, an open action, a decision, or is it a no-action acknowledgement?

## 3. Lift durable info → dev-docs/ + todos

Route per `dev-docs/README.md`:

- **Actionable** content → file it with the **`add-todo`** entry rules (that
  skill is the authority on todo shape): classify → the right `todos.md`
  section, scope the detail into a `plans/` doc (reuse one by theme), add the
  lean backlink plus a link to the source message. A message surfacing
  *several* actions is add-todo's batch mode — decompose, group, file each.
- **A design choice / trade-off** (a source-format decision, a schema-mapping
  option, an evidence-vocabulary argument) → a `dev-docs/designs/` reference
  doc instead, with no todo — it is reference, not an action.
- A no-action ack needs no todo — note it in the move footer.

Don't restate the todo-entry format here.

## 4. Route actionable items to the party who can act

If a message carries an **actionable task for another project**, file a note to
their inbox as `YYYY-MM-DD-from-microbiomekg-<topic>.md`. The most common
target is **kglite** (`../../Rust/KGLite/inbox/unread/`) — a blueprint,
ontology, Cypher or save/load limitation this repo ran into is the engine's to
fix, not ours to work around. Use the **`notify`** skill to compose it and to
resolve any path you are unsure of. Only route when there is genuinely
something for them to do.

## 5. Append Status footer, move to read/

Append one line before archiving:

`## Status (microbiomekg, <date>): <lifted to dev-docs/…; todo added | routed to X | no action>`

then move the file from `inbox/unread/` to `inbox/read/`. `unread/` must end
empty — every message is lifted+tracked, routed, or a logged no-action ack.

## 6. Flag to the user

Short summary: **new todos** (with detail-file paths), anything **routed**, and
any item that **needs a user decision**. Recommend keep/drop for the ambiguous.

## Output discipline

Under 400 tokens. If the write-up is long, put the full report in
`dev-docs/temp/inbox-triage.md` (1-day purge) and report that path.

## Relationship to the other skills

Shares `dev-docs/todos.md` with `dev-docs-cleanup` and `phased-plan` (which
folds relevant todos into a new plan on the user's go-ahead). `<date>` is the
session date, not a guess.
