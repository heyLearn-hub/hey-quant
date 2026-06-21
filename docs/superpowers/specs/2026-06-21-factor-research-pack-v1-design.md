# Factor Research Pack v1 Design

## Decision: Is This Worth Doing?

Yes. The current strategy already has a usable low-frequency trend core, but the factor layer is too implicit. The system can compute `ma50`, `ma200`, `mom20`, `mom60`, `rsi14`, `atr14`, volume confirmation, and benchmark-relative strength, yet it does not explain which factors are production inputs, which are research-only, and which reduce risk. That makes it hard to learn, compare variants, or decide whether adding options sentiment later is actually useful.

This change is worth doing before market sentiment or options analytics because it improves the research foundation without increasing data cost or signal noise. Options wall, put/call, skew, and IV analysis should remain a later overlay until the core factor research report can prove that simpler daily factors are understood and testable.

## Goals

- Create a `factor_registry` that documents every factor's group, calculation source, economic meaning, and intended use.
- Add a small set of higher-signal daily factors that can be computed from existing OHLCV data.
- Improve `factor-test` so the report is useful for learning and decision review, not just a top/bottom table.
- Keep production signal generation unchanged in this phase.
- Make the system explicitly say that options/sentiment analysis is deferred until the factor research pack is validated.

## Non-Goals

- No options chain, option wall, put/call ratio, IV rank, skew, or gamma exposure in this phase.
- No automatic change to buy/sell rules.
- No machine learning factor selection.
- No intraday factors.
- No new paid data dependency.

## Factor Set

Existing factors to keep:

- `mom20`: 20-day price momentum.
- `mom60`: 60-day price momentum.
- `rel20`: 20-day relative strength versus benchmark.
- `rel60`: 60-day relative strength versus benchmark.
- `rsi14`: 14-day RSI.

New factors:

- `mom120`: 120-day price momentum.
- `trend_slope_50`: 50-day moving-average slope over 20 trading days.
- `trend_slope_200`: 200-day moving-average slope over 60 trading days.
- `dist_ma50`: price distance from 50-day moving average.
- `dist_ma200`: price distance from 200-day moving average.
- `realized_vol20`: annualized 20-day realized volatility.
- `realized_vol60`: annualized 60-day realized volatility.
- `atr_pct`: ATR as percent of close.
- `risk_adjusted_mom60`: 60-day momentum divided by 60-day realized volatility.
- `drawdown60`: current close versus trailing 60-day high.
- `drawdown120`: current close versus trailing 120-day high.

## Factor Groups And Uses

| Group | Factors | Primary use |
| --- | --- | --- |
| Momentum | `mom20`, `mom60`, `mom120`, `risk_adjusted_mom60` | Candidate ranking and research |
| Trend | `trend_slope_50`, `trend_slope_200`, `dist_ma50`, `dist_ma200` | Trend confirmation and overextension review |
| Relative strength | `rel20`, `rel60` | Benchmark-relative selection |
| Volatility | `realized_vol20`, `realized_vol60`, `atr_pct` | Risk sizing and candidate filtering research |
| Drawdown | `drawdown60`, `drawdown120` | Downside risk and recovery quality |
| Oscillator | `rsi14` | Overheated/weak momentum context |

## Architecture

### `indicators`

`build_indicators` will calculate the new OHLCV-derived columns. All formulas must use only historical rolling windows and must not use future returns.

### `factors`

Add a registry object, likely `FactorDefinition`, with:

- `name`
- `group`
- `direction`
- `description`
- `production_use`

`run_factor_experiment` will continue to generate raw factor observations and forward returns, but metrics will carry group and description from the registry.

### Factor Report

`write_factor_report` will include:

- a factor registry section;
- grouped factor results;
- top/bottom forward return spread;
- hit rate;
- a note that results are research-only and not direct trade instructions;
- a note that options/sentiment overlay is intentionally deferred.

## Data Flow

```text
OHLCV + benchmark
  -> build_indicators
  -> factor registry selects factors
  -> run_factor_experiment computes forward returns
  -> grouped HTML factor research report
```

## Testing Plan

Use test-first implementation.

Tests to add or update:

- `build_indicators` emits all new factor columns.
- volatility and ATR percentage calculations are finite once enough history exists.
- drawdown factors are non-positive or zero.
- factor registry contains all default factors and classifies them into groups.
- `run_factor_experiment` returns metrics with group metadata.
- factor HTML report includes registry, grouped results, and deferred options/sentiment note.
- existing offline factor-test CLI still works.

## Acceptance Criteria

```bash
.venv/bin/python -m pytest tests/test_factors.py tests/test_indicators_signals.py -q
bin/quant-ai-local factor-test --config config/default.yaml --offline-sample --out outputs/factor_report.html
.venv/bin/python -m pytest -q
```

The generated factor report must clearly answer:

- What factor was tested?
- What group does it belong to?
- What economic question does it try to answer?
- Is it a production signal, risk input, or research-only observation?
- Did the top group outperform the bottom group in the selected sample?

## Follow-Up Gate For Options And Sentiment

Before building options or market sentiment analytics, ask:

1. Does the current factor research report show unresolved risk that options/sentiment could help explain?
2. Do we have a reliable and affordable data source for the required history?
3. Can the feature be backtested or at least audited against historical decisions?
4. Will it change sizing/risk decisions, or only add noise?

Only proceed if at least one concrete use case is true:

- reduce false buy signals before earnings;
- detect crowded call/put positioning that changes add/trim decisions;
- identify IV-implied event risk that affects holding size;
- improve risk alerts for real open positions.
