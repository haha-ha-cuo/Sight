.PHONY: format lint test check

format:
	uv run ruff format . ../scripts

lint:
	uv run ruff check . ../scripts

test:
	uv run python -m unittest discover -s tests -v

check:
	uv run ruff format --check . ../scripts
	uv run ruff check . ../scripts
	uv run python -m unittest discover -s tests -v
