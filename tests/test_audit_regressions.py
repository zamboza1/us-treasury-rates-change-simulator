"""Synthetic edge cases and independent finite-difference risk checks."""
import math
from decimal import Decimal, localcontext
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from backend import curve
from backend.bond import calculate_duration, calculate_dv01
from backend.main import app


@pytest.fixture(autouse=True)
def isolated_cache():
    saved = curve._CURVE_CACHE.copy()
    curve._CURVE_CACHE.update(timestamp=0, data=None)
    yield
    curve._CURVE_CACHE.clear()
    curve._CURVE_CACHE.update(saved)


def test_parse_all_maturities_and_latest_date():
    text = ('Date,1 Mo,1.5 Month,2 Mo,3 Mo,4 Mo,6 Mo,1 Yr,2 Yr,3 Yr,5 Yr,7 Yr,10 Yr,20 Yr,30 Yr\n'
            '01/02/2026,1,2,3,4,5,6,7,8,9,10,11,12,13,14\n'
            '01/05/2026,2,3,4,5,6,7,8,9,10,11,12,13,14,15\n')
    date, rates = curve.parse_curve_csv(text)
    assert date == '01/05/2026'
    assert len(rates) == 14
    assert rates[.125] == 3
    assert rates[30] == 15


def test_missing_values_stay_missing_without_mixing_dates():
    date, rates = curve.parse_curve_csv('Date,2 Yr,10 Yr,30 Yr\n01/05/2026,ND,5,N/A\n01/02/2026,4,4.5,5\n')
    assert date == '01/05/2026'
    assert rates == {10.: 5.}


@pytest.mark.parametrize('text', ['', 'Date,2 Yr\n', '<html>outage</html>',
    'Date,2 Yr,10 Yr\n01/05/2026,ND,N/A\n', 'Date,2 Yr,10 Yr\n01/05/2026,NaN,Infinity\n',
    'Date,2 Yr\ninvalid,5\n'])
def test_unusable_feeds_rejected(text):
    with pytest.raises(ValueError):
        curve.parse_curve_csv(text)


def test_empty_current_year_tries_previous_year():
    with patch('backend.curve.requests.get', side_effect=[Mock(text='Date,2 Yr\n'),
         Mock(text='Date,2 Yr\n12/31/2025,4.2\n')]) as request:
        assert curve.get_curve() == ('12/31/2025', {2.: 4.2})
    assert request.call_count == 2


def test_invalid_feed_does_not_replace_stale_cache():
    curve._CURVE_CACHE['data'] = ('12/31/2025', {2.:4.2})
    with patch('backend.curve.requests.get', return_value=Mock(text='Date,2 Yr\n')):
        assert curve.get_curve() == ('12/31/2025', {2.:4.2})
    assert curve.get_curve_status()['cache_status'] == 'stale'


def test_fresh_cache_does_not_fetch():
    with patch('backend.curve.time.time', return_value=1000), patch('backend.curve.requests.get') as request:
        curve._CURVE_CACHE.update(timestamp=999, data=('12/31/2025', {2.:4.2}))
        assert curve.get_curve()[1] == {2.:4.2}
        assert curve.get_curve_status()['cache_status'] == 'fresh'
        request.assert_not_called()


def test_parallel_and_twist_exact_units():
    original = {.5:5.,2.:4.5,10.:4.,30.:4.2}
    assert curve.apply_parallel_shock(original,100)[10] == 5.
    assert curve.apply_parallel_shock(original,-50)[2] == 4.
    twisted = curve.apply_steepener(original,100)
    assert (twisted[.5]-original[.5])*100 == pytest.approx(-75)
    assert twisted[2] == original[2]
    assert (twisted[10]-original[10])*100 == pytest.approx(100*8/28)
    assert (twisted[30]-original[30])*100 == pytest.approx(100)
    assert original == {.5:5.,2.:4.5,10.:4.,30.:4.2}
    assert curve.apply_steepener({},100) == {}


@pytest.mark.parametrize('yield_pct,tenor', [(0,10),(5,10),(-1,30),(4,.125),(100,2)])
def test_risk_matches_independent_price_derivative(yield_pct,tenor):
    # Differentiate high-precision discounted terminal cash flows numerically.
    with localcontext() as ctx:
        ctx.prec = 50
        y, t, h = Decimal(str(yield_pct))/100, Decimal(str(tenor)), Decimal('0.0000001')
        pv = lambda rate: Decimal(100) * ((1 + rate).ln() * -t).exp()
        derivative = (pv(y-h)-pv(y+h))/(2*h)
        assert calculate_duration(yield_pct,tenor) == pytest.approx(float(derivative/pv(y)),rel=1e-9)
        assert calculate_dv01(yield_pct,tenor) == pytest.approx(float(derivative/10000),rel=1e-9)


@pytest.mark.parametrize('yield_pct,tenor', [(-100,10),(-101,2),(math.nan,1),(math.inf,1),(4,-1),(4,math.inf)])
def test_invalid_risk_domain(yield_pct,tenor):
    for function in (calculate_duration,calculate_dv01):
        with pytest.raises(ValueError):
            function(yield_pct,tenor)


@pytest.fixture
def client():
    with patch('backend.main.get_curve',return_value=('01/05/2026',{.5:3.,2.:4.,10.:5.,30.:5.5})):
        yield TestClient(app,raise_server_exceptions=False)


@pytest.mark.parametrize('body', [
    {'type':'invalid'}, {'type':'parallel','magnitude':'Infinity'},
    {'type':'parallel','magnitude':'NaN'}, {'type':'steepener','pivot':0},
    {'type':'steepener','pivot':-2}, {'type':'steepener','pivot':30},
    {'type':'steepener','pivot':31}, {'type':'steepener','pivot':None},
    {'type':'custom','custom_shocks':{'10':-10500}},
    {'type':'custom','custom_shocks':{'10':-11000}},
    {'type':'custom','custom_shocks':{'9':20}},
    {'type':'custom','custom_shocks':{'NaN':20}},
    {'type':'custom','custom_shocks':{'10':'Infinity'}},
    {'type':'parallel','magnitude':1e308},
])
def test_invalid_scenarios_are_422(client,body):
    response=client.post('/api/analyze',json=body)
    assert response.status_code == 422
    assert response.json()['detail']


@pytest.mark.parametrize('number', ['1e309', '-1e309', 'NaN', 'Infinity'])
def test_nonfinite_json_numbers_do_not_break_error_serialization(client, number):
    response = client.post('/api/analyze',
        content='{"type":"parallel","magnitude":' + number + '}',
        headers={'Content-Type':'application/json'})
    assert response.status_code == 422
    assert response.json()['detail']


def test_negative_yields_and_missing_zero_shocks_are_valid(client):
    response=client.post('/api/analyze',json={'type':'custom','custom_shocks':{'2':-500,'9':0}})
    assert response.status_code == 200
    payload=response.json()
    assert payload['metrics']['2.0']['yield'] == -1
    assert payload['metrics']['2.0']['delta_bps'] == -500
    assert payload['risk_model']['compounding'] == 'annual'
    assert payload['risk_model']['face_value_usd'] == 100


def test_feed_outage_and_empty_curve_are_503():
    client=TestClient(app)
    for mocked in [patch('backend.main.get_curve',side_effect=RuntimeError('offline')),
                   patch('backend.main.get_curve',return_value=('01/05/2026',{}))]:
        with mocked:
            assert client.get('/api/curve').status_code == 503
            assert client.post('/api/analyze',json={'type':'parallel'}).status_code == 503
