# MicrobiomeKG — the local gate
#
# There is no CI (no remote yet — docs/design/library-pipeline.md item 5), so
# `make gate` is not a relevance filter ahead of a matrix: it is the whole net.
# It must therefore be fast enough to run before every commit, and it must be
# able to fail. Every target below either does its check or errors with the fix
# printed; none of them skips with a notice.
#
#   make gate     the pre-commit gate (~30 s): adapters, accumulation bounds,
#                 ruff, blueprint composition, the two truth gates
#   make test     the full suite
#   make build    build the graph (minutes; needs data/raw)
#   make prune-dev  the bounded regenerable tiers (R4)
#
# `make gate` compiles nothing and builds no graph. It *reads* the built graph,
# so on a tree that has none it fails with the build command printed rather
# than passing — green and not-attempted must not render identically (R10).

SHELL := /bin/bash

VENV   := .venv
PY     := $(VENV)/bin/python
RUFF   := $(VENV)/bin/ruff
# Everything the gate itself needs, plus the engine. One list, so a tool added
# to a gate is installed by `make venv` in the same change and the gate cannot
# no-op for whoever has not installed it by hand.
DEV_DEPS := pytest pytest-timeout ruff build "kglite>=0.16.22" pandas openpyxl requests
# Every Python path ruff owns. Referenced by check and format alike so the two
# cannot drift apart and silently stop covering a directory.
PY_PATHS := microbiomekg scripts tests bench

GRAPH := graph/microbiomekg.kgl

.PHONY: gate lint ruff-check ruff-fix fragments claims test build serve venv \
        check-adapters sync-adapters check-dev-docs check-data-bounds \
        prune-dev check-graph check-install

## The gate. Order is cheapest-first so a trivial failure costs a second.
gate: check-adapters check-dev-docs check-data-bounds lint fragments claims
	@echo ""
	@echo "=================================================="
	@echo " gate: ALL STEPS PASSED"
	@echo "=================================================="

## R7 — the two harness adapters are equivalent to what the authority implies.
## The check regenerates into memory and diffs against disk, so a hand-edited
## adapter, a missing file and an orphan file are all failures.
check-adapters:
	@echo "== [1/6] agent adapters (R7) =="
	$(PY) scripts/sync_agent_adapters.py --check

## Regenerate AGENTS.md + .agents/skills/ from CLAUDE.md + .claude/skills/.
## Never edit an adapter by hand — merge the improvement into the authority and
## run this (RULES.md R7, and dev-docs-cleanup §6).
sync-adapters:
	$(PY) scripts/sync_agent_adapters.py

## R4 — the gitignored working folder has a bound with an owner. Unlike the
## caches this NEVER deletes: which tier a file belongs in, and whether it is
## reproducible, is a judgement, so the gate FAILS and hands the decision back.
## Entries past their documented lifetime are a warning, not a failure — temp/
## and bin/ churn is normal working state, and failing on it would only teach
## people to bypass the gate. Tier lifecycles: dev-docs/README.md.
DEV_DOCS_MAX_MB ?= 256
check-dev-docs:
	@echo "== [2/6] dev-docs bound (R4) =="
	@[ -d dev-docs ] || { echo "no dev-docs/ — nothing to bound"; exit 0; }; \
	mb=$$(du -sm dev-docs | cut -f1); \
	stale=$$( { find dev-docs/temp -mindepth 1 -maxdepth 1 -mtime +1; \
	            find dev-docs/bin  -mindepth 1 -maxdepth 1 -mtime +7; \
	          } 2>/dev/null ); \
	if [ "$${mb:-0}" -ge $(DEV_DOCS_MAX_MB) ]; then \
		echo "FAIL: dev-docs/ is $${mb} MB (>= $(DEV_DOCS_MAX_MB) MB)"; \
		du -sm dev-docs/* 2>/dev/null | sort -rn | head -8 | sed 's/^/    /'; \
		[ -z "$$stale" ] || { echo "  past their documented lifetime:"; echo "$$stale" | sed 's/^/    /'; }; \
		echo "  -> reclaim, or move anything irreproducible to a durable tier (dev-docs/README.md)"; \
		exit 1; \
	fi; \
	echo "dev-docs/ is $${mb} MB (limit $(DEV_DOCS_MAX_MB) MB)"; \
	[ -z "$$stale" ] || { echo "WARN: past their documented lifetime (dev-docs/README.md):"; \
	                      echo "$$stale" | sed 's/^/    /'; }

## R4 — every other accumulation, each with its own bound and owner.
##
## data/raw/ is the exception that proves the rule: it is OPERATOR-OWNED, it is
## never pruned by anything here, and three of its origins (HMDB, MiMeDB, MASI)
## are browser-only downloads that cannot be re-fetched by a script. This target
## reports its size and touches nothing.
##
## The other three regenerate: data/csv/ is emptied by every build, graph/ holds
## one .kgl per build, and bench/results/ is the tracked longitudinal record
## (small json/md — heavy capture output goes to the scratch dir bench/README.md
## names, outside the repo). Each ceiling is generous: the failure being caught
## is an accumulation nothing owns, not a legitimate large build.
DATA_CSV_MAX_MB ?= 2048
GRAPH_MAX_MB    ?= 512
BENCH_RESULTS_MAX_MB ?= 5
check-data-bounds:
	@echo "== [3/6] data + artifact bounds (R4) =="
	@fail=0; \
	if [ -d data/raw ]; then \
		echo "  data/raw/         $$(du -sh data/raw | cut -f1)  operator-owned, never pruned automatically"; \
	fi; \
	for pair in "data/csv:$(DATA_CSV_MAX_MB)" "graph:$(GRAPH_MAX_MB)" "bench/results:$(BENCH_RESULTS_MAX_MB)"; do \
		d=$${pair%%:*}; cap=$${pair##*:}; \
		[ -d "$$d" ] || continue; \
		mb=$$(du -sm "$$d" | cut -f1); \
		if [ "$${mb:-0}" -ge "$$cap" ]; then \
			echo "  FAIL: $$d/ is $${mb} MB (>= $${cap} MB)"; \
			du -sm "$$d"/* 2>/dev/null | sort -rn | head -5 | sed 's/^/      /'; \
			fail=1; \
		else \
			echo "  $$d/  $${mb} MB (limit $${cap} MB)"; \
		fi; \
	done; \
	if [ "$$fail" = 1 ]; then \
		echo "  -> a build rewrites data/csv/ and graph/; anything else in them is an"; \
		echo "     accumulation nobody owns. Reclaim it, or give it a tier (CLAUDE.md R4 table)."; \
		exit 1; \
	fi

## ruff over every Python path: lint, then formatting. HARD-FAILS when ruff is
## missing rather than skipping — a gate that can silently no-op is not a gate,
## which is why ruff is in DEV_DEPS.
lint: ruff-check
ruff-check:
	@echo "== [4/6] ruff check + format --check =="
	@if [ ! -x "$(RUFF)" ]; then \
		echo "ERROR: ruff is not installed in $(VENV)."; \
		echo "       Run 'make venv' and retry."; \
		exit 1; \
	fi
	$(RUFF) check $(PY_PATHS)
	$(RUFF) format --check $(PY_PATHS)

## Apply ruff's fixes + formatting (convenience; not part of the gate).
ruff-fix:
	$(RUFF) check --fix $(PY_PATHS)
	$(RUFF) format $(PY_PATHS)

## The tracked blueprint.json is composed from every microbiomekg/blueprints/*.json fragment.
## --check fails if composing them would change the file, so a fragment edit
## that was never composed cannot reach a commit.
fragments:
	@echo "== [5/6] blueprint composition =="
	$(PY) scripts/build_blueprint.py --check

## The two truth gates: the prose an agent reads, and the queries the user
## contract documents. Both execute against the built graph.
claims: check-graph
	@echo "== [6/6] claim gate + documented queries =="
	$(PY) -m pytest -q tests/test_skill_claims.py tests/test_documented_queries.py

## Both truth gates read the built graph. An absent graph is not a pass (R10).
check-graph:
	@if [ ! -f $(GRAPH) ]; then \
		echo "ERROR: $(GRAPH) does not exist, so the truth gates cannot run."; \
		echo "       An absent graph is NOT a pass. Build it first:"; \
		echo "         make build       # ~minutes, needs data/raw (see docs/sources.md)"; \
		exit 1; \
	fi

## The full suite.
test:
	$(PY) -m pytest -q

## Build the graph. Minutes, and it needs data/raw/ — never part of a gate.
## ARGS passes flags through: make build ARGS='--with-kegg --with-vectors'.
build:
	$(PY) scripts/build.py $(ARGS)

## The MCP server over stdio. `make serve ARGS=--selftest` for the
## green/red configuration check.
serve:
	$(PY) scripts/serve.py $(ARGS)

## Provision the dev venv (idempotent). The single place that decides what the
## gates need installed — add a tool to a gate and add it here in the same
## change, or the gate no-ops for everyone who has not installed it by hand.
venv:
	@if [ ! -x "$(PY)" ]; then \
		if command -v uv >/dev/null 2>&1; then uv venv $(VENV); \
		else python3 -m venv $(VENV); fi; \
	fi
	@if command -v uv >/dev/null 2>&1; then \
		uv pip install --python $(PY) --upgrade $(DEV_DEPS); \
		uv pip install --python $(PY) --no-deps -e .; \
	else \
		$(PY) -m pip install --upgrade $(DEV_DEPS); \
		$(PY) -m pip install --no-deps -e .; \
	fi
	@echo "== venv: $(VENV) provisioned (package installed editable) =="

## The install proof (docs/design/release-readiness.md §3): build a wheel and
## an sdist into a scratch dir, install the wheel into a CLEAN venv outside
## the repo root so the checkout cannot shadow it, and run the three verbs
## against an empty data directory. Not part of `make gate` — it provisions a
## venv — but it is the check that the package is a package.
check-install:
	$(PY) scripts/check_install.py

## The regenerable tiers, and only those (R4). Never touches data/raw/ (the
## operator owns it and three of its sources are browser-only), data/csv/ or
## graph/ (a build owns those), or bench/results/ (the tracked record).
prune-dev:
	@echo "purging regenerable caches and the time-boxed dev-docs tiers"
	@rm -rf .pytest_cache .ruff_cache
	@find . -name '__pycache__' -type d -not -path './.venv/*' -prune -print -exec rm -rf {} + 2>/dev/null || true
	@find . -name '.DS_Store' -not -path './.venv/*' -print -delete 2>/dev/null || true
	@mkdir -p dev-docs/temp dev-docs/bin
	@find dev-docs/temp -type f -mmin +1440 -print -delete 2>/dev/null || true
	@find dev-docs/bin  -type f -mtime +7   -print -delete 2>/dev/null || true
	@echo "kept: data/raw (operator-owned), data/csv, graph/, bench/results, .venv"
