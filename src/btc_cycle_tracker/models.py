"""Core data models for the BTC Swing Cycle Tracker."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Timeframe(str, Enum):
    """Supported timeframes for price data."""

    ONE_MINUTE = "1m"
    THREE_MINUTE = "3m"
    FIVE_MINUTE = "5m"
    FIFTEEN_MINUTE = "15m"
    THIRTY_MINUTE = "30m"
    ONE_HOUR = "1h"
    FOUR_HOUR = "4h"
    ONE_DAY = "1d"
    ONE_WEEK = "1w"


class PivotType(str, Enum):
    """Types of pivot points."""

    SWING_HIGH = "swing_high"
    SWING_LOW = "swing_low"


class PivotMethod(str, Enum):
    """Pivot detection methods."""

    ZIGZAG = "zigzag"
    FRACTAL = "fractal"
    FIXED_WINDOW = "fixed_window"


class OHLCV(BaseModel):
    """Represents a single candle/OHLCV data point."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @property
    def body(self) -> float:
        """Get the absolute body size of the candle."""
        return abs(self.close - self.open)

    @property
    def upper_wick(self) -> float:
        """Get the upper wick size."""
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        """Get the lower wick size."""
        return min(self.open, self.close) - self.low

    @property
    def total_range(self) -> float:
        """Get the total price range (high - low)."""
        return self.high - self.low


class PivotPoint(BaseModel):
    """Represents a detected swing high or low pivot point."""

    index: int
    timestamp: datetime
    price: float
    pivot_type: PivotType
    source_candle_index: int
    confirmation_candle_index: int | None = None
    left_bars: int = 0
    right_bars: int = 0

    @property
    def is_high(self) -> bool:
        """Check if this is a swing high."""
        return self.pivot_type == PivotType.SWING_HIGH

    @property
    def is_low(self) -> bool:
        """Check if this is a swing low."""
        return self.pivot_type == PivotType.SWING_LOW


class SwingLeg(BaseModel):
    """Represents a price leg between two pivot points."""

    leg_id: int
    start_pivot_id: int
    end_pivot_id: int
    direction: str
    start_timestamp: datetime
    end_timestamp: datetime
    start_price: float
    end_price: float
    absolute_change: float
    percent_change: float
    duration_seconds: float
    duration_minutes: float
    duration_bars: int

    @property
    def is_up(self) -> bool:
        """Check if this is an upward leg."""
        return self.direction == "up"

    @property
    def is_down(self) -> bool:
        """Check if this is a downward leg."""
        return self.direction == "down"

    @property
    def start_pivot(self) -> PivotPoint:
        """Return a PivotPoint for the start."""
        return PivotPoint(
            index=self.start_pivot_id,
            timestamp=self.start_timestamp,
            price=self.start_price,
            pivot_type=PivotType.SWING_HIGH if self.direction == "down" else PivotType.SWING_LOW,
            source_candle_index=self.start_pivot_id,
            left_bars=0,
            right_bars=0,
        )

    @property
    def end_pivot(self) -> PivotPoint:
        """Return a PivotPoint for the end."""
        return PivotPoint(
            index=self.end_pivot_id,
            timestamp=self.end_timestamp,
            price=self.end_price,
            pivot_type=PivotType.SWING_HIGH if self.direction == "up" else PivotType.SWING_LOW,
            source_candle_index=self.end_pivot_id,
            left_bars=0,
            right_bars=0,
        )


class AnalysisMetadata(BaseModel):
    """Metadata about an analysis run."""

    symbol: str
    timeframe: str
    pivot_method: str
    start_date: datetime
    end_date: datetime
    total_candles: int
    total_pivots: int
    total_legs: int
    run_timestamp: datetime
    config_hash: str = ""


class SummaryStatistics(BaseModel):
    """Summary statistics for swing legs."""

    total_legs: int
    avg_percent_change: float
    avg_duration_minutes: float
    avg_duration_bars: int
    min_percent_change: float
    max_percent_change: float
    min_duration_minutes: float
    max_duration_minutes: float
    up_legs_count: int
    down_legs_count: int
    up_legs_total_change: float = 0.0
    down_legs_total_change: float = 0.0
    up_legs_avg_change: float | None = None
    down_legs_avg_change: float | None = None
    up_legs_avg_duration: float | None = None
    down_legs_avg_duration: float | None = None
    median_percent_change: float = 0.0
    median_duration_minutes: float = 0.0
    up_down_asymmetry: float = 0.0
    amplitude_duration_correlation: float = 0.0
    net_change_pct: float = 0.0
    efficiency_ratio: float = 0.0
    realized_vol_pct_per_bar: float = 0.0
    max_drawdown_pct: float = 0.0


class PatternSequenceMatch(BaseModel):
    """A historical sequence that closely matches the current leg pattern."""

    anchor_leg_id: int
    similarity_score: float
    match_signature: str
    next_direction: str
    next_change_pct: float
    next_duration_bars: int
    horizon_change_pct: float
    horizon_direction: str


class PatternInsight(BaseModel):
    """Current pattern-recognition insight derived from historical analogs."""

    pattern_signature: str
    pattern_length: int
    forecast_horizon: int
    matches_used: int
    dominant_bias: str
    bullish_probability: float
    bearish_probability: float
    expected_next_change_pct: float
    expected_horizon_change_pct: float
    expected_next_duration_bars: float
    next_change_p25_pct: float | None = None
    next_change_p75_pct: float | None = None
    horizon_change_p25_pct: float | None = None
    horizon_change_p75_pct: float | None = None
    base_confidence: float
    adaptive_confidence: float
    historical_direction_hit_rate: float
    historical_horizon_hit_rate: float
    summary: str
    matches: list[PatternSequenceMatch] = Field(default_factory=list)


class PatternBacktestRecord(BaseModel):
    """Walk-forward prediction outcome for a historical pattern instance."""

    anchor_leg_id: int
    pattern_signature: str
    predicted_direction: str
    actual_direction: str
    predicted_horizon_direction: str
    actual_horizon_direction: str
    predicted_next_change_pct: float | None = None
    confidence_score: float
    adaptive_confidence: float
    was_direction_correct: bool
    did_horizon_hold: bool
    realized_next_change_pct: float
    realized_horizon_change_pct: float
    realized_next_duration_bars: int = 0
    regime_key: str = "unknown"
    regime_label: str = "Unknown regime"


class PatternLearningSummary(BaseModel):
    """Aggregate learning metrics from historical validation and persisted memory."""

    total_backtests: int
    direction_hit_rate: float
    horizon_hit_rate: float
    baseline_reversion_hit_rate: float = 0.0
    baseline_majority_hit_rate: float = 0.0
    direction_edge_vs_baseline: float = 0.0
    mean_abs_error_next_change_pct: float | None = None
    persistent_samples: int
    persistent_direction_hit_rate: float
    persistent_horizon_hit_rate: float
    adaptive_weight: float
    learning_note: str
    regime_key: str = "unknown"
    regime_label: str = "Unknown regime"
    regime_samples: int = 0
    regime_direction_hit_rate: float = 0.0
    regime_horizon_hit_rate: float = 0.0
    median_next_change_pct: float | None = None
    p25_next_change_pct: float | None = None
    p75_next_change_pct: float | None = None
    median_horizon_change_pct: float | None = None
    p25_horizon_change_pct: float | None = None
    p75_horizon_change_pct: float | None = None
    median_next_duration_bars: float | None = None


class MoonPhaseEvent(BaseModel):
    """A major moon-phase timestamp and its nearest swing response."""

    timestamp: datetime
    phase_name: str
    phase_code: str
    phase_fraction: float
    nearest_pivot_timestamp: datetime | None = None
    nearest_pivot_type: str | None = None
    nearest_pivot_price: float | None = None
    hours_to_nearest_pivot: float | None = None
    aligned_within_window: bool = False
    next_leg_direction: str | None = None
    next_leg_percent_change: float | None = None
    next_leg_duration_bars: int | None = None


class MoonPhasePhaseStats(BaseModel):
    """Aggregate behavior following a given moon phase."""

    phase_name: str
    occurrences: int
    aligned_events: int
    alignment_rate: float
    avg_hours_to_pivot: float | None = None
    swing_high_rate: float = 0.0
    swing_low_rate: float = 0.0
    bullish_next_leg_rate: float = 0.0
    bearish_next_leg_rate: float = 0.0
    avg_next_leg_change_pct: float | None = None
    avg_next_leg_duration_bars: float | None = None
    dominant_bias: str = "balanced"


class MoonPhaseInsight(BaseModel):
    """Correlation summary between major moon phases and BTC swings."""

    phase_window_hours: float
    total_events: int
    aligned_events: int
    alignment_rate: float
    avg_hours_to_pivot: float | None = None
    strongest_phase: str | None = None
    strongest_bias: str | None = None
    strongest_bias_score: float = 0.0
    summary: str
    events: list[MoonPhaseEvent] = Field(default_factory=list)
    phase_stats: list[MoonPhasePhaseStats] = Field(default_factory=list)


class AssetCorrelationObservation(BaseModel):
    """Aligned BTC/external-asset datapoint for correlation charts."""

    timestamp: datetime
    btc_normalized: float
    asset_normalized: float
    rolling_return_correlation: float | None = None


class AssetCorrelationInsight(BaseModel):
    """Cross-asset correlation summary for BTC versus a market benchmark."""

    asset_name: str
    asset_symbol: str
    overlap_points: int
    rolling_window_days: int
    price_correlation: float | None = None
    return_correlation: float | None = None
    beta_to_asset: float | None = None
    latest_rolling_correlation: float | None = None
    latest_relative_strength_pct: float | None = None
    summary: str
    observations: list[AssetCorrelationObservation] = Field(default_factory=list)


class StructureAnchor(BaseModel):
    """Exact chart coordinate supporting a structure discovery."""

    timestamp: datetime
    price: float
    role: str


class StructureDiscovery(BaseModel):
    """Auditable market-structure observation produced by a detector."""

    discovery_id: str
    structure_type: str
    title: str
    status: str
    direction: str
    confidence: float = Field(ge=0.0, le=1.0)
    start_timestamp: datetime
    end_timestamp: datetime
    anchors: list[StructureAnchor] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    measurements: dict[str, float | int | str] = Field(default_factory=dict)
    invalidation_price: float | None = None
    zone_low: float | None = None
    zone_high: float | None = None
    detector_version: str = "1.0"


class DecisionContribution(BaseModel):
    """One weighted piece of evidence behind a decision brief."""

    source: str
    stance: str  # "invest" | "divest" | "neutral"
    weight: float  # evidence weight (shares sum near 100)
    score: float  # signed contribution to the composite (-100..100 scale)
    rationale: str
    detail: str = ""
    prior_weight: float | None = None  # fixed baseline weight (set when learning is active)
    learned_multiplier: float | None = None  # adaptive weight multiplier from track record
    alignment_samples: int | None = None  # graded samples behind the multiplier


class DecisionInvalidation(BaseModel):
    """A price level whose break would flip the current call."""

    price: float
    kind: str  # "structure_break" | "zone_edge"
    flips_toward: str  # stance the break would favor
    rationale: str


class DecisionCheckpoint(BaseModel):
    """A replayed historical decision (no lookahead: suffix data only)."""

    timestamp: datetime
    close: float
    score: float
    action: str
    forward_return_pct: float | None = None


class DecisionBandStat(BaseModel):
    """Forward-return statistics for one action band across replayed checkpoints."""

    action: str
    count: int
    avg_forward_return_pct: float | None = None
    aligned_rate: float | None = None  # forward return matched the stance


class DecisionWalkForward(BaseModel):
    """Historical replay of the decision scorecard."""

    horizon_bars: int
    checkpoints: list[DecisionCheckpoint] = Field(default_factory=list)
    band_stats: list[DecisionBandStat] = Field(default_factory=list)
    benchmark_return_pct: float | None = None
    note: str = ""


class DecisionBrief(BaseModel):
    """Auditable investment/divestment decision assembled from all evidence."""

    action: str  # strong_invest | invest | hold | divest | strong_divest
    composite_score: float  # -100..100
    conviction: float  # 0..1
    quality: str  # low | moderate | high (evidence quality gate)
    summary: str
    contributions: list[DecisionContribution] = Field(default_factory=list)
    invalidations: list[DecisionInvalidation] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    excluded: list[str] = Field(default_factory=list)
    last_price: float | None = None
    walk_forward: DecisionWalkForward | None = None
    conviction_uncalibrated: float | None = None
    track_record: "DecisionTrackRecord | None" = None


class DecisionRecord(BaseModel):
    """A logged decision, later graded against the realised outcome."""

    decision_id: str
    symbol: str
    timeframe: str
    source: str  # "live" (analysis run) | "replay" (walk-forward backfill)
    logged_at: datetime
    candle_timestamp: datetime
    last_price: float
    action: str
    composite_score: float
    conviction: float
    quality: str = "moderate"
    contributions: list[DecisionContribution] = Field(default_factory=list)
    invalidations: list[DecisionInvalidation] = Field(default_factory=list)
    horizon_bars: int
    grade_due_timestamp: datetime
    hold_band_pct: float = 1.0
    config_hash: str = ""
    revision_count: int = 0
    # ── grading (None until the outcome window has passed) ──
    graded_at: datetime | None = None
    forward_return_pct: float | None = None
    outcome_correct: bool | None = None
    invalidated: bool | None = None
    invalidation_breach_price: float | None = None
    invalidation_breach_timestamp: datetime | None = None
    aligned: bool | None = None
    grade_note: str = ""


class DecisionSourceStat(BaseModel):
    """Learned per-evidence-source performance from graded decisions."""

    source: str
    prior_weight: float
    multiplier: float  # learned, capped [0.5, 1.5]
    effective_weight: float  # after renormalisation to Σ100
    samples: int
    hits: int
    aligned_rate: float | None = None  # smoothed toward 0.5
    live_samples: int = 0
    replay_samples: int = 0


class DecisionGradedItem(BaseModel):
    """One graded past decision, for the track-record table."""

    candle_timestamp: datetime
    action: str
    source: str
    composite_score: float
    forward_return_pct: float | None
    aligned: bool | None
    invalidated: bool


class DecisionTrackRecord(BaseModel):
    """The engine's graded history for a symbol/timeframe pair."""

    graded_total: int = 0
    aligned_total: int = 0
    alignment_rate: float | None = None  # smoothed engine rate
    invalidated_total: int = 0
    live_graded: int = 0
    replay_graded: int = 0
    pending: int = 0
    avg_forward_return_pct: float | None = None
    band_stats: list[DecisionBandStat] = Field(default_factory=list)
    source_stats: list[DecisionSourceStat] = Field(default_factory=list)
    recent_graded: list[DecisionGradedItem] = Field(default_factory=list)
    calibration_factor: float = 1.0
    note: str = ""


# Resolve DecisionBrief's forward reference to DecisionTrackRecord.
DecisionBrief.model_rebuild()


class AnalysisResult(BaseModel):
    """Complete result of an analysis run."""

    metadata: AnalysisMetadata
    pivots: list[PivotPoint]
    legs: list[SwingLeg]
    summary: SummaryStatistics
    raw_data: list[OHLCV] = Field(default_factory=list)
    pattern_insight: PatternInsight | None = None
    pattern_learning: PatternLearningSummary | None = None
    pattern_backtests: list[PatternBacktestRecord] = Field(default_factory=list)
    moon_phase_insight: MoonPhaseInsight | None = None
    gold_correlation_insight: AssetCorrelationInsight | None = None
    nasdaq_correlation_insight: AssetCorrelationInsight | None = None
    oil_correlation_insight: AssetCorrelationInsight | None = None
    structure_discoveries: list[StructureDiscovery] = Field(default_factory=list)
    forming_leg: SwingLeg | None = None
    decision_brief: DecisionBrief | None = None
    correlation_errors: dict[str, str] = Field(default_factory=dict)


class ExportManifest(BaseModel):
    """Manifest of exported files."""

    output_directory: str
    generated_at: datetime
    symbol: str
    timeframe: str
    files: dict[str, str] = Field(default_factory=dict)


class Config(BaseModel):
    """Configuration for the BTC swing cycle tracker."""

    symbol: str = "BTC-USD"
    timeframe: Timeframe = Timeframe.FIVE_MINUTE
    lookback_period: str = "30d"
    pivot_method: PivotMethod = PivotMethod.ZIGZAG
    min_move_pct: float = 1.0
    left_bars: int = 5
    right_bars: int = 5
    use_atr_filter: bool = True
    atr_period: int = 14
    atr_multiplier: float = 1.5
    output_dir: str = "outputs"
    chart_width: int = 1200
    chart_height: int = 800
    save_chart: bool = True
    save_csv: bool = True
    csv_include_raw_data: bool = False
    enable_pattern_recognition: bool = True
    pattern_length: int = 3
    pattern_forecast_horizon: int = 2
    pattern_max_matches: int = 8
    enable_decision_engine: bool = True
    decision_walk_forward_checkpoints: int = 12
    enable_decision_memory: bool = True
    enable_adaptive_decision_weights: bool = True
    decision_learning_min_samples: int = 5
    decision_memory_max_records: int = 1000
    enable_moon_phase_analysis: bool = True
    enable_gold_correlation_analysis: bool = True
    enable_nasdaq_correlation_analysis: bool = True
    enable_oil_correlation_analysis: bool = False

    @field_validator("lookback_period")
    @classmethod
    def validate_lookback(cls, v: str) -> str:
        """Validate lookback period format."""
        if not any(v.endswith(suffix) for suffix in ["d", "w", "m", "y"]):
            raise ValueError("lookback_period must end with d, w, m, or y")
        return v

    @field_validator("pattern_length")
    @classmethod
    def validate_pattern_length(cls, value: int) -> int:
        """Pattern length should stay in a practical range."""
        if value < 2 or value > 6:
            raise ValueError("pattern_length must be between 2 and 6")
        return value

    @field_validator("pattern_forecast_horizon")
    @classmethod
    def validate_pattern_forecast_horizon(cls, value: int) -> int:
        """Forecast horizon should be small relative to the leg series."""
        if value < 1 or value > 6:
            raise ValueError("pattern_forecast_horizon must be between 1 and 6")
        return value

    @field_validator("pattern_max_matches")
    @classmethod
    def validate_pattern_max_matches(cls, value: int) -> int:
        """Limit the number of analog matches to keep insights focused."""
        if value < 1 or value > 25:
            raise ValueError("pattern_max_matches must be between 1 and 25")
        return value

    @field_validator("decision_walk_forward_checkpoints")
    @classmethod
    def validate_decision_checkpoints(cls, value: int) -> int:
        """Keep the historical replay cheap; 0 disables it."""
        if value < 0 or value > 24:
            raise ValueError("decision_walk_forward_checkpoints must be between 0 and 24")
        return value

    @field_validator("decision_learning_min_samples")
    @classmethod
    def validate_decision_min_samples(cls, value: int) -> int:
        """Adaptation waits for a real sample before acting on it."""
        if value < 0 or value > 100:
            raise ValueError("decision_learning_min_samples must be between 0 and 100")
        return value

    @field_validator("decision_memory_max_records")
    @classmethod
    def validate_decision_max_records(cls, value: int) -> int:
        """Bound the persisted decision log."""
        if value < 100 or value > 10000:
            raise ValueError("decision_memory_max_records must be between 100 and 10000")
        return value
