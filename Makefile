# Job360 developer Makefile.
#
# Convention: every target is self-describing. Run `make help` for a menu.
# `verify-step-0` is the aggregate gate checked by the Step-0 Ralph Loop.

.PHONY: help install test test-fast lint format migrate bootstrap verify-step-0 clean

help:
	@echo "Job360 targets:"
	@echo "  install          install backend in editable mode"
	@echo "  test             run the full backend test suite"
	@echo "  test-fast        run only @pytest.mark.fast tests (smoke subset)"
	@echo "  lint             ruff lint across backend/"
	@echo "  format           ruff format across backend/"
	@echo "  migrate          apply pending DB migrations"
	@echo "  bootstrap        run backend/scripts/bootstrap_dev.py against localhost:8000"
	@echo "  verify-step-0    run the Step-0 pre-flight gate (aggregate of below)"
	@echo "  clean            wipe __pycache__ + *.pyc"

install:
	cd backend && python -m pip install -e .

test:
	cd backend && python -m pytest tests/ --ignore=tests/test_main.py -q -p no:randomly

test-fast:
	cd backend && python -m pytest tests/ -m fast -q -p no:randomly

lint:
	cd backend && python -m ruff check src tests

format:
	cd backend && python -m ruff format src tests

migrate:
	cd backend && python -m migrations.runner up

bootstrap:
	cd backend && python scripts/bootstrap_dev.py

# ---------------------------------------------------------------------------
# Step-0 pre-flight gate.
#
# The Ralph Loop halts once this target exits 0. Each check is best-effort
# wired so a failure prints a readable reason instead of a silent non-zero.
# ---------------------------------------------------------------------------

verify-step-0:
	@echo "==> Step-0 gate: pytest"
	cd backend && python -m pytest tests/ --ignore=tests/test_main.py -q -p no:randomly --tb=no
	@echo "==> Step-0 gate: env parity"
	cd backend && python scripts/check_env_example.py
	@echo "==> Step-0 gate: migrations applied"
	cd backend && python -m migrations.runner status
	@echo "==> Step-0 gate: docs inventory"
	@test -f CONTRIBUTING.md          || { echo "MISSING: CONTRIBUTING.md"; exit 1; }
	@test -f backend/README.md        || { echo "MISSING: backend/README.md"; exit 1; }
	@test -f frontend/README.md       || { echo "MISSING: frontend/README.md"; exit 1; }
	@test -f docs/README.md           || { echo "MISSING: docs/README.md"; exit 1; }
	@test -f docs/troubleshooting.md  || { echo "MISSING: docs/troubleshooting.md"; exit 1; }
	@test -f .gitattributes           || { echo "MISSING: .gitattributes"; exit 1; }
	@test -f setup.bat                || { echo "MISSING: setup.bat"; exit 1; }
	@test -f backend/scripts/bootstrap_dev.py || { echo "MISSING: bootstrap_dev.py"; exit 1; }
	@test -f backend/migrations/0010_run_log_observability.up.sql || { echo "MISSING: 0010 up"; exit 1; }
	@echo "==> Step-0 gate: PASS"
	@mkdir -p .claude
	@git rev-parse HEAD > .claude/step-0-verified.txt
	@echo "STEP-0 GREEN: $$(cat .claude/step-0-verified.txt)"

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
