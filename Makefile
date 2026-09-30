# Cross-platform pipeline. On Windows use Git Bash or `python src/run_pipeline.py`.
ifeq ($(OS),Windows_NT)
  VENV_PY := .venv/Scripts/python.exe
  VENV_PIP := .venv/Scripts/pip.exe
else
  VENV_PY := .venv/bin/python
  VENV_PIP := .venv/bin/pip
endif

.PHONY: all setup ingest pipeline test figures clean-outputs

all: setup pipeline test

setup:
	python -m venv .venv
	$(VENV_PY) -m pip install --upgrade pip
	$(VENV_PIP) install -r requirements.txt

pipeline:
	$(VENV_PY) -m src.run_pipeline

ingest:
	$(VENV_PY) -m src.run_pipeline --stop-after ingest

test:
	$(VENV_PY) -m pytest -q tests

figures:
	$(VENV_PY) -m src.run_pipeline --stop-after eda

clean-outputs:
	$(VENV_PY) -c "import shutil, pathlib; p=pathlib.Path('data/processed'); shutil.rmtree(p, ignore_errors=True); p.mkdir(parents=True, exist_ok=True)"
