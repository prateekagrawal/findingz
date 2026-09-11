from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FourVector:
    energy: float
    px: float
    py: float
    pz: float

    def __add__(self, other: FourVector) -> FourVector:
        return FourVector(
            self.energy + other.energy,
            self.px + other.px,
            self.py + other.py,
            self.pz + other.pz,
        )

    @property
    def mass2(self) -> float:
        return self.energy**2 - self.px**2 - self.py**2 - self.pz**2

    @property
    def mass(self) -> float:
        return math.sqrt(max(self.mass2, 0.0))

    @property
    def pt(self) -> float:
        return math.hypot(self.px, self.py)


def from_pt_eta_phi_m(pt: float, eta: float, phi: float, mass: float) -> FourVector:
    px = pt * math.cos(phi)
    py = pt * math.sin(phi)
    pz = pt * math.sinh(eta)
    momentum2 = px**2 + py**2 + pz**2
    energy = math.sqrt(momentum2 + mass**2)
    return FourVector(energy, px, py, pz)


def lorentz_boost(vector: FourVector, beta: tuple[float, float, float]) -> FourVector:
    beta_vec = np.asarray(beta, dtype=float)
    beta2 = float(beta_vec @ beta_vec)
    if beta2 >= 1.0:
        raise ValueError("Boost speed must be below the speed of light")
    if beta2 == 0.0:
        return vector
    gamma = 1.0 / math.sqrt(1.0 - beta2)
    momentum = np.array([vector.px, vector.py, vector.pz], dtype=float)
    beta_dot_p = float(beta_vec @ momentum)
    boosted_energy = gamma * (vector.energy + beta_dot_p)
    factor = ((gamma - 1.0) * beta_dot_p / beta2) + gamma * vector.energy
    boosted_momentum = momentum + factor * beta_vec
    return FourVector(boosted_energy, *boosted_momentum.tolist())


def event_vectors(row: pd.Series) -> list[FourVector]:
    return [
        from_pt_eta_phi_m(
            float(row[f"l{i}_pt"]),
            float(row[f"l{i}_eta"]),
            float(row[f"l{i}_phi"]),
            float(row[f"l{i}_mass"]),
        )
        for i in range(1, 3)
    ]


def sum_vectors(vectors: list[FourVector]) -> FourVector:
    total = FourVector(0.0, 0.0, 0.0, 0.0)
    for vector in vectors:
        total = total + vector
    return total


def rapidity(vector: FourVector) -> float:
    """Return true rapidity, with infinities contained at the physical boundary."""
    numerator = vector.energy + vector.pz
    denominator = vector.energy - vector.pz
    if numerator <= 0.0 or denominator <= 0.0:
        return math.copysign(float("inf"), vector.pz)
    return 0.5 * math.log(numerator / denominator)


def collins_soper_cosine(negative: FourVector, positive: FourVector, dilepton: FourVector) -> float:
    """Compute the charge-signed Collins-Soper polar-angle cosine.

    At a proton-proton collider the incoming quark direction is not known event by
    event, so this sign convention must not be interpreted as the quark direction.
    """
    root_two = math.sqrt(2.0)
    minus_plus = (negative.energy + negative.pz) / root_two
    minus_minus = (negative.energy - negative.pz) / root_two
    plus_plus = (positive.energy + positive.pz) / root_two
    plus_minus = (positive.energy - positive.pz) / root_two
    denominator = dilepton.mass * math.sqrt(dilepton.mass2 + dilepton.pt**2)
    if denominator <= 0.0:
        return float("nan")
    value = 2.0 * (minus_plus * plus_minus - minus_minus * plus_plus) / denominator
    return float(np.clip(value, -1.0, 1.0))


def add_ranked_lepton_observables(frame: pd.DataFrame) -> pd.DataFrame:
    """Rank the saved pair by pT without changing its stored order or charge convention."""
    output = frame.copy()
    if not {"l1_pt", "l2_pt"}.issubset(frame.columns):
        return output
    first_pt = pd.to_numeric(frame["l1_pt"], errors="coerce")
    second_pt = pd.to_numeric(frame["l2_pt"], errors="coerce")
    valid = np.isfinite(first_pt) & np.isfinite(second_pt)
    first_leads = first_pt >= second_pt  # Stable tie-break: stored lepton 1.
    for quantity in ("pt", "eta"):
        if not {f"l1_{quantity}", f"l2_{quantity}"}.issubset(frame.columns):
            continue
        first = pd.to_numeric(frame[f"l1_{quantity}"], errors="coerce")
        second = pd.to_numeric(frame[f"l2_{quantity}"], errors="coerce")
        output[f"leading_lepton_{quantity}"] = np.where(
            valid, np.where(first_leads, first, second), np.nan
        )
        output[f"subleading_lepton_{quantity}"] = np.where(
            valid, np.where(first_leads, second, first), np.nan
        )
    return output


def add_observables(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    derived: list[tuple[float, float, float, float, float, float]] = []
    for _, row in output.iterrows():
        vectors = event_vectors(row)
        total = sum_vectors(vectors)
        charges = [int(row[f"l{i}_charge"]) for i in range(1, 3)]
        if sorted(charges) != [-1, 1]:
            cos_theta_cs = float("nan")
        else:
            negative = vectors[charges.index(-1)]
            positive = vectors[charges.index(1)]
            cos_theta_cs = collins_soper_cosine(negative, positive, total)
        minimum_pt = min(float(row[f"l{i}_pt"]) for i in range(1, 3))
        maximum_abs_eta = max(abs(float(row[f"l{i}_eta"])) for i in range(1, 3))
        derived.append(
            (total.mass, total.pt, rapidity(total), cos_theta_cs, minimum_pt, maximum_abs_eta)
        )
    output[
        [
            "mll",
            "ptll",
            "rapidity_ll",
            "cos_theta_cs",
            "min_lepton_pt",
            "max_abs_lepton_eta",
        ]
    ] = derived
    return output
