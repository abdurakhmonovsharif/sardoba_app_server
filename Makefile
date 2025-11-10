.PHONY: run dev test migrate

run:
	uvicorn app.main:app --reload

dev:
	pip install -r requirements.txt

test:
	pytest -q

migrate:
	alembic upgrade head
