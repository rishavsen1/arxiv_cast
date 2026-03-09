"""ArxivCast routes: /intel and /api/arxiv/*. All ArxivCast logic lives in core; routes delegate and serve generated HTML."""

from datetime import datetime

from flask import Response, jsonify, render_template, request

from . import arxvicast_bp
from . import core


@arxvicast_bp.route("/intel")
def intel_page():
    return render_template("intel.html")


@arxvicast_bp.route("/api/arxiv/matrix-html")
def matrix_html():
    categories_param = request.args.get("categories")
    date_param = request.args.get("date")
    papers_per_tag_param = request.args.get("papers_per_tag")
    categories = None
    if categories_param:
        categories = [c.strip() for c in categories_param.split(",") if c.strip()]
    date = None if not date_param or date_param == "latest" else date_param
    papers_per_tag = None
    if papers_per_tag_param:
        try:
            papers_per_tag = int(papers_per_tag_param)
            if papers_per_tag < 1:
                papers_per_tag = None
        except ValueError:
            pass
    if categories is not None or date is not None or papers_per_tag is not None:
        try:
            html = core.get_matrix_html(
                limit=120, date=date, categories=categories, papers_per_tag=papers_per_tag
            )
            return Response(html, mimetype="text/html; charset=utf-8")
        except Exception:
            pass
    if core.OUTPUT_HTML_PATH.is_file():
        with open(core.OUTPUT_HTML_PATH, "r", encoding="utf-8") as f:
            return Response(f.read(), mimetype="text/html; charset=utf-8")
    return Response(
        '<p class="text-slate-500 text-sm p-6">No data yet. Choose categories and date, then click <strong>Search &amp; Populate</strong> to fetch papers.</p>',
        mimetype="text/html; charset=utf-8",
    )


@arxvicast_bp.route("/api/arxiv/synopsis-html")
def synopsis_html():
    if core.SYNOPSIS_HTML_PATH.is_file():
        with open(core.SYNOPSIS_HTML_PATH, "r", encoding="utf-8") as f:
            return Response(f.read(), mimetype="text/html; charset=utf-8")
    return Response(
        '<p class="text-slate-500 text-sm">No transcript yet. Generate a podcast from the options above.</p>',
        mimetype="text/html; charset=utf-8",
    )


@arxvicast_bp.route("/api/arxiv/clear", methods=["POST"])
def clear():
    try:
        core.clear_papers()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@arxvicast_bp.route("/api/arxiv/fetch", methods=["POST"])
def fetch():
    data = request.get_json(force=True, silent=True) or {}
    categories = data.get("categories")
    papers_per_tag = data.get("papers_per_tag")
    limit = data.get("limit", 120)
    today = datetime.now().strftime("%Y-%m-%d")
    date = data.get("date")
    if date is not None and date != "":
        if date > today:
            return jsonify({"ok": False, "error": "Date cannot be in the future. Choose today or earlier."}), 400
    else:
        date = None
    if categories is not None and not isinstance(categories, list):
        categories = [c.strip() for c in str(categories).split(",") if c.strip()]
    try:
        core.init_db()
        result = core.fetch_and_store(categories=categories, papers_per_tag=papers_per_tag, date=date)
        core.generate_html(limit=limit, date=date, papers_per_tag=papers_per_tag)
        return jsonify({"ok": True, **result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@arxvicast_bp.route("/api/arxiv/podcast", methods=["POST"])
def podcast():
    data = request.get_json(force=True, silent=True) or {}
    style = data.get("style", "easy")
    length = data.get("length", "medium")
    custom_style = data.get("custom_style") or None
    date = data.get("date")
    paper_ids = data.get("paper_ids") or None
    if isinstance(paper_ids, list):
        paper_ids = [str(p).strip() for p in paper_ids if str(p).strip()]
        if not paper_ids:
            paper_ids = None
    else:
        paper_ids = None
    try:
        result = core.generate_podcast_and_synopsis(
            style=style, length=length, custom_style=custom_style, date=date, paper_ids=paper_ids
        )
        return jsonify({"ok": True, "result": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@arxvicast_bp.route("/api/arxiv/categories")
def categories():
    try:
        return jsonify({"categories": core.CATEGORIES, "tree": core.CATEGORIES_TREE})
    except Exception:
        return jsonify({
            "categories": [
                "cs.LG", "cs.AI", "cs.SY", "cs.RO", "cs.NE", "cs.CE",
                "eess.SY", "eess.SP", "math.OC", "stat.ML", "econ.EM", "physics.soc-ph",
            ],
            "tree": {
                "cs": ["AI", "LG", "SY", "RO", "NE", "CE"],
                "eess": ["SY", "SP"],
                "math": ["OC"],
                "stat": ["ML"],
                "econ": ["EM"],
                "physics": ["soc-ph"],
            },
        })
