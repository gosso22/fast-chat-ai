.PHONY: install dev test lint format clean run

# Install dependencies
install:
	pip install -r requirements.txt

# Install development dependencies
dev: install
	pip install -e .

# Run tests
test:
	pytest

# Run linting
lint:
	flake8 app tests
	mypy app

# Format code
format:
	black app tests
	isort app tests

# Clean cache files
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +

# Run development server
run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Run development server with debug
debug:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --log-level debug