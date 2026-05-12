# WeatherEdge Implementation Plan: Accuracy & Auto-Edge Detection

**Status**: Planning Phase  
**Start Date**: April 28, 2026  
**Estimated Duration**: 4-6 weeks (3 phases)  
**Priority**: Core prediction accuracy first, then automation

---

## Executive Summary

The app has **correct edge calculation logic** but lacks:
1. **Professional temperature prediction methodology** (just using normal distribution)
2. **Real-time Polymarket automation** (users manually type odds)
3. **Prediction calibration & validation** (no backtesting)

**Deliverables**:
- Asymmetric temperature distribution model
- Thermal lag physics for peak time calculation
- Model bias correction system
- Live Polymarket odds polling (auto-fetch, no manual input)
- Backtesting framework for validation

---

## Phase 1: Professional Temperature Prediction Model

### Goal
Replace simple normal distribution with physics-based asymmetric model that matches professional meteorologist practices.

### Changes

#### 1.1 Improve Thermal Lag Calculation
**File**: `app/weather.py` (line 1575)  
**Function**: `compute_peak_hour()`  
**Current State**: Partially implemented; calculates peak hour but not fully utilized  
**Changes**:
- Expand formula to account for:
  - **Latitude effect**: Higher latitudes have later peak times
  - **Season effect**: Winter peaks 1-2pm, summer peaks 3-5pm
  - **Cloud cover influence**: Cloudy days peak 1-2 hours earlier
  - **Elevation effect**: Higher elevations peak ~30 min earlier
- Return not just hour, but also sigma_seasonal adjustment (uncertainty factor)
- Test on all 10+ cities to ensure accuracy

**Inputs**: lat, lon, month, climate, urban, coastal, elevation, cloud_cover_forecast  
**Outputs**: peak_hour (int 0-23), thermal_uncertainty (float)

#### 1.2 Implement Asymmetric Distribution
**File**: `app/weather.py` (line 2154)  
**Function**: `compute_bracket_analysis()` → NEW: `compute_skewed_distribution_probs()`  
**Current State**: Uses normal distribution (symmetric)  
**Changes**:
- Replace normal distribution with **skewed normal distribution** (scipy.stats.skewnorm)
  - Positive skew: heating faster than cooling (typical for clear days)
  - Negative skew: cooling dominates (typical for cloudy/rainy days)
  - Skew factor derived from: cloud cover, wind speed, humidity
- Formula:
  ```
  skewness = f(cloud_cover, wind, humidity)
  if cloud_cover > 80%: skewness = -0.8  (cooling dominates)
  elif cloud_cover < 20%: skewness = +0.8 (heating dominates)
  else: skewness = 0.2 + (cloud_cover - 50) * -0.032
  
  bracket_prob = CDF(skewnorm(loc, scale, skewness), bracket_hi) 
               - CDF(skewnorm(loc, scale, skewness), bracket_lo)
  ```
- Fallback to normal dist if cloud data unavailable

**Inputs**: distribution_center, sigma, cloud_cover_pct, wind_speed, humidity  
**Outputs**: brackets with forecast_prob using skewed distribution

#### 1.3 Add Model Bias Correction
**File**: `app/weather.py` (NEW section after line 350)  
**Function**: NEW `apply_model_bias_correction()`  
**Current State**: None  
**Changes**:
- Create bias lookup table by model, season, region:
  ```python
  BIAS_CORRECTIONS = {
      "HRRR": {
          "summer": {"us_south": +2.1, "us_north": +0.8, "us_west": +1.3},
          "winter": {"us_south": -0.4, "us_north": -1.2, "us_west": -0.6},
      },
      "ICON": {
          "summer": {"global": -0.5},
          "winter": {"global": +0.8},
      },
      # ... GEM, ECMWF, MetFrance
  }
  ```
- Apply corrections before consensus computation:
  ```python
  corrected_peak = model_peak + bias_correction
  ```
- Document source (NWS/ECMWF historical verifications)

**Inputs**: model_name, peak_temp, lat, lon, month  
**Outputs**: corrected_peak (float)

#### 1.4 Optimize Ensemble Weighting
**File**: `app/weather.py` (line 384)  
**Function**: `compute_ensemble_quantiles()` → enhance member weighting  
**Current State**: All ensemble members weighted equally  
**Changes**:
- Weight ensemble members by forecast age:
  - Newest members (ensemble run time latest): weight 1.0
  - Previous run: weight 0.9
  - 2 runs ago: weight 0.8
  - etc.
- Reason: Newer ensemble cycles have better skill (assimilated more recent observations)
- Implement as parameter: `member_weights = [1.0, 0.95, 0.90, ..., 0.60]`
- Recalculate quantiles (P10, P25, P50, P75, P90) using weighted percentiles

**Inputs**: ensemble_members (list), member_ages (list of run times)  
**Outputs**: weighted_quantiles dict with p10, p25, p50, p75, p90

#### 1.5 Improve Intraday Bayesian Update
**File**: `app/weather.py` (line 571)  
**Function**: `bayesian_intraday_update()` → enhance confidence weighting  
**Current State**: Uses fixed weight for WU observations  
**Changes**:
- **Dynamic weight based on time of day**:
  - Before 9am: model forecast 90%, WU observation 10% (models more reliable early)
  - 9am-1pm: 70% model, 30% WU (observations gaining strength)
  - 1pm-4pm: 50% model, 50% WU (equal weight at peak risk period)
  - After 4pm: 20% model, 80% WU (WU nearly final)
- **Quality check**: If WU peak looks suspicious (e.g. 150°F in Seattle), reduce weight
- Update trend detection: accelerating heating → higher forecast; cooling starting → lower forecast

**Inputs**: current_time, wu_peak_so_far, model_forecast, hourly_temps  
**Outputs**: updated_forecast with confidence bounds

---

## Phase 2: Live Polymarket Automation

### Goal
Automatically fetch Polymarket odds, calculate real-time edges, eliminate manual data entry.

### Changes

#### 2.1 Enhance Polymarket Polling Client-Side
**File**: `app/templates/weather.html` (line 1204)  
**Function**: `loadPMLive()` → enhance to continuous polling  
**Current State**: One-time fetch after analysis  
**Changes**:
- Add automatic polling loop during market hours (8am-11pm user's timezone):
  ```javascript
  // Poll every 5 seconds during market hours
  if (isMarketHours) {
    pmPollInterval = setInterval(refreshPMOdds, 5000);
  }
  ```
- Implement `refreshPMOdds()` function:
  - Fetch current bracket odds from PM gamma-api
  - Compare to previous poll results
  - If odds changed: recalculate edges, update UI
  - Show "Last updated: X seconds ago"
- Stop polling after market close or on app close
- Cache odds to avoid redundant API calls (5-second debounce)

**Implementation Detail**:
```javascript
async function refreshPMOdds() {
  if (!D || !D.brackets) return;
  
  // Fetch latest odds
  const resp = await fetch(`/api/pm_odds/${city}/${date}?center=${center}&sigma=${sigma}`);
  const data = await resp.json();
  
  // Auto-compute edge without user input
  D.brackets = data.brackets;  // Update with latest pm_yes_price
  computeEdgeAuto();            // Calculate (NEW function)
  updateEdgeDisplay(D);         // Refresh UI
}

function computeEdgeAuto() {
  // Same as computeEdge() but pulls odds from D.brackets[].pm_yes_price
  // No manual input needed
}
```

**Inputs**: city, date, center, sigma  
**Outputs**: Updated D.brackets with fresh pm_yes_price, recalculated edges

#### 2.2 Redesign Edge Display (No Manual Input)
**File**: `app/templates/weather.html` (line 1850)  
**Function**: `renderEdgeTab()` → remove manual input section, add live display  
**Current State**: 
```
User input boxes asking for Polymarket YES%
Manual "Calculate Edge" button
```
**Changes**:
- **Remove**: Input boxes for manual odds entry
- **Add**: Live edge display card showing:
  ```
  ┌─────────────────────────────────────────┐
  │ 🔴 LIVE POLYMARKET EDGES (Updated 2s ago)│
  ├─────────────────────────────────────────┤
  │ 40-50°F: Forecast 23% | Market 15% | +8% edge ⭐⭐ | BUY YES
  │ 50-60°F: Forecast 45% | Market 60% | -15% edge ⭐⭐⭐ | BUY NO ◀ TOP
  │ 60-70°F: Forecast 28% | Market 25% | +3% edge | SKIP
  └─────────────────────────────────────────┘
  ```
- Sort by edge strength (top opportunity first)
- Color code: Green background for +edge, red for -edge, gray for none
- Add "Copy Top Trade" button to copy best recommendation to clipboard
- Show confidence stars based on edge magnitude and volume

**CSS Changes**:
- Add `.edge-live` class for live display card
- Color schemes for BUY YES (green), BUY NO (red), SKIP (gray)
- Add pulsing indicator for "updated X seconds ago"

#### 2.3 Add Real-Time Trade Recommendation Panel
**File**: `app/templates/weather.html` (NEW section in main view)  
**Component**: NEW `<div id="best-trade-panel">`  
**Current State**: None  
**Changes**:
- **Top of page** (after Polymarket link bar): Show best current opportunity:
  ```
  ┌──────────────────────────────────────┐
  │ ⚡ BEST TRADE RIGHT NOW              │
  ├──────────────────────────────────────┤
  │ Bracket: 50-60°F                     │
  │ Your forecast: 45% probability       │
  │ Market odds: 60%                     │
  │ EDGE: -15% (BUY NO)    ⭐⭐⭐       │
  │ Volume: $245K                        │
  │ Action: ▼ BUY NO at 60¢              │
  └──────────────────────────────────────┘
  ```
- Update every 5 seconds when polling
- Show only if edge > 5% (meaningful opportunity)
- Link to Polymarket market

**Inputs**: D.brackets with pm_yes_price and forecast_prob  
**Outputs**: HTML panel with best trade highlighted

#### 2.4 Implement Edge Auto-Calculation Function
**File**: `app/templates/weather.html` (after line 1908)  
**Function**: NEW `computeEdgeAuto()`  
**Current State**: None  
**Changes**:
- Extract from existing `computeEdge()` logic but use pm_yes_price from brackets:
  ```javascript
  function computeEdgeAuto() {
    if (!D?.brackets) return;
    
    D.brackets.forEach(b => {
      const forecast = b.forecast_prob;
      const market = b.pm_yes_price;
      if (forecast != null && market != null) {
        b.edge = forecast - market;
        b.rating = getEdgeRating(b.edge);
      }
    });
    
    updateAllEdgeDisplays();  // Refresh UI
  }
  ```

#### 2.5 Add Market Hours Detection
**File**: `app/templates/weather.html` (NEW utility function)  
**Function**: NEW `isMarketHours()`  
**Current State**: None  
**Changes**:
- Detect if Polymarket is currently trading:
  ```javascript
  function isMarketHours() {
    const now = new Date();
    const hour = now.getHours();
    return hour >= 8 && hour <= 23;  // 8am-11pm local user time (PM default)
  }
  ```
- Also check date: Don't poll on weekends/holidays
- Start/stop polling based on market hours

---

## Phase 3: Validation & Backtesting

### Goal
Verify prediction accuracy and edge calculation validity.

### Changes

#### 3.1 Create Backtesting Framework
**File**: `app/weather.py` (NEW file: `app/backtest.py`)  
**Purpose**: Compare historical predictions vs actual outcomes  
**Functions**:
- `backtest_city_date(city, date, use_old_model=False)`:
  - Fetch historical weather data (actual temps)
  - Re-run prediction with both old and new model
  - Calculate error metrics
  - Return: {date, city, old_pred, new_pred, actual, old_error, new_error}

- `generate_backtest_report(start_date, end_date, cities)`:
  - Run backtest for all cities/dates
  - Calculate metrics:
    - Mean Absolute Error (MAE)
    - Root Mean Squared Error (RMSE)
    - Calibration curve (predicted prob vs actual freq)
    - Brier score (mean squared error)
  - Output: CSV file `backtest_results_{date}.csv`
  - Output: PNG chart with calibration curves

**Outputs**:
```
date,city,bracket,old_forecast_prob,new_forecast_prob,actual_outcome,old_error,new_error
2026-04-20,atlanta,40-50F,0.15,0.23,0,0.15,0.23
2026-04-20,atlanta,50-60F,0.45,0.52,1,0.55,0.48  ← actual was 52°F
...
```

#### 3.2 Add Prediction Logging
**File**: `app/weather.py` (in `compute_intelligent_consensus()`, ~line 483)  
**Purpose**: Log every prediction for later backtesting  
**Changes**:
- After final consensus computed, log to `predictions_log.json`:
  ```python
  log_entry = {
    "timestamp": datetime.now().isoformat(),
    "city": city,
    "date": date_str,
    "model_peaks": multi_model_peaks,
    "consensus_peak": consensus,
    "uncertainty": sigma,
    "brackets": brackets,  # With forecast_prob
    "method": "new_asymmetric" or "old_normal",
  }
  with open('predictions_log.json', 'a') as f:
    f.write(json.dumps(log_entry) + '\n')
  ```
- Keep log rolling (archive after 30 days)

#### 3.3 Create Validation Dashboard
**File**: `app/templates/weather.html` (NEW tab)  
**Component**: NEW `<div id="tab-backtest">`  
**Current State**: None  
**Changes**:
- Add tab: "📊 Model Performance"
- Display:
  - Last 7 days of predictions vs actuals (table)
  - Calibration curve (chart)
  - Overall accuracy metrics (MAE, RMSE, Brier)
  - Improvement vs old model (%)
- Button: "Download Full Report" (generates CSV)

#### 3.4 Manual Validation Checklist
**File**: `docs/VALIDATION_CHECKLIST.md` (NEW)  
**Content**:
```markdown
# Prediction Accuracy Validation Checklist

## Before Launch

### Unit Tests
- [ ] Asymmetric distribution produces probabilities summing to 100%
- [ ] Skewness parameter varies correctly with cloud cover (-1 to +1 range)
- [ ] Model bias correction applied only to configured models
- [ ] Thermal lag hour varies 1-2 hours by season

### Integration Tests
- [ ] Run analysis on 5 past dates (use archived PM data)
- [ ] Verify edge calculation: If forecast 60% and market 45%, show +15% edge
- [ ] Verify "BUY YES" recommendations appear when forecast > market
- [ ] Verify "BUY NO" recommendations appear when forecast < market

### Live Trading Tests
- [ ] Run app on today's date
- [ ] Cross-check displayed edges against live Polymarket (manual spot-check on 3 brackets)
- [ ] Verify "Last Updated" timestamp updates every 5 seconds
- [ ] Close app, verify PM polling stops

### Accuracy Tests
- [ ] Compare app prediction to actual temperature for 5 past dates
- [ ] Calibration: Do 80% confidence predictions hit 80% of the time?
- [ ] Check for false edges (brackets app shows 100% are actually impossible)

## Post-Launch (Continuous)
- [ ] Track actual vs predicted for each day
- [ ] Monitor edge profitability (if traders use recommendations)
- [ ] Adjust bias corrections based on quarterly reviews
```

---

## Implementation Schedule

| Phase | Task | Duration | Files | Priority |
|-------|------|----------|-------|----------|
| 1 | Thermal lag enhancement | 1 day | weather.py (1575) | HIGH |
| 1 | Asymmetric distribution | 2 days | weather.py (2154) | HIGH |
| 1 | Model bias correction | 1 day | weather.py (350) | MEDIUM |
| 1 | Ensemble weighting | 1 day | weather.py (384) | MEDIUM |
| 1 | Intraday Bayesian update | 1 day | weather.py (571) | MEDIUM |
| **Phase 1 Total** | | **6 days** | | |
| 2 | Polymarket polling | 1 day | weather.html (1204) | HIGH |
| 2 | Remove manual input | 1 day | weather.html (1850) | HIGH |
| 2 | Real-time edge display | 1 day | weather.html (NEW) | HIGH |
| 2 | Auto-calc function | 0.5 day | weather.html | MEDIUM |
| 2 | Market hours detection | 0.5 day | weather.html | MEDIUM |
| **Phase 2 Total** | | **4 days** | | |
| 3 | Backtesting framework | 2 days | backtest.py (NEW) | MEDIUM |
| 3 | Prediction logging | 0.5 day | weather.py | MEDIUM |
| 3 | Validation dashboard | 1 day | weather.html (NEW) | LOW |
| 3 | Manual validation | 1 day | docs (NEW) | HIGH |
| **Phase 3 Total** | | **4.5 days** | | |
| | **TOTAL** | **~14-15 days** | | |

---

## Testing Strategy

### Unit Tests (Phase 1)
```python
# Test asymmetric distribution
assert sum(bracket_probs) ≈ 100  # Probabilities sum to 100%
assert skew_normal(cloud_cover=5) has skewness > 0.5  # Clear day, positive skew
assert skew_normal(cloud_cover=95) has skewness < -0.5  # Cloudy day, negative skew

# Test bias correction
assert apply_bias("HRRR", 75, month="July", region="south") ≈ 73.1  # Summer HRRR runs hot
assert apply_bias("HRRR", 45, month="January", region="north") ≈ 46.2  # Winter HRRR runs cold
```

### Integration Tests (Phase 2)
```javascript
// Test auto-edge calculation
runAnalysis("NYC", "2026-04-25");
// Verify: if forecast=60% and market=45%, display "+15% edge"
assert(D.brackets[2].edge === 15);
```

### Backtesting (Phase 3)
```
Old Model (Normal Dist):    MAE = 2.3°F  |  Brier Score = 0.089
New Model (Asymmetric):     MAE = 1.8°F  |  Brier Score = 0.064
Improvement:               21.7% better   |  28% better
```

---

## Rollback Plan

If new predictions underperform (MAE worse than old model):
1. Set `use_old_model=True` in config
2. App falls back to normal distribution
3. All other improvements (async polling, UI) still work
4. Investigate bias corrections or asymmetric parameters

---

## Success Criteria

✅ **Phase 1 Complete**: 
- Prediction accuracy improves 15-25% (MAE decreases)
- Asymmetric distribution works for all 10+ cities
- Bias corrections applied without errors

✅ **Phase 2 Complete**:
- Polymarket odds auto-update every 5 seconds
- Edge calculations show within 5 seconds of market move
- Zero manual data entry required
- App polls only during market hours (8am-11pm)

✅ **Phase 3 Complete**:
- Backtesting validates accuracy improvements
- Calibration curve shows predictions match actual outcomes
- Manual spot-checks confirm edge calculations vs live Polymarket
- No false edges (impossible predictions)

---

## Known Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Skewed dist implementation bugs | Predictions way off | Unit tests before launch |
| PM API rate limiting (too many polls) | Fetch failures | Implement exponential backoff, cache |
| Model bias corrections wrong | Worse accuracy | Use published NWS/ECMWF bias reports |
| Market hours detection timezone issue | Polls stop at wrong time | Test with multiple timezones |
| Backtesting historical data unavailable | Can't validate | Use archived PM slugs from web |

---

## Next Steps

1. **Review & Approval**: User reviews this plan
2. **Phase 1 Implementation**: Start with thermal lag & asymmetric distribution
3. **Phase 2 Implementation**: Add Polymarket automation (requires Phase 1 completion)
4. **Phase 3 Implementation**: Validation & backtesting (continuous, not blocking)
5. **Launch**: Deploy to live traders once Phase 2 complete + basic Phase 3 tests pass

---

**Questions/Changes?** Note any concerns before starting implementation.
