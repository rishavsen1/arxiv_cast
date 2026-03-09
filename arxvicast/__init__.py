# ArxivCast: Intelligence Briefing (arXiv papers + two-voice podcast).
# Logically separate from the main weblogger dashboard; mounted at /intel and /api/arxiv/*.

from flask import Blueprint

arxvicast_bp = Blueprint("arxvicast", __name__, url_prefix="")

from . import routes  # noqa: E402, F401

__all__ = ["arxvicast_bp"]
