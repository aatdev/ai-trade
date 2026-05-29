# Uptrend Analyzer Report

**Generated:** 2026-05-29 16:13:57
**Data Source:** Monty's Uptrend Ratio Dashboard (GitHub CSV)
**API Key Required:** No

---

## Overall Assessment

| Metric | Value |
|--------|-------|
| **Composite Score** | **46.9/100** |
| **Zone** | 🟡 Neutral |
| **Zone Detail** | Neutral |
| **Zone Proximity** | **Near boundary: +6.9 points from 40 (above)** |
| **Exposure Guidance** | Reduced Exposure (60-80%) |
| **Warning Penalty** | -3 (raw: 49.9/100) |
| **Active Warnings** | 1: SECTOR DIVERGENCE WARNING |
| **Strongest Component** | Sector Rotation (70/100) |
| **Weakest Component** | Market Breadth (Overall) (32/100) |
| **Data Quality** | Complete (5/5 components) |
| **Confidence** | High (moderate, Both regime coverage) |

> **Guidance:** Mixed signals. Participate selectively with tighter risk controls.

---

## Active Warnings

### SECTOR DIVERGENCE WARNING
> Significant divergence detected within sector groups. Some sectors within the same group are moving in opposite directions, suggesting hidden risk beneath the averages.

- Verify individual sector trends before entering positions
- Avoid sectors diverging from their group majority
- Monitor for group convergence or further deterioration

---

## Current Market Snapshot

| Metric | Value |
|--------|-------|
| Uptrend Ratio | 23.8% |
| 10-Day MA | 22.2% |
| Trend | down |
| Slope | -0.0008 |
| Distance from 37% (Overbought) | -13.2pp |
| Distance from 9.7% (Oversold) | +14.1pp |
| Date | 2026-05-28 |

---

## Component Scores

| # | Component | Weight | Score | Contribution | Signal |
|---|-----------|--------|-------|--------------|--------|
| 1 | **Market Breadth (Overall)** | 30% | █░░░ 32 | 9.6 | WEAK: 23.8% uptrend ratio, trend down |
| 2 | **Sector Participation** | 25% | ██░░ 54 | 13.5 | MODERATE: 4/11 sectors uptrending, spread 27.4% |
| 3 | **Sector Rotation** | 15% | ███░ 70 | 10.5 | RISK-ON: Cyclical leads by 7.5pp |
| 4 | **Momentum** | 20% | ██░░ 56 | 11.2 | NEUTRAL MOMENTUM: slope=-0.0004, accelerating |
| 5 | **Historical Context** | 10% | ██░░ 51 | 5.1 | NEAR MEDIAN: 23.8% at 51.3th percentile historically |

---

## Component Details

### 1. Market Breadth (Overall)

- **Uptrend Ratio:** 23.8%
- **10-Day MA:** 22.2%
- **Trend:** down
- **Slope:** -0.0008
- **Trend Adjustment:** -5

### 2. Sector Participation

- **Uptrending Sectors:** 4/11
- **Count Score:** 40/100
- **Spread:** 27.4% (score: 75/100)
- **Overbought (>37%):** 1 sectors (Technology)
- **Oversold (<9.7%):** 0 sectors ()

### 3. Sector Rotation

- **Cyclical Avg:** 25.8%
- **Defensive Avg:** 18.3%
- **Commodity Avg:** 20.1%
- **Cyclical-Defensive Gap:** 7.5pp
- **Divergence Warning:** YES (penalty: -5)
  - **Cyclical Divergence:** std=0.0827, spread=0.2423
    - Outlier: Technology (deviation: +0.1395)
    - Trend dissenter: Communication Services (down vs majority up)
    - Trend dissenter: Industrials (down vs majority up)
  - **Defensive Divergence:** std=0.053, spread=0.1181
    - Trend dissenter: Real Estate (up vs majority down)

**Cyclical Sectors:**

| Sector | Ratio | Trend | Slope |
|--------|-------|-------|-------|
| Technology | 39.7% | Up | +0.0029 |
| Consumer Cyclical | 22.5% | Up | +0.0110 |
| Communication Services | 21.6% | Down | -0.0018 |
| Financial | 15.5% | Up | +0.0030 |
| Industrials | 29.5% | Down | -0.0013 |


**Defensive Sectors:**

| Sector | Ratio | Trend | Slope |
|--------|-------|-------|-------|
| Utilities | 12.3% | Down | +0.0000 |
| Consumer Defensive | 13.7% | Down | -0.0011 |
| Healthcare | 24.2% | Down | -0.0015 |
| Real Estate | 22.9% | Up | +0.0040 |


**Commodity Sectors:**

| Sector | Ratio | Trend | Slope |
|--------|-------|-------|-------|
| Energy | 12.7% | Down | -0.0397 |
| Basic Materials | 27.6% | Down | -0.0079 |


### 4. Momentum

- **Raw Slope:** -0.0008 
- **Smoothed Slope (EMA(3)):** -0.0004 (score: 53/100)
- **Acceleration (10v10):** 0.001524 (accelerating, score: 75/100)
- **Sector Slope Breadth:** 4/11 positive (score: 36/100)

### 5. Historical Context

- **Current Ratio:** 23.8%
- **Percentile Rank:** 51.3th
- **Historical Range:** 1.1% - 44.3%
- **Historical Median:** 23.4%
- **30-Day Avg:** 26.6%
- **90-Day Avg:** 25.6%
- **Data Points:** 724 (2023-08-11 to 2026-05-28)
- **Confidence:** High (sample: moderate, regime: Both, recency: balanced)

---

## Sector Heatmap

| Rank | Sector | Ratio | Count/Total | 10MA | Trend | Slope | Status |
|------|--------|-------|-------------|------|-------|-------|--------|
| 1 | Technology | 39.7% | 168/423 | 33.8% | Up | +0.0029 | Overbought |
| 2 | Industrials | 29.5% | 115/390 | 24.8% | Down | -0.0013 | Normal |
| 3 | Basic Materials | 27.6% | 43/156 | 17.2% | Down | -0.0079 | Normal |
| 4 | Healthcare | 24.2% | 100/414 | 20.8% | Down | -0.0015 | Normal |
| 5 | Real Estate | 22.9% | 33/144 | 20.3% | Up | +0.0040 | Normal |
| 6 | Consumer Cyclical | 22.5% | 63/280 | 13.9% | Up | +0.0110 | Normal |
| 7 | Communication Services | 21.6% | 24/111 | 21.2% | Down | -0.0018 | Normal |
| 8 | Financial | 15.5% | 92/594 | 15.9% | Up | +0.0030 | Normal |
| 9 | Consumer Defensive | 13.7% | 16/117 | 14.7% | Down | -0.0011 | Normal |
| 10 | Energy | 12.7% | 21/165 | 44.5% | Down | -0.0397 | Normal |
| 11 | Utilities | 12.3% | 10/81 | 10.3% | Down | +0.0000 | Normal |

---

## Recommended Actions

**Zone:** Neutral (Neutral)
**Exposure Guidance:** Reduced Exposure (60-80%)

- Reduce position sizes by 20-30%
- Focus on strongest sectors only
- Tighten stop-losses
- Avoid low-quality setups
- Increase cash allocation gradually

---

## Methodology

This analysis uses Monty's Uptrend Ratio Dashboard data to assess market breadth health.
The dashboard tracks ~2,800 US stocks across 11 sectors, measuring the percentage in uptrends.

**5-Component Scoring System (0-100, higher = healthier):**

1. **Market Breadth (30%):** Overall uptrend ratio level and trend direction
2. **Sector Participation (25%):** Number of uptrending sectors and spread uniformity
3. **Sector Rotation (15%):** Cyclical vs Defensive vs Commodity balance
4. **Momentum (20%):** Slope direction, acceleration, and sector slope breadth
5. **Historical Context (10%):** Percentile rank in historical distribution

**Key Thresholds (Monty's Dashboard):** Overbought = 37%, Oversold = 9.7%

For detailed methodology, see `references/uptrend_methodology.md`.

---

**Disclaimer:** This analysis is for educational and informational purposes only. Not investment advice. Past patterns may not predict future outcomes. Conduct your own research and consult a financial advisor before making investment decisions.
