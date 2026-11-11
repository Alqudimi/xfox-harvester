.PHONY: setup run dev test lint format migrate web-build web-dev docker-up docker-down clean

setup:            ## full local setup (venv + browser + env + web + migrate)
	./scripts/setup.sh

run:              ## start the production server
	./scripts/run.sh

dev:              ## start API with auto-reload (port 8000)
	uvicorn xfox.main:app --reload --port 8000

web-dev:          ## start the console dev server with proxy (port 5173)
	cd web && npm run dev

web-build:        ## build the console into web/dist
	cd web && npm run build

test:             ## run the whole test suite
	pytest

lint:             ## static analysis (clean-code gate)
	ruff check xfox/ tests/

format:           ## auto-format then lint
	ruff check xfox/ tests/ --fix

migrate:          ## apply database migrations
	alembic upgrade head

docker-up:        ## build & start the full stack (app + postgres)
	docker compose -f docker/docker-compose.yml up -d --build

docker-down:      ## stop the stack
	docker compose -f docker/docker-compose.yml down

clean:            ## remove caches and build artifacts
	rm -rf .pytest_cache .ruff_cache **/__pycache__ web/dist
