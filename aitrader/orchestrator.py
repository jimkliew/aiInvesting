"""The orchestrator: a plain state machine, not a model (practice P14).

campaign -> seasons -> phases: data, research, select, trade, score, review, apply.
Budgets end loops; Controls allow pause, step and stop between agent turns.
"""
from __future__ import annotations

import threading
import traceback
from pathlib import Path

import pandas as pd

from . import levers
from .agents.coder_agent import write_code
from .agents.critic_agent import review as critic_review
from .agents.data_agent import run_data_agent
from .agents.idea_agent import propose
from .agents.review_agent import ReviewPacket, best_worst, coach
from .agents.trader_agent import decide
from .backtest.lookahead import lookahead_check
from .backtest.engine import at_cadence
from .backtest.metrics import metrics
from .backtest.sandbox import Rejected, check_source, run_strategy
from .backtest.scorer import score_season, window_metrics
from .backtest.selector import select
from .backtest.strategies import BASELINES, tradeable
from .config import Universe
from .data.features import feature_catalog, slice_to, snapshot
from .events import EventBus
from .llm import AgentError, Budget, BudgetExceeded
from .seasons import Season, calendar, rebalance_dates, trim_to_data
from .store import RunStore

PHASES = ["data", "research", "select", "trade", "score", "review", "apply"]


class Stopped(Exception):
    pass


class Controls:
    """pause/resume/step/stop, checked between agent turns."""

    def __init__(self):
        self._paused = threading.Event()
        self._step = threading.Event()
        self._stop = threading.Event()

    def pause(self): self._paused.set()
    def resume(self): self._paused.clear(); self._step.set()
    def step(self): self._paused.set(); self._step.set()
    def stop(self): self._stop.set(); self._step.set()

    @property
    def paused(self) -> bool: return self._paused.is_set()
    @property
    def stopped(self) -> bool: return self._stop.is_set()

    def checkpoint(self) -> None:
        if self._stop.is_set():
            raise Stopped()
        if self._paused.is_set():
            self._step.wait()
            self._step.clear()
            if self._stop.is_set():
                raise Stopped()


class Orchestrator:
    def __init__(self, universe: Universe, store: RunStore, llm, bus: EventBus, controls: Controls | None = None,
                 personas: list[str] | None = None, apply_mode: str = "auto", quick: bool = False,
                 data_dir: str | Path = "data", use_llm_data: bool = True):
        self.u = universe
        self.store = store
        self.llm = llm
        self.bus = bus
        self.controls = controls or Controls()
        self.personas = personas or ["momentum"]
        self.apply_mode = apply_mode
        self.quick = quick
        self.data_dir = Path(data_dir)
        self.use_llm_data = use_llm_data
        self.prices: pd.DataFrame | None = None
        self.features: dict[str, pd.DataFrame] | None = None
        self.budget = Budget(store.params["budget.max_llm_calls"], store.params["budget.max_minutes"])
        if llm is not None:
            llm.budget = self.budget
        self.current_phase: str | None = None
        self.current_season: Season | None = None
        self.last_error: str | None = None

    # ---- helpers ----
    def emit(self, kind: str, **payload):
        return self.bus.emit(kind, **payload)

    def phase(self, name: str):
        self.current_phase = name
        self.bus.set_context(phase=name, agent=None)
        self.emit("phase", text=f"Phase: {name}", name=name)

    def agent(self, name: str | None):
        self.bus.set_context(agent=name)

    @property
    def p(self):
        return self.store.params

    # ---- campaign ----
    def run_campaign(self, n_seasons: int | None = None) -> None:
        n = n_seasons or self.u.seasons
        self.bus.set_context(campaign=self.store.id)
        self.store.save_meta(universe=self.u.to_dict(), model=getattr(self.llm, "model", None), personas=self.personas,
                             apply_mode=self.apply_mode, quick=self.quick, seasons=n, params_at_start=dict(self.p))
        self.store.save_params()
        self.emit("campaign_started", text=f"Campaign {self.store.id}: {n} seasons from {self.u.campaign_start}, "
                                           f"{len(self.u.tickers)} tickers, model {getattr(self.llm, 'model', 'none')}",
                  seasons=n, universe=self.u.to_dict())
        try:
            self.ensure_data()
            done = set(self.store.seasons_done())
            last = self.prices.index.max()
            for season in calendar(self.u.campaign_start, n, self.u.start):
                if season.n in done:
                    self.emit("season_skipped", text=f"Season {season.n} already scored, resuming after it", season=season.n)
                    continue
                if season.start > last:
                    self.emit("season_unavailable", text=f"Season {season.n} ({season.label}) starts after the last data date {last.date()}; stopping",
                              season=season.n)
                    break
                self.run_season(trim_to_data(season, last))
                if self.controls.stopped:
                    break
            self.emit("campaign_done", text="Campaign finished", stopped=self.controls.stopped)
        except Stopped:
            self.emit("stopped", text="Stopped by the operator")
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            self.emit("campaign_error", text=f"Campaign error: {self.last_error}", trace=traceback.format_exc()[-2000:])
            raise
        finally:
            self.bus.set_context(season=None, phase=None, agent=None)

    # ---- data ----
    def ensure_data(self) -> None:
        if self.prices is not None:
            return
        self.bus.set_context(season=None)
        self.phase("data")
        self.agent("data")
        res = run_data_agent(self.llm, self.u, self.bus, self.data_dir, use_llm=self.use_llm_data and self.llm is not None)
        self.prices, self.features = res.prices, res.features
        if sorted(res.tickers) != sorted(self.u.tickers):
            self.emit("universe_changed", text=f"Universe after the data phase: {', '.join(res.tickers)} (brief had {', '.join(self.u.tickers)})",
                      before=self.u.tickers, after=res.tickers)
        self.u.tickers = list(res.tickers)
        self.store.save_meta(universe=self.u.to_dict(), data_report=res.report, data_sha256=res.manifest.get("sha256"))
        self.agent(None)

    # ---- season ----
    def run_season(self, season: Season) -> None:
        self.current_season = season
        self.bus.set_context(season=season.n)
        self.budget.reset()
        self.store.season_dir(season.n)
        self.emit("season_started", text=f"Season {season.n}, {season.label}: {season.start.date()} to {season.end.date()}"
                                         + (" (partial, up to the last available day)" if season.partial else ""),
                  **season.to_dict())
        steps = [("research", self.research), ("select", self.select_book), ("trade", self.trade),
                 ("score", self.score), ("review", self.review), ("apply", self.apply)]
        state: dict = {}
        for name, fn in steps:
            self.phase(name)
            try:
                fn(season, state)
            except BudgetExceeded as e:
                self.emit("budget_exceeded", text=f"Budget hit during {name}: {e}. Continuing with what we have.", phase=name)
            except Stopped:
                raise
            except AgentError as e:
                self.emit("agent_error", text=f"Agent error during {name}: {e}", error=str(e), phase=name)
            finally:
                self.agent(None)
        self.emit("season_done", text=f"Season {season.n} complete", season=season.n)

    # ---- research ----
    def _visible(self, season: Season):
        end = season.visible_end
        return self.prices.loc[:end], slice_to(self.features, end)

    def research(self, season: Season, state: dict) -> None:
        vis_prices, vis_feats = self._visible(season)
        rounds = int(self.p["research.rounds"]) + (1 if season.n == 1 and not self.quick else 0)
        k = 1 if self.quick else int(self.p["research.ideas_per_round"])
        max_strats = 2 if self.quick else int(self.p["budget.max_strategies"])
        catalog = feature_catalog()
        tried = 0
        names = {e["name"] for e in self.store.notebook()}
        for rnd in range(1, rounds + 1):
            self.controls.checkpoint()
            self.agent("idea")
            hyps = propose(self.llm, k, catalog, self.store.notebook_summary(), self.p.get("family_focus"),
                           self.store.lesson_texts("idea"), existing_names=names)
            self.emit("hypotheses", text=f"Round {rnd}: {len(hyps)} hypotheses: " + ", ".join(f"{h.name} ({h.family})" for h in hyps),
                      round=rnd, items=[h.model_dump() for h in hyps])
            for hyp in hyps:
                names.add(hyp.name)
                self.controls.checkpoint()
                code, full_w, feedback = None, None, None
                m_train = m_val = None
                max_turn = float(self.p["selector.max_turnover"])
                for attempt in range(1, 4):
                    self.agent("coder")
                    sc = write_code(self.llm, hyp, catalog, feedback=feedback, lessons=self.store.lesson_texts("coder"))
                    code = sc.code
                    self.emit("code", text=f"{hyp.name}, attempt {attempt}: {len(code.splitlines())} lines", name=hyp.name,
                              attempt=attempt, code=code, notes=sc.notes)
                    self.agent("sandbox")
                    try:
                        check_source(code)
                        ok, msg, full_w = lookahead_check(code, vis_prices, vis_feats)
                    except Rejected as e:
                        feedback = str(e)
                        if "KeyError" in feedback:
                            feedback += (". Only these feature keys exist: " + ", ".join(sorted(vis_feats)) +
                                         ". Compute anything else yourself from prices or features['ret_1d'].")
                        self.emit("sandbox_rejected", text=f"Rejected: {feedback}. Sent back to the Coder Agent.", name=hyp.name, error=feedback)
                        continue
                    if not ok:
                        feedback = msg
                        self.emit("lookahead_failed", text=f"Lookahead test failed: {msg}", name=hyp.name, error=msg)
                        continue
                    full_w = at_cadence(full_w, self.p.get("book.rebalance", "weekly"))
                    window = full_w.loc[season.train[0]:season.visible_end]
                    exposure = float(window.sum(axis=1).mean()) if len(window) else 0.0
                    days_held = float((window.sum(axis=1) > 0).mean()) if len(window) else 0.0
                    if exposure < 0.02 or days_held < 0.05:
                        feedback = (f"the strategy holds nothing: average exposure {exposure:.1%}, invested on {days_held:.0%} of days. "
                                    f"Check that your entry condition is ever true and that the normalisation does not divide by zero.")
                        self.emit("sandbox_rejected", text=f"Rejected: {feedback}", name=hyp.name, error=feedback)
                        continue
                    self.emit("sandbox_ok", text=f"Compiled, no imports or file access. Lookahead test passed: {msg}. "
                                                 f"Average exposure {exposure:.0%}, invested on {days_held:.0%} of days.", name=hyp.name)
                    self.agent("engine")
                    m_train = window_metrics(full_w, vis_prices, *season.train, self.u.cost_bps)
                    m_val = window_metrics(full_w, vis_prices, *season.validation, self.u.cost_bps)
                    self.emit("backtest", text=f"Backtest {hyp.name}: train Sharpe {m_train.sharpe:.2f}, validation Sharpe {m_val.sharpe:.2f}, "
                                              f"turnover {m_val.turnover * 100:.0f}%/yr, max drawdown {m_val.max_dd * 100:.1f}%",
                              name=hyp.name, train=m_train.model_dump(), val=m_val.model_dump())
                    if m_val.turnover * 100 > max_turn and attempt < 3:
                        feedback = (f"validation turnover is {m_val.turnover * 100:.0f}% per year; the limit is {max_turn:.0f}%. "
                                    f"Trade less often: require the condition to hold for several days, add hysteresis between entry and exit, "
                                    f"or rebalance monthly. Keep the same idea.")
                        self.emit("turnover_feedback", text=f"Too much turnover ({m_val.turnover * 100:.0f}%/yr vs {max_turn:.0f}% limit); asking the Coder to slow it down",
                                  name=hyp.name, turnover=m_val.turnover)
                        continue
                    break
                else:
                    self.store.notebook_add({"name": hyp.name, "family": hyp.family, "idea": hyp.idea, "season": season.n,
                                             "status": "failed", "error": feedback, "code": code})
                    self.emit("strategy_failed", text=f"{hyp.name} failed after 3 attempts: {feedback}", name=hyp.name)
                    tried += 1
                    continue
                if m_val is None:
                    continue
                self.controls.checkpoint()
                self.agent("critic")
                rv = critic_review(self.llm, code, m_train, m_val, self.store.notebook_summary(), self.store.lesson_texts("critic"),
                                   float(self.p["critic.min_val_sharpe"]), float(self.p["selector.max_turnover"]))
                status = "kept" if rv.verdict == "KEEP" else "discarded"
                self.emit("critic", text=f"{rv.verdict}: {hyp.name}. " + ("; ".join(rv.concerns) or "no concerns") +
                                         (f". Suggestion: {rv.suggestion}" if rv.suggestion else ""),
                          name=hyp.name, verdict=rv.verdict, concerns=rv.concerns, suggestion=rv.suggestion)
                self.store.notebook_add({"name": hyp.name, "family": hyp.family, "idea": hyp.idea, "season": season.n,
                                         "status": status, "code": code, "train": m_train.model_dump(), "val": m_val.model_dump(),
                                         "review": rv.model_dump(), "features_used": hyp.features_used})
                tried += 1
                if tried >= max_strats:
                    self.emit("budget_strategies", text=f"Strategy budget of {max_strats} reached for this season")
                    return

    # ---- select ----
    def select_book(self, season: Season, state: dict) -> None:
        vis_prices, vis_feats = self._visible(season)
        self.agent("selector")
        candidates = []
        for e in self.store.kept():
            if not e.get("code"):
                continue
            try:
                w = at_cadence(run_strategy(e["code"], vis_prices, vis_feats), self.p.get("book.rebalance", "weekly"))
            except Rejected as ex:
                self.emit("candidate_skipped", text=f"{e['name']} could not run on the current data: {ex}", name=e["name"])
                continue
            m_val = window_metrics(w, vis_prices, *season.validation, self.u.cost_bps)
            candidates.append({**e, "val": m_val.model_dump(), "weights": w})
        # classic baselines compete too: the book is the best validated rule available to the team
        for bname, fn in BASELINES.items():
            if bname == "buy_hold_spy":
                continue
            try:
                w = at_cadence(fn(vis_prices, vis_feats).fillna(0.0), self.p.get("book.rebalance", "weekly"))
                m_val = window_metrics(w, vis_prices, *season.validation, self.u.cost_bps)
                candidates.append({"name": bname, "code": None, "baseline": True, "family": "baseline",
                                   "val": m_val.model_dump(), "weights": w})
            except Exception as ex:
                self.emit("candidate_skipped", text=f"baseline {bname} failed: {ex}", name=bname)
        prev = self.store.quant_book(season.n - 1) if season.n > 1 else None
        best, fallback = select(candidates, self.p, prev)
        if best is None:
            name, code = "equal_weight", None
            val_sharpe = None
            self.emit("selector_fallback", text="No strategy qualified on validation; the quant book falls back to equal weight", fallback="equal_weight")
        else:
            name, code = best["name"], best.get("code")
            val_sharpe = (best.get("val") or {}).get("sharpe")
            if fallback:
                self.emit("selector_fallback", text=f"No strategy qualified; keeping last season's book {name}", fallback=name)
            elif best.get("baseline"):
                self.emit("selector_note", text=f"A classic baseline beat the researched strategies on validation this season: {name}", name=name)
        self.store.set_quant_book(season.n, name, code or "", val_sharpe, fallback)
        state["book"] = {"name": name, "code": code, "val_sharpe": val_sharpe, "fallback": fallback}
        ranked = sorted(candidates, key=lambda c: c["val"]["sharpe"], reverse=True)
        self.emit("book_selected", text=f"Quant book for season {season.n}: {name}" +
                                        (f", validation Sharpe {val_sharpe:.2f}" if val_sharpe is not None else "") +
                                        (f". Runner-up {ranked[1]['name']} ({ranked[1]['val']['sharpe']:.2f})" if len(ranked) > 1 else "") +
                                        ". Chosen on validation only.",
                  name=name, val_sharpe=val_sharpe, fallback=fallback,
                  candidates=[{"name": c["name"], "val_sharpe": c["val"]["sharpe"], "val_turnover": c["val"]["turnover"],
                               "baseline": bool(c.get("baseline"))} for c in ranked])

    # ---- trade ----
    def trade(self, season: Season, state: dict) -> None:
        book = state.get("book") or (self.store.quant_book(season.n) or {"name": "equal_weight", "code": None})
        prices_to_end = self.prices.loc[:season.end]
        feats_to_end = slice_to(self.features, season.end)
        self.agent("engine")
        if book.get("code"):
            book_w = run_strategy(book["code"], prices_to_end, feats_to_end)
        else:
            book_w = BASELINES.get(book["name"], BASELINES["equal_weight"])(prices_to_end, feats_to_end).fillna(0.0)
        book_w = at_cadence(book_w, self.p.get("book.rebalance", "weekly"))
        self.store.save_weights(season.n, "book_weights", book_w.loc[season.start - pd.Timedelta(days=10):])
        self.emit("book_trading", text=f"Season opens {season.start.date()}. Quant book {book['name']} trades mechanically from its weights, rebalanced {self.p.get('book.rebalance', 'weekly')}.",
                  name=book["name"])

        cols = tradeable(self.prices)
        max_w = float(self.p["desk.max_weight"])
        prev = self.store.weights(season.n - 1, "desk_weights") if season.n > 1 else None
        current = {t: 0.0 for t in cols}
        if prev is not None and len(prev):
            last = prev.iloc[-1]
            current = {t: float(last.get(t, 0.0)) for t in cols}
        desk_w = pd.DataFrame(0.0, index=prices_to_end.index, columns=self.prices.columns)
        dates = rebalance_dates(self.prices.index, season.start, season.end, self.p["desk.rebalance"])
        if self.quick:
            dates = dates[:4]
        self.emit("desk_open", text=f"Desk: {len(dates)} rebalance dates, personas {', '.join(self.personas)}, max weight {max_w:.2f}. "
                                    f"Starting weights: " + ", ".join(f"{t} {w:.2f}" for t, w in current.items() if w > 0) + ".",
                  dates=[str(d.date()) for d in dates], personas=self.personas)
        decisions_rows: list[dict] = []
        for i, d in enumerate(dates, 1):
            week_targets: dict[str, list[float]] = {t: [] for t in cols}
            for t in cols:
                if prices_to_end.loc[:d, t].dropna().empty:
                    continue
                snap = snapshot(prices_to_end, feats_to_end, t, d, current[t], max_w)
                for persona in self.personas:
                    self.controls.checkpoint()
                    self.agent(f"trader_{persona}")
                    dec = decide(self.llm, persona, snap, self.store.lesson_texts(f"trader_{persona}"), max_w, current[t])
                    week_targets[t].append(dec.target_weight)
                    row = {"season": season.n, "week": i, "date": str(d.date()), "ticker": t, "persona": persona,
                           "action": dec.action, "from_weight": round(current[t], 4), "target_weight": dec.target_weight,
                           "confidence": dec.confidence, "reason": dec.reason, "snapshot": snap}
                    decisions_rows.append(row)
                    self.emit("decision", text=f"Week {i}, {d.date()}. {t} {dec.action} {current[t]:.2f} -> {dec.target_weight:.2f}, "
                                               f"confidence {dec.confidence:.2f}. {dec.reason}", **{k: v for k, v in row.items() if k != "snapshot"})
            self.agent("engine")
            for t in cols:
                if week_targets[t]:
                    current[t] = sum(week_targets[t]) / len(week_targets[t])
            total = sum(current.values())
            if total > 1.0:
                current = {t: w / total for t, w in current.items()}
            row_vec = pd.Series(0.0, index=self.prices.columns)
            for t, w in current.items():
                row_vec[t] = w
            desk_w.loc[d:, :] = row_vec.values
            nxt = prices_to_end.index[prices_to_end.index > d]
            fill = nxt[0].date() if len(nxt) else d.date()
            held = {t: w for t, w in current.items() if w > 0}
            self.emit("fill", text=f"Filled at the {fill} open. Portfolio: {len(held)} positions, cash {max(0.0, 1 - sum(current.values())) * 100:.0f}%.",
                      date=str(fill), weights={t: round(w, 4) for t, w in held.items()})
        # one-month outcomes for the coach
        for row in decisions_rows:
            d = pd.Timestamp(row["date"])
            px = prices_to_end[row["ticker"]].dropna()
            after = px.loc[px.index > d]
            if len(after) >= 2:
                horizon = after.iloc[min(21, len(after) - 1)]
                row["outcome_1m"] = round(float(horizon / after.iloc[0] - 1), 6)
            else:
                row["outcome_1m"] = None
            self.store.add_decision(season.n, row)
        self.store.save_weights(season.n, "desk_weights", desk_w.loc[season.start - pd.Timedelta(days=10):])
        state["book_w"], state["desk_w"] = book_w, desk_w

    # ---- score ----
    def score(self, season: Season, state: dict) -> None:
        self.agent("scorer")
        book_w = state.get("book_w")
        desk_w = state.get("desk_w")
        if book_w is None:
            book_w = self.store.weights(season.n, "book_weights")
        if desk_w is None:
            desk_w = self.store.weights(season.n, "desk_weights")
        if book_w is None or desk_w is None:
            self.emit("score_skipped", text="Nothing to score: trading did not complete")
            return
        info = self.store.quant_book(season.n) or {}
        sc = score_season(self.prices, self.features, season, book_w, desk_w, self.u.cost_bps, self.u.benchmark, info)
        self.store.save_scorecard(season.n, sc)
        self.store.append_track_record({
            "season": season.n, "label": season.label, "partial": sc["partial"],
            "team": sc["team"]["total_return"], "book": sc["book"]["total_return"], "desk": sc["desk"]["total_return"],
            "spy": sc["spy"]["total_return"], "team_sharpe": sc["team"]["sharpe"], "book_name": sc["book_name"],
            "book_val_sharpe": sc["book_val_sharpe"], "book_season_sharpe": sc["book"]["sharpe"],
            "max_dd": sc["team"]["max_dd"], "llm_calls": self.budget.calls,
        })
        self.emit("season_scored", text=f"Season {season.n} scored: team {sc['team']['total_return'] * 100:+.1f}%, "
                                        f"book {sc['book']['total_return'] * 100:+.1f}%, desk {sc['desk']['total_return'] * 100:+.1f}%, "
                                        f"SPY {sc['spy']['total_return'] * 100:+.1f}%",
                  team=sc["team"], book=sc["book"], desk=sc["desk"], spy=sc["spy"], partial=sc["partial"])

    # ---- review ----
    def review(self, season: Season, state: dict) -> None:
        sc = self.store.scorecard(season.n)
        if sc is None:
            self.emit("review_skipped", text="No scorecard; skipping the review")
            return
        self.controls.checkpoint()
        self.agent("review")
        packet = ReviewPacket(season.label, sc, self.store.track_record(), self.store.changelog(),
                              self.store.notebook_summary(), best_worst(self.store.decisions(season.n)), self.store.all_lessons(),
                              personas=list(self.personas))
        rv = coach(self.llm, packet)
        self.store.save_review(season.n, {**rv.model_dump(), "packet": packet.as_text()})
        state["review"] = rv
        self.emit("review", text=f"Coach: {rv.assessment} Worked: {rv.what_worked} Failed: {rv.what_failed} "
                                 f"({len(rv.recommendations)} recommendations)",
                  assessment=rv.assessment, what_worked=rv.what_worked, what_failed=rv.what_failed,
                  recommendations=[r.model_dump() for r in rv.recommendations])

    # ---- apply ----
    def apply(self, season: Season, state: dict) -> None:
        rv = state.get("review")
        if rv is None:
            return
        self.agent("orchestrator")
        if self.apply_mode == "approve":
            pending = self.store.pending()
            for r in rv.recommendations:
                pending.append({"season": season.n, "status": "pending", **r.model_dump()})
            self.store.save_pending(pending)
            self.emit("pending_recommendations", text=f"{len(rv.recommendations)} recommendations wait for your Accept or Reject",
                      count=len(rv.recommendations))
            return
        for r in rv.recommendations:
            try:
                change = levers.apply(self.store, r, season=season.n)
                self.emit("change_applied", text=f"Change {change['id']}: {change['lever']} {change['target']} -> {str(change['change'])[:160]}. "
                                                 f"Because: {r.rationale}", **{k: v for k, v in change.items() if k != "detail"})
            except levers.InvalidLever as e:
                self.emit("invalid_recommendation", text=f"Rejected recommendation ({r.lever} {r.target}): {e}", lever=r.lever,
                          target=r.target, error=str(e))
