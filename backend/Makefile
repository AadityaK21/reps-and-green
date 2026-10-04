# Reps & Greens backend — common tasks
.PHONY: install dev seed test lint docker up down

install:        ## install runtime + dev deps
	pip install -r requirements-dev.txt

dev:            ## run the API with autoreload
	uvicorn app.main:app --reload --port 8000

seed:           ## seed coach, products, plans, promos, catalog
	python seed.py

test:           ## run the test suite
	pytest

up:             ## start the full stack (api + mongo + redis)
	docker compose -f ../docker-compose.yml up --build

down:           ## stop the stack
	docker compose -f ../docker-compose.yml down
