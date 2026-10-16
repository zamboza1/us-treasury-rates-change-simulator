"""
Daily US Treasury par yields and basis-point shock scenarios.
"""
import requests
import time
import csv
import io
import math
from datetime import datetime, timezone
from typing import Dict, Tuple

# Cache mechanism with 3600s TTL (1 hour)
_CURVE_CACHE = {
    'timestamp': 0,
    'data': None
}

CACHE_TTL = 3600  # 1 hour

TENORS = {
    '1 Mo': 1 / 12, '1.5 Month': 1.5 / 12, '1.5 Mo': 1.5 / 12,
    '2 Mo': 2 / 12, '3 Mo': .25, '4 Mo': 4 / 12, '6 Mo': .5,
    '1 Yr': 1., '2 Yr': 2., '3 Yr': 3., '5 Yr': 5., '7 Yr': 7.,
    '10 Yr': 10., '20 Yr': 20., '30 Yr': 30.,
}


def parse_curve_csv(text: str) -> Tuple[str, Dict[float, float]]:
    """Select the latest dated, usable row; never combine observation dates."""
    reader = csv.DictReader(io.StringIO(text.strip().lstrip('\ufeff')))
    if not reader.fieldnames:
        raise ValueError('CSV is empty')
    reader.fieldnames = [name.strip() for name in reader.fieldnames]
    if 'Date' not in reader.fieldnames:
        raise ValueError('CSV has no Date column')
    observations = []
    for row in reader:
        try:
            observed = datetime.strptime((row.get('Date') or '').strip(), '%m/%d/%Y')
        except ValueError:
            continue
        rates = {}
        for name, tenor in TENORS.items():
            try:
                value = float(row.get(name) or '')
            except (ValueError, TypeError):
                continue
            if math.isfinite(value) and value > -100:
                rates[tenor] = value
        if rates:
            observations.append((observed, rates))
    if not observations:
        raise ValueError('CSV has no usable dated yield rows')
    observed, rates = max(observations, key=lambda item: item[0])
    return observed.strftime('%m/%d/%Y'), dict(sorted(rates.items()))


def get_curve_status() -> dict:
    """Describe cache freshness separately from the Treasury observation date."""
    timestamp = _CURVE_CACHE['timestamp']
    return {
        'cache_status': 'fresh' if time.time() - timestamp < CACHE_TTL else 'stale',
        'fetched_at': datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
    }


def get_curve() -> Tuple[str, Dict[float, float]]:
    """
    Fetch the latest usable daily par yields from the official Treasury CSV.
    Returns: (date_str, {tenor: yield_pct})
    
    Cache results for one hour; return stale data if a refresh fails.
    """
    now = time.time()
    
    # Return fresh cache if available
    if _CURVE_CACHE['data'] and (now - _CURVE_CACHE['timestamp']) < CACHE_TTL:
        return _CURVE_CACHE['data']
    
    try:
        # Try current year first, then fallback to previous year (e.g. early January)
        current_year = datetime.now().year
        years_to_try = [current_year, current_year - 1]
        
        for year in years_to_try:
            try:
                url = f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve&field_tdr_date_value={year}&page&_format=csv"
                # Add User-Agent header to avoid being blocked
                headers = {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                
                resp = requests.get(url, headers=headers, timeout=30)
                resp.raise_for_status()
                data = parse_curve_csv(resp.text)
                _CURVE_CACHE['timestamp'] = time.time()
                _CURVE_CACHE['data'] = data
                return data
            except Exception as e:
                print(f"Failed to fetch data for {year}: {e}")
                continue
        
        raise ValueError('Could not fetch usable Treasury data for current or previous year.')
        
    except Exception as e:
        print(f"Treasury API error: {e}")
        
        # Return stale cache if available
        if _CURVE_CACHE['data']:
            print("Returning stale cached data")
            return _CURVE_CACHE['data']
        
        # No fallback data - raise error
        raise Exception(f"Unable to fetch Treasury data: {str(e)}. No cached data available.")


def apply_parallel_shock(curve: Dict[float, float], magnitude_bps: float) -> Dict[float, float]:
    """
    Apply a parallel shift to the entire yield curve.
    
    Args:
        curve: {tenor: yield_pct}
        magnitude_bps: Shift in basis points (+100 adds 1 percentage point)
    
    Returns:
        Percentage yields with magnitude_bps / 100 added to each maturity
    """
    shift_pct = magnitude_bps / 100.0
    return {tenor: yld + shift_pct for tenor, yld in curve.items()}


def apply_steepener(curve: Dict[float, float], magnitude_bps: float, pivot_tenor: float = 2.0) -> Dict[float, float]:
    """
    Apply a steepener/flattener twist around a pivot point.
    
    The pivot point stays unchanged. Points before the pivot move opposite
    to points after the pivot, creating a twist effect.
    
    Args:
        curve: {tenor: yield_pct}
        magnitude_bps: Change at the longest maturity in bps (+100 adds 1 percentage point)
        pivot_tenor: The tenor that remains unchanged (default 2.0 years)
    
    Returns:
        Shocked curve with twist applied
    """
    if not curve:
        return {}
    if not math.isfinite(pivot_tenor) or not 0 < pivot_tenor < max(curve):
        raise ValueError('Pivot must be positive and below the longest available tenor.')
    shift_pct = magnitude_bps / 100.0
    
    max_tenor = max(curve.keys())
    
    result = {}
    for tenor, yld in curve.items():
        if tenor <= pivot_tenor:
            # Short end: inverse weight (from -1 at t=0 to 0 at pivot)
            weight = -(pivot_tenor - tenor) / pivot_tenor
        else:
            # Long end: positive weight (from 0 at pivot to 1 at max tenor)
            weight = (tenor - pivot_tenor) / (max_tenor - pivot_tenor)
        
        result[tenor] = yld + (weight * shift_pct)
    
    return result


def apply_custom_shock(curve: Dict[float, float], custom_shocks: Dict[float, float]) -> Dict[float, float]:
    """
    Apply custom shocks to specific tenors.
    
    Args:
        curve: {tenor: yield_pct}
        custom_shocks: {tenor: shock_bps}
    
    Returns:
        Shocked curve with specified tenors adjusted
    """
    result = curve.copy()
    for tenor, shock_bps in custom_shocks.items():
        if tenor in result:
            result[tenor] += shock_bps / 100.0
    return result
