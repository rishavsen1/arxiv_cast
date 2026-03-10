"""ArxivCast routes: /intel and /api/arxiv/*. All ArxivCast logic lives in core; routes delegate and serve generated HTML."""

import json
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


@arxvicast_bp.route("/api/arxiv/voice/status", methods=["GET"])
def voice_status():
    """Report availability of STT, LLM, TTS for fallback messaging (config-based, no heavy model load)."""
    try:
        from . import voice_config as vc
        try:
            import faster_whisper
            stt_ok = True
        except ImportError:
            stt_ok = False
        llm_ok = vc.VOICE_LLM_PROVIDER in ("ollama", "openrouter", "nvidia_nim", "nvidia-nim")
        if vc.VOICE_LLM_PROVIDER == "openrouter":
            llm_ok = bool(vc.OPENROUTER_KEY)
        elif "nim" in (vc.VOICE_LLM_PROVIDER or ""):
            llm_ok = bool(vc.NIM_CHAT_URL)
        tts_ok = bool(vc.get_piper_voice_path())
        try:
            import piper
            tts_ok = tts_ok and True
        except ImportError:
            tts_ok = False
        return jsonify({
            "stt": stt_ok,
            "llm": llm_ok,
            "tts": tts_ok,
            "message": None if (stt_ok and llm_ok and tts_ok) else "One or more voice services need setup. See docs/VOICE_SETUP.md.",
        })
    except Exception as e:
        return jsonify({"stt": False, "llm": False, "tts": False, "message": str(e)})


@arxvicast_bp.route("/api/arxiv/voice/turn", methods=["POST"])
def voice_turn():
    """Stream one voice turn: audio (base64) -> STT -> LLM stream -> TTS stream. Chunked NDJSON."""
    data = request.get_json(force=True, silent=True) or {}
    audio_b64 = data.get("audio")
    paper_ids = data.get("paper_ids")
    if isinstance(paper_ids, list):
        paper_ids = [str(p).strip() for p in paper_ids if str(p).strip()]
    else:
        paper_ids = None
    conversation_history = data.get("conversation_history") or []

    if not audio_b64:
        return jsonify({"error": "Missing audio"}), 400

    from . import voice_pipeline

    def generate():
        for event in voice_pipeline.run_voice_turn(
            audio_b64=audio_b64,
            paper_ids=paper_ids,
            conversation_history=conversation_history,
        ):
            yield json.dumps(event) + "\n"

    return Response(
        generate(),
        mimetype="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
