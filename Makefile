.PHONY: lint type test run check

lint:
	ruff check .

type:
	mypy cadence

test:
	pytest

run:
	python -m cadence

check: lint type test
