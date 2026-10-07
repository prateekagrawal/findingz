"""Beam presets shared by course catalogues and the MadGraph run configuration."""
import math
from typing import Literal

BeamType = Literal['pp', 'ee', 'mumu', 'ep', 'pe', 'ppbar']
# MadGraph lpp: 0 = elementary beam (no PDF), +1 = proton, -1 = antiproton.
BEAM_PDFS = {'pp': (1, 1), 'ee': (0, 0), 'mumu': (0, 0),
             'ep': (0, 1), 'pe': (1, 0), 'ppbar': (1, -1)}


def com_energy(energy1, energy2=None):
    """Ultrarelativistic head-on beam energy, in GeV."""
    return 2 * math.sqrt(energy1 * (energy1 if energy2 is None else energy2))
