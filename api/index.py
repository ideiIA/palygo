"""Ponto de entrada do Vercel (Python serverless): expõe o app FastAPI do PlayGo.
Site (/), aplicativo PWA (/app/) e API (/api/v1) saem todos deste mesmo app."""

from playgo.web.app import app  # noqa: F401
