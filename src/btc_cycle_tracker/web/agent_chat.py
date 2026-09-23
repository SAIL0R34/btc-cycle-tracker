"""Conversational agent for the BTC tracker's agent pane.

Ported from the opportunity_pipeline agent stack: a small JSON tool-calling
loop over an OpenAI-compatible LLM (no native tool-calling required, which
local vLLM setups don't always expose):

    user turn
      -> model emits {"action": "call", "tool": ..., "args": ...}   (read tool)
      -> tool runs, observation fed back, loop continues
      -> model emits {"action": "propose", "tool": ..., ...}         (write tool)
      -> loop stops and returns a confirmation request to the UI
      -> user confirms -> write executes -> loop resumes -> final answer
      -> model emits {"action": "final", "message": ...}             (answer)

Write tools (anything that runs the pipeline, changes config, or writes
files) are never executed until the user confirms them in the UI.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from btc_cycle_tracker.models import PivotMethod, Timeframe
from btc_cycle_tracker.web import agent_db
from btc_cycle_tracker.web.llm import LLMClient, extract_json_from_response
from btc_cycle_tracker.web.serializers import build_insight_context
from btc_cycle_tracker.web.state import AppState

logger = logging.getLogger("btc_cycle_tracker.web.agent_chat")

MAX_STEPS = 5
_OBS_CHARS = 6000  # retain enough evidence for comparisons without unbounded prompts


@dataclass
class ChatContext:
    llm: LLMClient
    state: AppState


def _ok(**data) -> dict:
    return {"ok": True, **data}


def _err(message: str) -> dict:
    return {"ok": False, "error": message}


def _short(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= 240 else text[:240] + "…"


_CALL_VERB = {
    "get_overview": "Reading the current analysis",
    "list_legs": "Scanning swing legs",
    "list_pivots": "Scanning pivot points",
    "get_insights": "Reviewing pattern & correlation insights",
    "get_structure_discoveries": "Reviewing detected market structures",
    "get_config": "Checking the configuration",
}


def _describe_call(name: str, args: dict) -> str:
    base = _CALL_VERB.get(name, f"Running {name}")
    hint = args.get("direction") or args.get("sort") or args.get("symbol") or args.get("timeframe")
    return base + (f" — {str(hint)[:60]}" if hint else "…")


def _describe_result(name: str, result: dict) -> str:
    if not result.get("ok", True):
        return f"{name} hit a problem: {result.get('error', 'unknown')}"
    if "legs" in result:
        return f"Found {result.get('count', 0)} leg(s)"
    if "pivots" in result:
        return f"Found {result.get('count', 0)} pivot(s)"
    if "metadata" in result or "summary" in result:
        return "Loaded the current analysis"
    if "config" in result:
        return "Loaded the configuration"
    if "files" in result:
        return f"Exported {len(result.get('files', {}))} file(s)"
    return "Done"


# ---------------------------------------------------------------------------
# READ tools (auto-executed)
# ---------------------------------------------------------------------------

def _tool_get_overview(args: dict, ctx: ChatContext) -> dict:
    context = build_insight_context(ctx.state.result, ctx.state.config)
    if ctx.state.result is None:
        return _ok(state="no analysis yet", **context)
    return _ok(**context)


def _sorted_legs(legs, sort: str):
    if sort == "biggest":
        return sorted(legs, key=lambda x: abs(x.percent_change), reverse=True)
    if sort == "longest":
        return sorted(legs, key=lambda x: x.duration_minutes, reverse=True)
    return list(reversed(legs))  # newest first


def _tool_list_legs(args: dict, ctx: ChatContext) -> dict:
    result = ctx.state.result
    if result is None:
        return _err("No analysis has been run yet — propose run_analysis first.")
    legs = result.legs
    direction = (args.get("direction") or "").strip().lower()
    if direction in ("up", "down"):
        legs = [leg for leg in legs if leg.direction == direction]
    legs = _sorted_legs(legs, (args.get("sort") or "newest").strip().lower())
    limit = min(int(args.get("limit", 10) or 10), 40)
    trimmed = [
        {
            "leg_id": leg.leg_id,
            "direction": leg.direction,
            "pct": round(leg.percent_change, 2),
            "minutes": round(leg.duration_minutes, 1),
            "bars": leg.duration_bars,
            "from": leg.start_timestamp.isoformat(),
            "to": leg.end_timestamp.isoformat(),
            "start_price": leg.start_price,
            "end_price": leg.end_price,
        }
        for leg in legs[:limit]
    ]
    return _ok(count=len(trimmed), total=len(result.legs), legs=trimmed)


def _tool_list_pivots(args: dict, ctx: ChatContext) -> dict:
    result = ctx.state.result
    if result is None:
        return _err("No analysis has been run yet — propose run_analysis first.")
    pivots = list(reversed(result.pivots))
    limit = min(int(args.get("limit", 10) or 10), 40)
    trimmed = [
        {
            "timestamp": p.timestamp.isoformat(),
            "price": p.price,
            "type": p.pivot_type.value,
        }
        for p in pivots[:limit]
    ]
    return _ok(count=len(trimmed), total=len(result.pivots), pivots=trimmed)


def _tool_get_insights(args: dict, ctx: ChatContext) -> dict:
    result = ctx.state.result
    if result is None:
        return _err("No analysis has been run yet — propose run_analysis first.")
    out: dict[str, Any] = {}
    if result.pattern_insight:
        out["pattern"] = result.pattern_insight.model_dump(mode="json")
    if result.pattern_learning:
        out["pattern_learning"] = result.pattern_learning.model_dump(mode="json")
    if result.moon_phase_insight:
        out["moon_phase"] = result.moon_phase_insight.model_dump(mode="json")
    for name, insight in (
        ("gold", result.gold_correlation_insight),
        ("nasdaq", result.nasdaq_correlation_insight),
        ("oil", result.oil_correlation_insight),
    ):
        if insight is not None:
            out[f"{name}_correlation"] = insight.model_dump(mode="json")
    if not out:
        return _ok(note="No optional insights are enabled. Pattern recognition / moon phase / correlations can be turned on via update_config.")
    return _ok(**out)


def _tool_get_decision(args: dict, ctx: ChatContext) -> dict:
    result = ctx.state.result
    if result is None:
        return _err("No analysis has been run yet — propose run_analysis first.")
    if result.decision_brief is None:
        return _err("Decision engine is disabled — enable_decision_engine=true via update_config, then re-run.")
    return _ok(decision=result.decision_brief.model_dump(mode="json"))


def _tool_get_config(args: dict, ctx: ChatContext) -> dict:
    return _ok(config=ctx.state.config.model_dump(mode="json"))


def _tool_get_structure_discoveries(args: dict, ctx: ChatContext) -> dict:
    if ctx.state.result is None:
        return _err("No analysis has been run yet — propose run_analysis first.")
    discoveries = ctx.state.result.structure_discoveries
    kind = str(args.get("type") or "").strip().lower()
    if kind:
        discoveries = [item for item in discoveries if item.structure_type == kind]
    return _ok(
        count=len(discoveries),
        discoveries=[item.model_dump(mode="json") for item in discoveries[:20]],
    )


# ---------------------------------------------------------------------------
# WRITE tools (only run after user confirmation)
# ---------------------------------------------------------------------------

_TIMEFRAMES = [t.value for t in Timeframe]
_METHODS = [m.value for m in PivotMethod]


def _tool_run_analysis(args: dict, ctx: ChatContext) -> dict:
    timeframe = (args.get("timeframe") or "").strip() or None
    if timeframe and timeframe not in _TIMEFRAMES:
        return _err(f"Invalid timeframe. Use one of: {', '.join(_TIMEFRAMES)}")
    lookback = (args.get("lookback") or "").strip() or None
    symbol = (args.get("symbol") or "").strip() or None
    try:
        result = ctx.state.run_analysis_sync(symbol=symbol, timeframe=timeframe, lookback=lookback)
    except Exception as exc:  # noqa: BLE001 - surface as tool error to the model
        return _err(f"Analysis failed: {exc}")
    meta = result.metadata
    return _ok(
        symbol=meta.symbol,
        timeframe=meta.timeframe,
        candles=meta.total_candles,
        pivots=meta.total_pivots,
        legs=meta.total_legs,
        note="Analysis complete; the dashboard now shows this run.",
    )


def _tool_update_config(args: dict, ctx: ChatContext) -> dict:
    if not args:
        return _err("Provide at least one config field to change.")
    if "timeframe" in args and args["timeframe"] not in _TIMEFRAMES:
        return _err(f"Invalid timeframe. Use one of: {', '.join(_TIMEFRAMES)}")
    if "pivot_method" in args and args["pivot_method"] not in _METHODS:
        return _err(f"Invalid pivot_method. Use one of: {', '.join(_METHODS)}")
    try:
        config = ctx.state.update_config(dict(args))
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))
    return _ok(
        updated=dict(args),
        config={"symbol": config.symbol, "timeframe": config.timeframe.value,
                "pivot_method": config.pivot_method.value, "min_move_pct": config.min_move_pct},
        note="Config updated. Re-run the analysis for it to take effect on the chart.",
    )


def _tool_export_data(args: dict, ctx: ChatContext) -> dict:
    try:
        files = ctx.state.export_current()
    except Exception as exc:  # noqa: BLE001
        return _err(str(exc))
    return _ok(files=files, note="Files written under the outputs/ directory.")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

@dataclass
class Tool:
    name: str
    func: Callable[[dict, ChatContext], dict]
    write: bool
    doc: str


TOOLS: dict[str, Tool] = {t.name: t for t in [
    Tool("get_overview", _tool_get_overview, False,
         "get_overview() — current analysis snapshot: config, window, KPIs, recent legs, pattern bias."),
    Tool("list_legs", _tool_list_legs, False,
         "list_legs(limit?, direction?, sort?) — swing legs. direction: up/down. sort: newest/biggest/longest."),
    Tool("list_pivots", _tool_list_pivots, False,
         "list_pivots(limit?) — most recent confirmed swing highs/lows."),
    Tool("get_insights", _tool_get_insights, False,
         "get_insights() — pattern recognition, pattern learning, moon phase, and cross-asset correlation details."),
    Tool("get_config", _tool_get_config, False,
         "get_config() — the full current configuration."),
    Tool("get_structure_discoveries", _tool_get_structure_discoveries, False,
         "get_structure_discoveries(type?) — ranked trend/range, break/change, support and resistance discoveries with evidence, anchors, confidence, and invalidation."),
    Tool("get_decision", _tool_get_decision, False,
         "get_decision() — the auditable decision brief: action band, composite score, conviction, weighted evidence contributions, invalidation levels, and walk-forward replay stats."),
    Tool("run_analysis", _tool_run_analysis, True,
         f"run_analysis(symbol?, timeframe?, lookback?) — fetch fresh data and run the full pipeline. timeframe one of {'/'.join(_TIMEFRAMES)}; lookback like 30d/12w/6m/1y."),
    Tool("update_config", _tool_update_config, True,
         "update_config(<field>=<value>, ...) — change settings, e.g. pivot_method (zigzag/fractal/fixed_window), min_move_pct, left_bars, right_bars, use_atr_filter, atr_period, atr_multiplier, enable_pattern_recognition, pattern_length, enable_moon_phase_analysis, enable_gold_correlation_analysis, enable_nasdaq_correlation_analysis, enable_oil_correlation_analysis."),
    Tool("export_data", _tool_export_data, True,
         "export_data() — write the current result to CSV/JSON files in outputs/."),
]}


def _tools_doc() -> str:
    read = [t.doc for t in TOOLS.values() if not t.write]
    write = [t.doc for t in TOOLS.values() if t.write]
    return (
        "READ tools (run immediately):\n- " + "\n- ".join(read)
        + "\n\nWRITE tools (require user confirmation before they run):\n- " + "\n- ".join(write)
    )


# ---------------------------------------------------------------------------
# Prompt + loop
# ---------------------------------------------------------------------------

def _system_prompt() -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"""You are the assistant inside a BTC swing-cycle analysis dashboard.
Today is {today} (UTC). You help the user read pivots, swing legs, cycle statistics and
pattern insights, re-run the analysis with different settings, and export data.
You are not a financial advisor; never present analysis as trading advice.

You have these tools:
{_tools_doc()}

On each step respond with a SINGLE JSON object and nothing else. Choose one:
  {{"action":"call","tool":"<read_tool>","args":{{...}}}}      to gather information
  {{"action":"propose","tool":"<write_tool>","args":{{...}},"summary":"<one-line plain-English description of the change>"}}   to run/change/export
  {{"action":"final","message":"<your reply to the user>"}}     to answer

Rules:
- Use read tools first to ground yourself before answering. Start with get_overview if unsure.
- For interpretation questions, use market_intelligence as the primary evidence brief. Clearly distinguish observed recent structure from historical pattern evidence, mention conflicts, and calibrate language to its quality label.
- For structure discoveries, preserve each detector's exact status. Confidence is detector-evidence strength, not outcome probability. Call invalidation_price a "detector invalidation level"; never turn it into a candle-close, trade-entry, or stop rule unless the evidence explicitly says so.
- Never invent prices, dates, percentages or settings — look them up.
- For anything that runs the pipeline, changes settings, or writes files, use "propose"; it is shown to the user for confirmation. Do not assume it happened.
- Resolve relative dates (e.g. "this week") using today's date.
- Keep final messages concise and friendly, citing concrete values you retrieved."""


def _build_prompt(messages: list[dict], observations: list[dict]) -> str:
    convo = []
    for m in messages[-12:]:
        role = m.get("role", "user")
        convo.append(f"{role.upper()}: {m.get('content', '')}")
    obs_text = ""
    if observations:
        lines = []
        for o in observations:
            payload = json.dumps(o["result"], default=str)
            if len(payload) > _OBS_CHARS:
                payload = payload[:_OBS_CHARS] + "…"
            lines.append(f'- {o["tool"]}({json.dumps(o.get("args", {}))}) -> {payload}')
        obs_text = "\n\nTOOL RESULTS SO FAR:\n" + "\n".join(lines)
    return (
        _system_prompt()
        + "\n\nCONVERSATION:\n"
        + "\n".join(convo)
        + obs_text
        + "\n\nRespond with the next JSON object:"
    )


def _parse_decision(raw: str) -> dict:
    block = extract_json_from_response(raw, expected_keys={"action"})
    if block:
        try:
            data = json.loads(block)
            if isinstance(data, dict) and "action" in data:
                return data
        except json.JSONDecodeError:
            pass
    # Fallback: treat the raw text as a direct answer.
    return {"action": "final", "message": raw.strip()}


def _confirm_response(tool: str, args: dict, summary: str, trace: list) -> dict:
    return {
        "type": "confirm",
        "pending": {"tool": tool, "args": args, "summary": summary or f"Run {tool}"},
        "trace": trace,
    }


def run_chat(messages: list[dict], confirm: Optional[dict], ctx: ChatContext) -> dict:
    """Run one assistant turn. Returns a dict with type 'message' or 'confirm'."""
    observations: list[dict] = []
    trace: list[dict] = []

    if confirm:
        agent_db.emit_event("log", "▶ Continuing after your confirmation…")
    else:
        agent_db.emit_event("log", "💬 New request received…")

    # Execute a user-confirmed write first, then let the model wrap up.
    if confirm and confirm.get("tool") in TOOLS and TOOLS[confirm["tool"]].write:
        tool = TOOLS[confirm["tool"]]
        args = confirm.get("args", {}) or {}
        agent_db.emit_event("subtask_started", f"Applying: {tool.name}…")
        try:
            result = tool.func(args, ctx)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Write tool %s failed", tool.name)
            result = _err(str(exc))
        agent_db.emit_event(
            "subtask_completed" if result.get("ok", True) else "log",
            f"{'Applied' if result.get('ok', True) else 'Failed'}: {tool.name}",
        )
        observations.append({"tool": tool.name, "args": args, "result": result})
        trace.append({"tool": tool.name, "args": args, "result": _short(result), "kind": "write"})

    for _ in range(MAX_STEPS):
        raw = ctx.llm.generate(_build_prompt(messages, observations))
        decision = _parse_decision(raw)
        action = decision.get("action")

        if action in ("call", "propose"):
            name = decision.get("tool", "")
            args = decision.get("args", {}) or {}
            tool = TOOLS.get(name)
            if tool is None:
                observations.append({"tool": name, "args": args, "result": _err("unknown tool")})
                continue
            if tool.write:
                agent_db.emit_event("log", f"✍️ Proposing: {decision.get('summary') or name}")
                return _confirm_response(name, args, decision.get("summary", ""), trace)
            # read tool
            agent_db.emit_event("subtask_started", _describe_call(name, args))
            try:
                result = tool.func(args, ctx)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Read tool %s failed", name)
                result = _err(str(exc))
            agent_db.emit_event("subtask_completed", _describe_result(name, result))
            observations.append({"tool": name, "args": args, "result": result})
            trace.append({"tool": name, "args": args, "result": _short(result), "kind": "read"})
            continue

        # final (or unrecognized -> treated as final by _parse_decision)
        message = decision.get("message") or decision.get("final") or "Done."
        agent_db.emit_event("subtask_completed", "Replied")
        return {"type": "message", "content": message, "trace": trace}

    return {
        "type": "message",
        "content": "I couldn't finish that within a few steps — try narrowing the request.",
        "trace": trace,
    }
