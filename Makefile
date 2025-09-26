SHELL := /bin/bash

.PHONY: up down logs test lint fmt download-models

up:
	docker compose up -d --build

down:
	docker compose down -v

logs:
	docker compose logs -f

test:
	./scripts/run-tests.sh

lint:
	ruff check backend
	npm --prefix frontend run lint

fmt:
	ruff format backend
	npm --prefix frontend run lint -- --fix

download-models:
	./scripts/download-models.sh
