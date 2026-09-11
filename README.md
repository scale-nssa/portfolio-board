# SCALE Active Research Portfolio (public board)

A public Streamlit app that shows SCALE's active research projects grouped into
four research buckets (Frontier Model Studies · Measures & Benchmarks · Tutoring
& AI Causal · Implementation & Other), with the people on each, and lets viewers
reassign buckets and edit team / stage / name.

**Data lives elsewhere.** This repo contains only the app UI. Project data is read
from and written to the private `scale-nssa/project-database` repo at runtime via a
GitHub token supplied through Streamlit secrets — no data is stored in this repo.

## Deploy (Streamlit Community Cloud)
1. New app → this repo, branch `main`, main file `portfolio_board_app.py`.
2. Advanced settings → Secrets:
   ```
   GITHUB_TOKEN = "…"   # a token with read+write on scale-nssa/project-database
   REPO_NAME = "scale-nssa/project-database"
   ```
3. Deploy, then set the app's Sharing to **Public**.
