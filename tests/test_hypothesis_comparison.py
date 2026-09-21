import math
import pandas as pd
import pytest
from findingz.counting import compare_hypotheses


def events(yield_):
    return pd.DataFrame({"weight": [yield_]})


@pytest.mark.parametrize("n0,n1,delta,z", [(100,150,50,4.6518310838), (100,100,0,0), (100,80,-20,-math.sqrt(2*(80*math.log(.8)+20)))])
def test_complete_predictions_are_subtracted(n0,n1,delta,z):
    result = compare_hypotheses(events(n0),events(n1))
    assert result.null_yield == n0
    assert result.alternative_yield == n1
    assert result.difference == delta
    assert result.signed_significance == pytest.approx(z)


def test_uncertainty_and_zero_null():
    result = compare_hypotheses(events(100),events(150),null_uncertainty_fraction=.1)
    fitted = math.sqrt(15000)
    expected = math.sqrt(2*(150*math.log(150/fitted)+fitted-150)+(fitted-100)**2/100)
    assert result.signed_significance == pytest.approx(expected)
    assert result.signed_significance < compare_hypotheses(events(100), events(150)).signed_significance
    assert compare_hypotheses(events(0),events(10)).signed_significance is None
    with pytest.raises(ValueError):
        compare_hypotheses(events(1),events(2),null_uncertainty_fraction=float("nan"))


def test_test4_test5_ee_regression():
    result = compare_hypotheses(events(283435.2),events(313314.),null_uncertainty_fraction=.1)
    assert result.difference == pytest.approx(29878.8)
    assert 1.05 < result.signed_significance < 1.06


@pytest.mark.parametrize("uncertainty", [0, .1, 1.])
def test_zero_alternative_and_identical_predictions(uncertainty):
    assert compare_hypotheses(events(10), events(0), null_uncertainty_fraction=uncertainty).signed_significance < 0
    assert compare_hypotheses(events(10), events(10), null_uncertainty_fraction=uncertainty).signed_significance == pytest.approx(0, abs=1e-7)


def test_large_resonant_excess_is_not_gaussian_shortcut():
    result = compare_hypotheses(events(.58), events(13.12))
    assert result.signed_significance == pytest.approx(math.sqrt(2*(13.12*math.log(13.12/.58)-13.12+.58)))
    assert result.signed_significance < (13.12-.58)/math.sqrt(.58)
