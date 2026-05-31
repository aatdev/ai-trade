# Uptrend Analyzer Report

**Generated:** 2026-05-31 17:06:01
**Data Source:** Monty's Uptrend Ratio Dashboard (GitHub CSV)
**API Key Required:** No

---

## Overall Assessment

| Metric | Value |
|--------|-------|
| **Composite Score** | **57.7/100** |
| **Zone** | 🟡 Neutral |
| **Zone Detail** | Neutral |
| **Zone Proximity** | **Near boundary: -2.3 points from 60 (below)** |
| **Exposure Guidance** | Reduced Exposure (60-80%) |
| **Warning Penalty** | -3 (raw: 60.7/100) |
| **Active Warnings** | 1: SECTOR DIVERGENCE WARNING |
| **Strongest Component** | Sector Participation (77/100) |
| **Weakest Component** | Market Breadth (Overall) (41/100) |
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
| Uptrend Ratio | 23.5% |
| 10-Day MA | 22.4% |
| Trend | up |
| Slope | +0.0026 |
| Distance from 37% (Overbought) | -13.5pp |
| Distance from 9.7% (Oversold) | +13.8pp |
| Date | 2026-05-29 |

---

## Component Scores

| # | Component | Weight | Score | Contribution | Signal |
|---|-----------|--------|-------|--------------|--------|
| 1 | **Market Breadth (Overall)** | 30% | ██░░ 41 | 12.3 | WEAK: 23.5% uptrend ratio, trend up |
| 2 | **Sector Participation** | 25% | ███░ 77 | 19.2 | HEALTHY: 9/11 sectors uptrending, spread 28.2% |
| 3 | **Sector Rotation** | 15% | ███░ 72 | 10.8 | RISK-ON: Cyclical leads by 8.8pp |
| 4 | **Momentum** | 20% | ███░ 67 | 13.4 | POSITIVE MOMENTUM: slope=0.0011, accelerating |
| 5 | **Historical Context** | 10% | ██░░ 50 | 5.0 | NEAR MEDIAN: 23.5% at 50.3th percentile historically |

---

## Component Details

### 1. Market Breadth (Overall)

- **Uptrend Ratio:** 23.5%
- **10-Day MA:** 22.4%
- **Trend:** up
- **Slope:** +0.0026
- **Trend Adjustment:** +5

### 2. Sector Participation

- **Uptrending Sectors:** 9/11
- **Count Score:** 80/100
- **Spread:** 28.2% (score: 74/100)
- **Overbought (>37%):** 0 sectors ()
- **Oversold (<9.7%):** 1 sectors (Energy)

### 3. Sector Rotation

- **Cyclical Avg:** 25.6%
- **Defensive Avg:** 16.8%
- **Commodity Avg:** 20.7%
- **Cyclical-Defensive Gap:** 8.8pp
- **Divergence Warning:** YES (penalty: -5)
  - **Defensive Divergence:** std=0.0534, spread=0.1414
    - Trend dissenter: Consumer Defensive (down vs majority up)

**Cyclical Sectors:**

| Sector | Ratio | Trend | Slope |
|--------|-------|-------|-------|
| Technology | 36.6% | Up | +0.0042 |
| Consumer Cyclical | 21.4% | Up | +0.0108 |
| Communication Services | 23.6% | Up | +0.0025 |
| Financial | 18.7% | Up | +0.0083 |
| Industrials | 27.6% | Up | +0.0022 |


**Defensive Sectors:**

| Sector | Ratio | Trend | Slope |
|--------|-------|-------|-------|
| Utilities | 13.8% | Up | +0.0076 |
| Consumer Defensive | 10.3% | Down | -0.0047 |
| Healthcare | 24.4% | Up | +0.0046 |
| Real Estate | 18.9% | Up | +0.0076 |


**Commodity Sectors:**

| Sector | Ratio | Trend | Slope |
|--------|-------|-------|-------|
| Energy | 8.4% | Down | -0.0518 |
| Basic Materials | 32.9% | Up | +0.0134 |


### 4. Momentum

- **Raw Slope:** +0.0026 
- **Smoothed Slope (EMA(3)):** +0.0011 (score: 57/100)
- **Acceleration (10v10):** 0.002516 (accelerating, score: 75/100)
- **Sector Slope Breadth:** 9/11 positive (score: 82/100)

### 5. Historical Context

- **Current Ratio:** 23.5%
- **Percentile Rank:** 50.3th
- **Historical Range:** 1.1% - 44.3%
- **Historical Median:** 23.4%
- **30-Day Avg:** 26.3%
- **90-Day Avg:** 25.5%
- **Data Points:** 725 (2023-08-11 to 2026-05-29)
- **Confidence:** High (sample: moderate, regime: Both, recency: balanced)

---

## Sector Heatmap

| Rank | Sector | Ratio | Count/Total | 10MA | Trend | Slope | Status |
|------|--------|-------|-------------|------|-------|-------|--------|
| 1 | Technology | 36.6% | 153/418 | 34.3% | Up | +0.0042 | Normal |
| 2 | Basic Materials | 32.9% | 52/158 | 18.5% | Up | +0.0134 | Normal |
| 3 | Industrials | 27.6% | 107/387 | 25.1% | Up | +0.0022 | Normal |
| 4 | Healthcare | 24.4% | 101/414 | 21.3% | Up | +0.0046 | Normal |
| 5 | Communication Services | 23.6% | 26/110 | 21.5% | Up | +0.0025 | Normal |
| 6 | Consumer Cyclical | 21.4% | 60/281 | 15.0% | Up | +0.0108 | Normal |
| 7 | Real Estate | 18.9% | 27/143 | 21.1% | Up | +0.0076 | Normal |
| 8 | Financial | 18.7% | 112/600 | 16.7% | Up | +0.0083 | Normal |
| 9 | Utilities | 13.8% | 11/80 | 11.1% | Up | +0.0076 | Normal |
| 10 | Consumer Defensive | 10.3% | 12/117 | 14.2% | Down | -0.0047 | Normal |
| 11 | Energy | 8.4% | 14/166 | 39.3% | Down | -0.0518 | Oversold |

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
