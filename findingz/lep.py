from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from matplotlib.figure import Figure

GEV2_TO_PB = 0.389379338e9


@dataclass(frozen=True)
class LEPParameters:
    """Fixed teaching benchmark for the tree-level LEP dimuon scan."""

    m_z_gev: float = 91.1876
    gamma_z_gev: float = 2.4952
    sin2_theta_w: float = 0.23122
    alpha_em: float = 1.0 / 128.0
    q_e: float = -1.0
    q_mu: float = -1.0

    @property
    def cos2_theta_w(self) -> float:
        return 1.0 - self.sin2_theta_w

    @property
    def kappa(self) -> float:
        return 1.0 / (4.0 * self.sin2_theta_w * self.cos2_theta_w)

    @property
    def v_lepton(self) -> float:
        return -0.5 + 2.0 * self.sin2_theta_w

    @property
    def a_lepton(self) -> float:
        return -0.5


def born_mumu_components_pb(
    sqrt_s_gev: np.ndarray | list[float] | float,
    parameters: LEPParameters | None = None,
) -> dict[str, np.ndarray]:
    """Return photon, gamma-Z interference, Z, and coherent Born cross sections.

    The calculation is for unpolarized, massless external leptons and retains the
    finite-width Z propagator. It does not use the narrow-width approximation or
    replace the explicit vertices by partial widths.
    """

    params = parameters or LEPParameters()
    energy = np.asarray(sqrt_s_gev, dtype=float)
    if np.any(energy <= 0.0):
        raise ValueError("Center-of-mass energies must be positive")

    s = energy**2
    delta_z = s - params.m_z_gev**2
    denominator = delta_z**2 + (params.m_z_gev * params.gamma_z_gev) ** 2
    v_e = v_mu = params.v_lepton
    a_e = a_mu = params.a_lepton

    prefactor_pb = 4.0 * np.pi * params.alpha_em**2 / (3.0 * s) * GEV2_TO_PB
    photon_factor = params.q_e**2 * params.q_mu**2 * np.ones_like(s)
    interference_factor = (
        2.0 * params.q_e * params.q_mu * v_e * v_mu * params.kappa * s * delta_z / denominator
    )
    z_factor = (v_e**2 + a_e**2) * (v_mu**2 + a_mu**2) * params.kappa**2 * s**2 / denominator

    photon = prefactor_pb * photon_factor
    interference = prefactor_pb * interference_factor
    z_exchange = prefactor_pb * z_factor
    return {
        "sqrt_s_gev": energy,
        "photon_pb": photon,
        "interference_pb": interference,
        "z_pb": z_exchange,
        "total_pb": photon + interference + z_exchange,
    }


def born_mumu_structure_functions(
    sqrt_s_gev: np.ndarray | list[float] | float,
    parameters: LEPParameters | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Return the parity-even F1 and parity-odd F2 angular coefficients."""

    params = parameters or LEPParameters()
    energy = np.asarray(sqrt_s_gev, dtype=float)
    if np.any(energy <= 0.0):
        raise ValueError("Center-of-mass energies must be positive")

    s = energy**2
    delta_z = s - params.m_z_gev**2
    denominator = delta_z**2 + (params.m_z_gev * params.gamma_z_gev) ** 2
    v_e = v_mu = params.v_lepton
    a_e = a_mu = params.a_lepton
    re_chi = params.kappa * s * delta_z / denominator
    abs_chi_sq = params.kappa**2 * s**2 / denominator

    f1 = (
        params.q_e**2 * params.q_mu**2
        + 2.0 * params.q_e * params.q_mu * v_e * v_mu * re_chi
        + (v_e**2 + a_e**2) * (v_mu**2 + a_mu**2) * abs_chi_sq
    )
    f2 = (
        2.0 * params.q_e * params.q_mu * a_e * a_mu * re_chi
        + 4.0 * v_e * a_e * v_mu * a_mu * abs_chi_sq
    )
    return f1, f2


def born_mumu_differential_pb(
    sqrt_s_gev: float,
    cos_theta: np.ndarray | list[float] | float,
    parameters: LEPParameters | None = None,
) -> np.ndarray:
    """Return d sigma / d cos(theta) in pb for one scan energy."""

    params = parameters or LEPParameters()
    if sqrt_s_gev <= 0.0:
        raise ValueError("Center-of-mass energy must be positive")
    cosine = np.asarray(cos_theta, dtype=float)
    if np.any(np.abs(cosine) > 1.0):
        raise ValueError("cos(theta) must lie between -1 and 1")
    f1, f2 = born_mumu_structure_functions(sqrt_s_gev, params)
    s = float(sqrt_s_gev) ** 2
    prefactor_pb = np.pi * params.alpha_em**2 / (2.0 * s) * GEV2_TO_PB
    return prefactor_pb * ((1.0 + cosine**2) * f1 + 2.0 * cosine * f2)


def forward_backward_asymmetry(
    sqrt_s_gev: np.ndarray | list[float] | float,
    parameters: LEPParameters | None = None,
) -> np.ndarray:
    """Return the tree-level unpolarized forward-backward asymmetry."""

    f1, f2 = born_mumu_structure_functions(sqrt_s_gev, parameters)
    return 0.75 * f2 / f1


def make_lep_lineshape_figure(
    parameters: LEPParameters | None = None,
    energy_min_gev: float = 75.0,
    energy_max_gev: float = 110.0,
    points: int = 700,
    show_total: bool = True,
    show_photon: bool = True,
    show_z: bool = True,
    show_interference: bool = False,
    y_scale: Literal["log", "linear", "symlog"] = "log",
) -> Figure:
    """Create the deterministic lepton-collider lineshape plot used by the course."""

    params = parameters or LEPParameters()
    energies = np.linspace(energy_min_gev, energy_max_gev, points)
    result = born_mumu_components_pb(energies, params)

    figure = Figure(figsize=(8.6, 5.1))
    axis = figure.subplots()
    if show_total:
        axis.plot(
            result["sqrt_s_gev"],
            result["total_pb"],
            color="#245A9B",
            linewidth=3.0,
            label=r"coherent $\gamma+Z$ prediction",
        )
    if show_z:
        axis.plot(
            result["sqrt_s_gev"],
            result["z_pb"],
            color="#B35A00",
            linewidth=1.8,
            linestyle="--",
            label=r"$Z$ exchange alone",
        )
    if show_photon:
        axis.plot(
            result["sqrt_s_gev"],
            result["photon_pb"],
            color="#555555",
            linewidth=1.8,
            linestyle=":",
            label=r"photon exchange alone",
        )
    if show_interference:
        axis.plot(
            result["sqrt_s_gev"],
            result["interference_pb"],
            color="#7A3E9D",
            linewidth=2.0,
            linestyle="-.",
            label=r"signed $\gamma$-$Z$ interference",
        )
        axis.axhline(0.0, color="#777777", linewidth=0.8)
    axis.axvline(params.m_z_gev, color="#777777", linewidth=1.0, alpha=0.65)
    axis.annotate(
        rf"$M_Z={params.m_z_gev:.4f}\ \mathrm{{GeV}}$",
        xy=(params.m_z_gev, 0.96),
        xycoords=("data", "axes fraction"),
        xytext=(7, 0),
        textcoords="offset points",
        ha="left",
        va="top",
        color="#333333",
    )
    if y_scale == "symlog":
        axis.set_yscale("symlog", linthresh=1.0)
    else:
        axis.set_yscale(y_scale)
    axis.set_xlim(energy_min_gev, energy_max_gev)
    if y_scale == "log":
        axis.set_ylim(5.0, 3000.0)
    axis.set_xlabel(r"center-of-mass energy $\sqrt{s}$ [GeV]")
    axis.set_ylabel(r"Born cross section $\sigma_{\mu\mu}$ [pb]")
    axis.set_title(r"Finding Z tool: $e^-e^+\rightarrow\gamma^*/Z\rightarrow\mu^-\mu^+$")
    axis.grid(which="both", alpha=0.18)
    axis.legend(frameon=False, loc="upper right")
    axis.text(
        0.02,
        0.04,
        (
            "Fixed teaching benchmark: massless leptons, finite-width Z propagator, "
            "no ISR, beam spread, or detector response"
        ),
        transform=axis.transAxes,
        fontsize=8.5,
        color="#444444",
    )
    figure.tight_layout()
    return figure


def make_lep_angular_figure(
    parameters: LEPParameters | None = None,
    energies_gev: tuple[float, ...] | None = None,
    points: int = 300,
) -> Figure:
    """Create angular distributions and report A_FB at selected scan energies."""

    params = parameters or LEPParameters()
    energies = energies_gev or (80.0, params.m_z_gev, 100.0)
    cosine = np.linspace(-1.0, 1.0, points)
    figure = Figure(figsize=(8.6, 5.1))
    axis = figure.subplots()
    colors = ("#555555", "#245A9B", "#B35A00", "#2A7F62")
    for index, energy in enumerate(energies):
        differential = born_mumu_differential_pb(energy, cosine, params)
        asymmetry = float(forward_backward_asymmetry(energy, params))
        axis.plot(
            cosine,
            differential,
            linewidth=2.4,
            color=colors[index % len(colors)],
            label=rf"$\sqrt{{s}}={energy:.2f}$ GeV, $A_{{FB}}={asymmetry:+.3f}$",
        )
    axis.set_xlabel(r"$\cos\theta$ for the outgoing $\mu^-$")
    axis.set_ylabel(r"$d\sigma/d\cos\theta$ [pb]")
    axis.set_title("Finding Z tool: angular distributions")
    axis.axvline(0.0, color="#777777", linewidth=0.8)
    axis.grid(alpha=0.2)
    axis.legend(frameon=False)
    figure.tight_layout()
    return figure
