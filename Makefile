.PHONY: install lint format types boundaries test schemas security ci clean

install:
	pip install -e ".[dev,aws,report,analysis]"

lint:
	ruff check .
	ruff format --check .

format:
	ruff format .
	ruff check --fix .

types:
	mypy

boundaries:
	lint-imports
	pytest -m unit tests/unit/test_import_boundaries.py -q

test:
	pytest -m "unit or integration" --cov=chainbreak --cov-report=term-missing -q

schemas:
	python -m chainbreak.scenarios.export_schema schemas
	git diff --exit-code schemas/

security:
	bandit -r src/ -q
	pip-audit --skip-editable

# Runs everything the CI 'test' + 'boundaries' + 'lint' + 'types' jobs run, locally.
ci: lint types boundaries test

clean:
	find . -name '__pycache__' -not -path './.venv/*' -type d -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
