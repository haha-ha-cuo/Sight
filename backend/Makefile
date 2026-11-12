.PHONY: format lint test check

format:
	uv run ruff format .

lint:
	uv run ruff check .

test:
	uv run python -m unittest discover -s tests -v

check:
	uv run ruff format --check .
	uv run ruff check .
	uv run python -m unittest discover -s tests -v
