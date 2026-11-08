.PHONY: help install dev-install test lint run migrate bootstrap docker-build docker-run clean

help:
	@echo "Comandos disponibles:"
	@echo "  make install        - Instala las dependencias para producción"
	@echo "  make dev-install    - Instala las dependencias para desarrollo"
	@echo "  make test           - Ejecuta los tests"
	@echo "  make lint           - Ejecuta el linter"
	@echo "  make run            - Ejecuta la aplicación en modo desarrollo"
	@echo "  make migrate        - Aplica las migraciones SQL (alembic upgrade head)"
	@echo "  make bootstrap      - Crea el admin inicial y la primera API key (idempotente)"
	@echo "  make docker-build   - Construye la imagen Docker"
	@echo "  make docker-run     - Ejecuta la aplicación en Docker"
	@echo "  make clean          - Limpia archivos temporales"

install:
	pip install -r requirements.txt

dev-install:
	pip install -r requirements.txt
	pip install pytest pytest-cov flake8 black isort mypy

test:
	pytest

test-cov:
	pytest --cov=app --cov-report=term --cov-report=html

lint:
	flake8 app tests
	black --check app tests
	isort --check-only app tests
	mypy app

format:
	black app tests
	isort app tests

run:
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

migrate:
	alembic upgrade head

bootstrap:
	python -m app.cli bootstrap

docker-build:
	docker build -t quark:latest .

docker-run:
	docker run -p 8000:8000 -v $(PWD)/data:/app/data quark:latest

docker-compose-up:
	docker-compose up -d

docker-compose-down:
	docker-compose down

clean:
	rm -rf __pycache__
	rm -rf .pytest_cache
	rm -rf htmlcov
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete 