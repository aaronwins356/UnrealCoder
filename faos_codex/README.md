# FAOS Codex

FAOS Codex is an autonomous coding environment designed to translate natural language project descriptions into runnable code. This repository snapshot captures the initial architectural vision and project scaffold that will be extended in subsequent iterations.

## High-Level Architecture Overview

FAOS Codex is organized around four collaborating subsystems:

1. **Interaction Front-End**
   - Presents a user interface (terminal UI for the first iteration, with the option to evolve into a web dashboard).
   - Collects project descriptions and displays generated artefacts and status updates.

2. **Orchestration & Project Management Core**
   - Coordinates requests between the front-end, model interface, and code execution sandbox.
   - Persists project sessions, including user intents, generated files, execution logs, and metadata.
   - Manages workspace directory layouts and versioning of generated outputs.

3. **Model Gateway (LLM Interface Layer)**
   - Connects to a locally hosted LLM endpoint (e.g., Hugging Face Text Generation Inference, vLLM, or other REST-compatible backends).
   - Normalizes prompts, handles retries/timeouts, and enforces safety guards before releasing generated code to the project manager.

4. **Execution Sandbox (Optional, Pluggable)**
   - Provides an isolated environment for executing generated code snippets or full projects.
   - Collects runtime telemetry and reports back to the orchestration layer for display and persistence.

These components communicate via explicit service boundaries to keep responsibilities well-defined and testable.

## Proposed Directory Structure

```text
faos_codex/
├── app.py                 # Entry point for the CLI prototype
├── requirements.txt       # Python dependencies for the project (to be expanded incrementally)
├── README.md              # Project overview, architecture summary, and setup instructions
└── docs/
    └── ARCHITECTURE.md    # Detailed architectural description and design notes
```

Future iterations will populate additional modules within subpackages such as `frontend/`, `core/`, `llm_gateway/`, and `sandbox/` in alignment with the architecture above.

## Installation Instructions

FAOS Codex targets Python 3.11+ on Linux or WSL. To set up the prototype environment, run:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

> **Note:** The initial prototype has no third-party dependencies beyond the Python standard library; the `requirements.txt` file is intentionally empty and will evolve alongside the system.

## Running the Prototype

Activate your virtual environment (if using one) and execute:

```bash
python app.py
```

Expected output:

```
FAOS Codex initialized.
```

This confirms that the foundational scaffold is in place. Subsequent iterations will flesh out each subsystem and deliver the full autonomous coding workflow.

