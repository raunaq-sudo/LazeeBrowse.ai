---
name: financial-market-analysis-india
description: Analyze Indian financial markets including NSE, BSE, mutual funds, IPOs, and economic indicators. Extract real-time and historical data from financial platforms.
license: MIT
---

# Financial Market Analysis — India Skill

## When to Use
- User asks about Indian stock markets (Nifty, Sensex, individual stocks)
- User wants mutual fund analysis, SIP comparisons, or portfolio review
- User asks about IPOs, F&O, commodity markets, or economic indicators
- User wants technical or fundamental analysis of Indian companies

## Key Platforms

### Market Data
- **Moneycontrol** — `moneycontrol.com` — stocks, mutual funds, news, analysis
- **NSE India** — `nseindia.com` — official NSE data, indices, FO data
- **BSE India** — `bseindia.com` — official BSE data, corporate actions
- **Google Finance** — `google.com/finance` — quick quotes, charts

### Mutual Funds
- **AMFI** — `amfiindia.com` — NAV data, fund categories, ratings
- **Value Research** — `valueresearchonline.com` — fund analysis, rankings, ratings
- **Morningstar India** — `morningstar.in` — fund analysis, star ratings

### News & Analysis
- **Economic Times** — `economictimes.com` — market news, analysis
- **LiveMint** — `livemint.com` — business and market coverage
- **CNBC-TV18** — `cnbctv18.com` — market updates, expert opinions

### IPO
- **Chittorgarh** — `chittorgarh.com` — IPO details, subscription status, listing predictions
- **NSE IPO** — `nseindia.com/products-and-services/equity-market-ipos`

## Workflow

### 1. Understand the Request
Confirm with the user via `get_user_confirmation`:
- **What** — stock, index, mutual fund, IPO, sector, or economy-wide
- **Timeframe** — intraday, short-term, long-term
- **Depth** — quick check vs detailed analysis
- **Output** — summary, report, comparison, or data table

### 2. Data Collection

#### For Stocks
1. `open_url` to Moneycontrol or Google Finance
2. Search for the stock by name or symbol
3. `get_ui_schema` to find data elements
4. Extract:
   - Current price, day change, 52-week high/low
   - Market cap, PE ratio, EPS
   - Volume, average volume
   - Promoter holding, FII/DII data
   - Recent news and corporate actions
5. `scroll` to reach financials section
6. Extract quarterly/annual results if needed
7. `update_memory` with all data points

#### For Mutual Funds
1. `open_url` to Value Research or AMFI
2. Search by fund name or category
3. Extract:
   - NAV and NAV history
   - Fund category (equity/debt/hybrid)
   - AUM, expense ratio
   - 1Y, 3Y, 5Y returns
   - Benchmark comparison
   - Top holdings
   - Risk metrics (Sharpe ratio, standard deviation)
   - Morningstar/VR rating
4. `update_memory` with fund data

#### For IPOs
1. `open_url` to Chittorgarh IPO page
2. Find the specific IPO
3. Extract:
   - Company name, issue size, price band
   - Lot size, issue dates
   - Subscription status (day-wise)
   - Grey market premium (GMP)
   - Company financials and business description
   - Promoter background
   - Listing date and expected listing price
4. `update_memory` with IPO data

#### For Market Overview
1. `open_url` to NSE India or Moneycontrol market page
2. Extract:
   - Nifty 50, Sensex, Bank Nifty levels and change
   - Top gainers and losers
   - Sectoral indices performance
   - FII/DII flow data
   - India VIX
   - Put-Call ratio
3. Check economic calendar for events
4. `update_memory` with market snapshot

### 3. Analysis Patterns

#### Fundamental Analysis
- Compare PE ratio with sector average and historical range
- Check revenue and profit growth trends (quarterly and yearly)
- Review debt levels and interest coverage
- Check promoter holding changes
- Compare with peer companies

#### Technical Analysis (if data available)
- Note support and resistance levels from charts
- Check moving averages (if visible on page)
- Note volume patterns
- Identify trend (uptrend, downtrend, consolidation)

#### Mutual Fund Comparison
- Compare returns across similar category funds
- Check consistency of performance
- Compare expense ratios
- Review portfolio overlap if comparing multiple funds
- Check fund manager track record

### 4. Compile Report
1. `read_memory` to gather all data
2. `write_file` a structured report:

```markdown
# Financial Analysis: <Subject>

## Overview
<Current status and key numbers>

## Key Metrics
| Metric | Value | Benchmark/Average |
|--------|-------|-------------------|
| ... | ... | ... |

## Analysis
<Detailed analysis with data backing>

## Risks
<Key risks to consider>

## Sources
1. <URL> — <data retrieved>
```

## Rules
- **Never give buy/sell recommendations** — present data and let the user decide
- Always note the date and time of data (markets change rapidly)
- Distinguish between real-time data and delayed data
- If data is not available for a metric, say so explicitly
- Note when data is from a premium/restricted source that required login
- If a platform requires login, pause and ask the user
- Cross-verify critical numbers (stock price, NAV) across 2 sources when possible
- Always mention that this is not financial advice
