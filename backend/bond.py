"""
Annual-compounding zero-coupon duration and DV01.
"""
import math


def validate_bond_inputs(yield_pct: float, tenor_years: float) -> None:
    if not math.isfinite(yield_pct) or yield_pct <= -100:
        raise ValueError('Yield must be finite and greater than -100%.')
    if not math.isfinite(tenor_years) or tenor_years < 0:
        raise ValueError('Tenor must be finite and nonnegative.')

def calculate_duration(yield_pct: float, tenor_years: float) -> float:
    """
    Calculate modified duration for an annual-compounding zero-coupon bond.
    
    Modified Duration = Maturity / (1 + decimal yield)
    
    Args:
        yield_pct: Yield in percentage (e.g., 5.0 for 5%)
        tenor_years: Time to maturity in years
    
    Returns:
        Modified duration in years
    """
    validate_bond_inputs(yield_pct, tenor_years)
    if tenor_years == 0:
        return 0.0
    
    yield_decimal = yield_pct / 100.0
    return tenor_years / (1.0 + yield_decimal)


def calculate_dv01(yield_pct: float, tenor_years: float) -> float:
    """
    Calculate DV01 (dollar value of 1 basis point) for a zero-coupon bond.
    
    DV01 = Price × Modified Duration × 0.0001
    
    For a $100 face value zero-coupon bond:
    Price = 100 / (1 + decimal yield)^tenor
    
    Args:
        yield_pct: Yield in percentage (e.g., 5.0 for 5%)
        tenor_years: Time to maturity in years
    
    Returns:
        DV01 in dollars per basis point (for $100 face value)
    """
    validate_bond_inputs(yield_pct, tenor_years)
    if tenor_years == 0:
        return 0.0
    
    yield_decimal = yield_pct / 100.0
    
    # Zero-coupon bond price
    price = 100.0 / ((1.0 + yield_decimal) ** tenor_years)
    
    # Modified duration
    mod_duration = calculate_duration(yield_pct, tenor_years)
    
    # DV01 = Price × ModDur × 0.0001 (1 basis point = 0.01%)
    return price * mod_duration * 0.0001
