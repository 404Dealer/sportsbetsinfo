# Frontend UI Plan: SportsBetsInfo

## Philosophy

Your backend is about **honest, immutable timelines of belief**. The frontend should surface insights that no one else can see because no one else captures data this way.

**Core principle**: Every chart should answer a question that requires your event-sourced architecture to answer.

---

## Phase 1: Essential Actions (MVP)

Start with 3 actions that deliver immediate value:

### 1. One-Click Daily Snapshot
```
[ Collect Today's Games ]  →  Shows spinner  →  "Captured 8 games at 2:34 PM"
```
- Single button on dashboard
- Runs `collect-day --sport basketball_nba`
- Shows what was captured with timestamps

### 2. Edge Scanner
```
[ Find Edges ]  →  Table of games sorted by |delta|
```
- Runs analysis on latest snapshots
- Shows: Game | Kalshi % | Vegas % | Delta | Direction
- Color-coded: Green (>5%), Yellow (3-5%), Gray (<3%)

### 3. Score My Predictions
```
[ Evaluate ]  →  Report card with Brier/ROI/Win Rate
```
- One button to run evaluations
- Simple scorecard showing aggregate performance

---

## Phase 2: Unique Visualizations (What Others Can't See)

### Chart 1: "Belief Drift" Timeline
**Question it answers**: "How did my estimate of Team X winning change as game time approached?"

```
100% ─────────────────────────────────
     │                    ╭──── Kalshi
 75% │               ╭────╯
     │          ╭────╯ ╭──── Vegas (no-vig)
 50% │     ╭────╯──────╯
     │ ────╯
 25% │
     │
  0% ─────────────────────────────────
     10am   12pm   2pm   4pm   6pm  Tip
         S0    S1    S2    S3   S4
```

**Why it's unique**: Requires your immutable snapshot timeline. No one else saves "what Kalshi thought at 10am."

**Implementation**:
- X-axis: `snapshot.collected_at`
- Y-axis: `kalshi_implied_prob` and `vegas_home_prob` from each snapshot
- One line per source, per game
- Vertical marker at game time showing outcome

---

### Chart 2: "Market Disagreement Heatmap"
**Question it answers**: "Right now, which games have the biggest Kalshi/Vegas disagreement?"

```
           -10%  -5%   0%   +5%  +10%
           Vegas←    →Kalshi higher
Lakers     ████████░░░░░░░░░░░░░  +8.2%
Celtics    ░░░░░░░░░████░░░░░░░░  +2.1%
Warriors   ░░░░░░████████░░░░░░░  -4.5%
Heat       ░░░████████░░░░░░░░░░  -6.1%
```

**Why it's unique**: Real-time edge detection across all games at once.

**Implementation**:
- One row per game from latest analysis
- Color scale: Blue (Vegas higher) → Gray (aligned) → Orange (Kalshi higher)
- Click row to drill into belief drift timeline

---

### Chart 3: "Edge Accuracy Over Time"
**Question it answers**: "When I spotted a >3% edge, how often was I right?"

```
Win Rate %
100 ─────────────────────────────────
    │    ╭╮
 75 │ ───╯ ╰─╮  ╭──╮
    │        ╰──╯  ╰─── 58% lifetime
 50 │─────────────────────────────────
    │
 25 │
   ─────────────────────────────────
    Week1  Week2  Week3  Week4  Week5
```

**Why it's unique**: Requires the evaluation loop to exist. This is your system proving (or disproving) it has an edge.

**Implementation**:
- Rolling window of edge bets (>3% delta)
- Y-axis: win rate in that window
- Reference line at 50% (random)
- Cumulative line showing lifetime edge accuracy

---

### Chart 4: "Calibration Plot"
**Question it answers**: "When I said 70% confident, did that team win 70% of the time?"

```
Actual Win %
100 ─────────────────────────────╮
    │                        ╭──╯ Perfect
 80 │                    ╭──●╯    calibration
    │                ╭──●╯
 60 │            ╭──●╯
    │        ╭──●╯
 40 │    ╭──●╯
    │ ──●╯ Your predictions
 20 │──╯
    ─────────────────────────────
    20   40   60   80   100
         Predicted Prob %
```

**Why it's unique**: Needs historical predictions + outcomes. Your Brier score visualization.

**Implementation**:
- Bucket predictions: 0-20%, 20-40%, 40-60%, 60-80%, 80-100%
- Y-axis: actual win rate in each bucket
- Dots = your data, diagonal line = perfect calibration
- Deviation from diagonal = miscalibration

---

### Chart 5: "ROI Waterfall"
**Question it answers**: "If I had bet $1 on every edge signal, where would I be?"

```
Cumulative $
+20 ─────────────────────────────────
    │                              ╭─
+10 │                    ╭─────────╯
    │          ╭─────────╯
  0 ─────────────────────────────────
    │     ╭────╯
-10 │ ────╯
    │
-20 ─────────────────────────────────
     Jan1       Jan15        Jan30
```

**Why it's unique**: Combines edge signals + outcomes + odds. Full closed-loop.

**Implementation**:
- X-axis: chronological bets
- Y-axis: cumulative P&L
- Each step = one edge bet (+profit or -loss)
- Color: green segments (wins), red segments (losses)

---

## Phase 3: Data Automation Dashboard

### Auto-Collection Schedule
```
┌─────────────────────────────────────┐
│  Auto-Collection: ON               │
│  ─────────────────────────────────  │
│  Morning:   9:00 AM  ✓ Collected    │
│  Midday:   12:00 PM  ✓ Collected    │
│  Pre-game:  6:00 PM  ⏳ Pending     │
│  ─────────────────────────────────  │
│  Next run in: 2h 34m               │
└─────────────────────────────────────┘
```

**Implementation**:
- Cron job or systemd timer calling CLI
- Frontend shows schedule status
- WebSocket or polling for live updates

### Analysis Pipeline Status
```
┌───────────────────────────────────────────────┐
│  Pipeline Health                              │
│  ─────────────────────────────────────────    │
│  Snapshots:   48 today  │  1,247 total        │
│  Analyses:    12 today  │    892 total        │
│  Outcomes:     6 today  │    743 total        │
│  Evaluations:  6 today  │    698 total        │
│  ─────────────────────────────────────────    │
│  Edge Detection: 3 games above threshold      │
│  Last Run: 14 min ago                         │
└───────────────────────────────────────────────┘
```

---

## Technical Stack Recommendation

### Option A: FastAPI + HTMX (Simplest)
```
Backend:  FastAPI serving JSON endpoints + HTML partials
Frontend: HTMX for reactivity, minimal JS
Charts:   Chart.js or lightweight Plotly
```
- Pros: Reuses Python, minimal JS complexity, fast iteration
- Cons: Less interactive charts

### Option B: FastAPI + React (Most Flexible)
```
Backend:  FastAPI serving JSON API
Frontend: React/Vite + TanStack Query
Charts:   Recharts or D3.js
```
- Pros: Rich interactions, component reuse, ecosystem
- Cons: More complexity, separate build step

### Option C: Streamlit (Fastest MVP)
```
Single:   Streamlit app
Charts:   Built-in Plotly/Altair
```
- Pros: Prototype in hours, Python only
- Cons: Less customizable, harder to scale

**Recommendation**: Start with **Option A (FastAPI + HTMX)** for Phase 1-2. Migrate to React only if you need complex client-side state.

---

## API Endpoints Needed

```python
# Phase 1
GET  /api/status                    # Dashboard counts
POST /api/collect                   # Trigger snapshot collection
GET  /api/edges                     # Current edge opportunities
POST /api/evaluate                  # Trigger evaluation run
GET  /api/report                    # Aggregate performance

# Phase 2
GET  /api/games/{game_id}/timeline  # Belief drift data
GET  /api/heatmap                   # All games with deltas
GET  /api/calibration               # Bucketed accuracy data
GET  /api/roi/cumulative            # Waterfall data
GET  /api/edge-accuracy/rolling     # Win rate over time
```

---

## File Structure (FastAPI + HTMX)

```
src/sportsbetsinfo/
├── web/
│   ├── __init__.py
│   ├── app.py              # FastAPI app
│   ├── routes/
│   │   ├── api.py          # JSON endpoints
│   │   ├── pages.py        # HTML page routes
│   │   └── partials.py     # HTMX partial renders
│   ├── templates/
│   │   ├── base.html       # Layout
│   │   ├── dashboard.html  # Main dashboard
│   │   ├── partials/
│   │   │   ├── edge_table.html
│   │   │   ├── status_card.html
│   │   │   └── belief_chart.html
│   │   └── components/
│   │       └── charts.html
│   └── static/
│       ├── css/
│       └── js/
│           └── charts.js   # Chart.js setup
└── cli/
    └── commands.py         # Add: serve command
```

---

## Implementation Order

1. **Week 1**: Dashboard skeleton + status endpoint + collect button
2. **Week 2**: Edge scanner table with color coding
3. **Week 3**: Evaluate button + report card display
4. **Week 4**: Belief Drift chart for single game
5. **Week 5**: Market Disagreement heatmap
6. **Week 6**: Calibration plot + ROI waterfall
7. **Week 7**: Auto-collection scheduler UI
8. **Week 8**: Polish, mobile responsiveness

---

## What Makes This Different

Most betting UIs show:
- Current odds ❌ (commoditized)
- Line movement ❌ (everyone has this)
- "Sharp money" indicators ❌ (black box, unverifiable)

Your UI shows:
- **Time-series of your actual beliefs** ✓
- **Market disagreement you calculated** ✓
- **Closed-loop accuracy on your edge calls** ✓
- **Calibration proof of your probability estimates** ✓

The value is in **proving or disproving your edge with your own data**, not in showing what every other site already shows.
