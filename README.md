# Music Arranger API

FastAPI backend for AI-powered music arrangement.

## Stack
- FastAPI + Uvicorn
- Supabase (auth + database + storage)
- basic-pitch / Demucs for audio analysis
- OpenRouter (Gemini 2.5 Flash / Claude Sonnet) for AI arrangement
- music21 + LilyPond for score generation

## Local development

```bash
cp .env.example .env
# fill in your keys

pip install -r requirements.txt
uvicorn app.main:app --reload
```

API docs available at http://localhost:8000/docs

## Deployment (Railway)

Build and run via the provided Dockerfile. Set the environment variables listed
in `.env.example` in the Railway project settings.
