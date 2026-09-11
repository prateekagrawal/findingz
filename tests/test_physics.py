import math

import pandas as pd

from findingz.physics import (
    FourVector,
    add_observables,
    add_ranked_lepton_observables,
    from_pt_eta_phi_m,
    lorentz_boost,
)


def test_ranked_leptons_keep_eta_with_pt_and_preserve_saved_order():
    frame = pd.DataFrame({
        "l1_pt": [20., 50., 30., float("nan")],
        "l2_pt": [40., 10., 30., 20.],
        "l1_eta": [0.1, 0.2, 0.3, 0.4],
        "l2_eta": [-0.1, -0.2, -0.3, -0.4],
    })
    ranked = add_ranked_lepton_observables(frame)
    assert ranked.leading_lepton_pt.iloc[:3].tolist() == [40., 50., 30.]
    assert ranked.subleading_lepton_pt.iloc[:3].tolist() == [20., 10., 30.]
    assert ranked.leading_lepton_eta.iloc[:3].tolist() == [-0.1, 0.2, 0.3]
    assert ranked.subleading_lepton_eta.iloc[:3].tolist() == [0.1, -0.2, -0.3]
    assert pd.isna(ranked.leading_lepton_eta.iloc[3])
    pd.testing.assert_frame_equal(ranked[frame.columns], frame)
    assert "leading_lepton_pt" not in frame


def test_coordinate_conversion_preserves_mass() -> None:
    vector = from_pt_eta_phi_m(pt=42.0, eta=0.8, phi=-1.2, mass=0.10566)
    assert math.isclose(vector.mass, 0.10566, rel_tol=1e-10, abs_tol=1e-10)


def test_lorentz_boost_preserves_mass() -> None:
    vector = FourVector(10.0, 2.0, 3.0, 4.0)
    boosted = lorentz_boost(vector, (0.1, -0.05, 0.2))
    assert math.isclose(vector.mass2, boosted.mass2, rel_tol=1e-12, abs_tol=1e-12)


def test_zero_boost_returns_same_vector() -> None:
    vector = FourVector(5.0, 1.0, 2.0, 3.0)
    assert lorentz_boost(vector, (0.0, 0.0, 0.0)) == vector


def test_back_to_back_dilepton_reconstructs_mass_and_angle() -> None:
    frame = pd.DataFrame(
        [
            {
                "l1_pt": 45.0,
                "l1_eta": 0.0,
                "l1_phi": 0.0,
                "l1_mass": 0.0,
                "l1_charge": -1,
                "l2_pt": 45.0,
                "l2_eta": 0.0,
                "l2_phi": math.pi,
                "l2_mass": 0.0,
                "l2_charge": 1,
            }
        ]
    )
    observed = add_observables(frame).iloc[0]
    assert math.isclose(observed["mll"], 90.0, rel_tol=1e-12)
    assert math.isclose(observed["ptll"], 0.0, abs_tol=1e-12)
    assert math.isclose(observed["cos_theta_cs"], 0.0, abs_tol=1e-12)
