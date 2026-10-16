# US Treasury Rates Change Simulator

I built this simulator to better understand yield curve risk. It loads daily US Treasury par yields and lets you compare parallel shifts, steepeners and custom shocks.

## How It Works

Python FastAPI fetches the Treasury CSV, caches observations for one hour and calculates scenario yields, modified duration and DV01. React, Tailwind and Chart.js provide the controls and chart.

- **Parallel:** add the same shock to every available maturity.
- **Steepener:** twist the curve around 2 years. The pivot stays unchanged; shorter maturities move in the opposite direction to longer maturities. The requested shock applies at the longest available maturity. A negative shock flattens the curve.
- **Custom:** adjust the 2-, 5-, 10- and 30-year points individually. The API accepts other available maturities.

Yields are percentages: `5` means 5%. Shocks are basis points: `+100 bps` adds one percentage point. Displayed changes compare the scenario with its baseline, not with the previous trading day. Negative scenario yields are allowed.

## Data and Model

The source is the [Treasury daily par yield curve](https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve). The parser supports 14 maturities, including 1.5 months, and selects the latest usable dated row. Missing observations remain missing; values from different dates are not combined. If the current year's response is unusable, it tries the previous year. A failed refresh can return a labeled stale cache. The displayed date is the observation date.

The API's risk measures describe an illustrative zero-coupon bond with annual compounding and $100 face value, evaluated at the shocked yield:

```text
Price             = 100 / (1 + y)^T
Modified duration = T / (1 + y)
DV01              = Price × Modified duration × 0.0001
```

Here, `y` is decimal yield and `T` is maturity in years. Duration is in years; DV01 is dollars per basis point for $100 face value. Yields at or below -100% are outside this model's domain.

Treasury par yields are used as proxies, not bootstrapped spot rates. These measures do not price coupon-bearing Treasury bonds, which [pay interest semiannually](https://www.treasurydirect.gov/marketable-securities/understanding-pricing/). Coupon schedules, accrued interest, convexity and portfolio P&L are not implemented. Chart maturities use categorical spacing; smooth lines are visual guides, not modeled intermediate yields.

## Run It Yourself

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
./start.sh
```

Open [the simulator](http://127.0.0.1:3001/?apiPort=8081). The launcher binds locally and refuses occupied ports. To run a separate instance:

```bash
BACKEND_PORT=8097 FRONTEND_PORT=3097 ./start.sh
```

Alternatively, run the servers separately:

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8081
python -m http.server 3001 --bind 127.0.0.1 --directory frontend
```

The frontend accepts `?apiPort=...` or `window.TREASURY_API_BASE` set before the app script. React 18, Babel 6, Tailwind, Chart.js and fonts load from external CDNs, so the browser needs internet access. There is no frontend build step or dependency lockfile.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Tests cover synthetic feeds, network failures, scenario validation, shock references and independent finite-difference risk checks. Live feed availability and browser workflows require separate integration checks.

License: MIT.
