from __future__ import annotations

import numpy as np

from findingz.lep import (
    LEPParameters,
    born_mumu_components_pb,
    born_mumu_differential_pb,
    forward_backward_asymmetry,
    make_lep_angular_figure,
    make_lep_lineshape_figure,
)


def test_components_sum_to_coherent_total() -> None:
    result = born_mumu_components_pb(np.array([80.0, 91.1876, 100.0]))
    expected = result["photon_pb"] + result["interference_pb"] + result["z_pb"]
    np.testing.assert_allclose(result["total_pb"], expected)


def test_z_peak_is_near_benchmark_mass() -> None:
    params = LEPParameters()
    energies = np.linspace(88.0, 94.0, 3001)
    result = born_mumu_components_pb(energies, params)
    peak_energy = energies[int(np.argmax(result["total_pb"]))]
    assert abs(peak_energy - params.m_z_gev) < 0.05
    assert float(np.max(result["total_pb"])) > 1500.0


def test_figure_has_theory_components() -> None:
    figure = make_lep_lineshape_figure(points=80)
    axis = figure.axes[0]
    labels = {line.get_label() for line in axis.lines}
    assert "coherent $\\gamma+Z$ prediction" in labels
    assert "$Z$ exchange alone" in labels
    assert "photon exchange alone" in labels


def test_differential_distribution_integrates_to_total() -> None:
    cosine = np.linspace(-1.0, 1.0, 10001)
    for energy in (80.0, 91.1876, 100.0):
        differential = born_mumu_differential_pb(energy, cosine)
        integrated = np.trapezoid(differential, cosine)
        total = float(born_mumu_components_pb(energy)["total_pb"])
        np.testing.assert_allclose(integrated, total, rtol=2.0e-8)


def test_forward_backward_asymmetry_matches_angular_integrals() -> None:
    cosine = np.linspace(-1.0, 1.0, 20001)
    differential = born_mumu_differential_pb(100.0, cosine)
    midpoint = len(cosine) // 2
    backward = np.trapezoid(differential[: midpoint + 1], cosine[: midpoint + 1])
    forward = np.trapezoid(differential[midpoint:], cosine[midpoint:])
    from_integrals = (forward - backward) / (forward + backward)
    expected = float(forward_backward_asymmetry(100.0))
    np.testing.assert_allclose(from_integrals, expected, rtol=2.0e-8)


def test_angular_figure_reports_selected_energies() -> None:
    figure = make_lep_angular_figure(energies_gev=(80.0, 91.1876, 100.0), points=80)
    assert len(figure.axes[0].lines) == 4  # three predictions plus cos(theta)=0 guide
    labels = {line.get_label() for line in figure.axes[0].lines}
    assert any("80.00" in label for label in labels)
    assert any("91.19" in label for label in labels)
    assert any("100.00" in label for label in labels)


def test_signed_interference_can_be_plotted_on_symlog_scale() -> None:
    figure = make_lep_lineshape_figure(
        points=80,
        show_interference=True,
        y_scale="symlog",
    )
    assert figure.axes[0].get_yscale() == "symlog"
    assert any("interference" in line.get_label() for line in figure.axes[0].lines)

