"""Short default labels; course catalogues can override them."""
DESCRIPTIONS = {
    'ptl': 'Minimum charged-lepton pT [GeV].',
    'ptj': 'Minimum jet pT [GeV].',
    'ptg': 'Minimum photon pT [GeV].',
    'pta': 'Minimum photon pT [GeV].',
    'etal': 'Maximum charged-lepton |eta|.',
    'etaj': 'Maximum jet |eta|.',
    'etag': 'Maximum photon |eta|.',
    'etaa': 'Maximum photon |eta|.',
    'mmll': 'Minimum same-flavour opposite-sign dilepton mass [GeV].',
    'mmllmax': 'Maximum same-flavour opposite-sign dilepton mass [GeV].',
    'mmjj': 'Minimum dijet mass [GeV].',
    'drll': 'Minimum lepton–lepton separation ΔR.',
    'drjj': 'Minimum jet–jet separation ΔR.',
    'drjl': 'Minimum jet–lepton separation ΔR.',
    'drgg': 'Minimum photon–photon separation ΔR.',
    'drgj': 'Minimum photon–jet separation ΔR.',
    'drgl': 'Minimum photon–lepton separation ΔR.',
    'pdlabel': 'Parton distribution function provider/set label.',
    'lhaid': 'LHAPDF set identifier (when using LHAPDF).',
    'fixed_ren_scale': 'Use a fixed renormalization scale.',
    'fixed_fac_scale': 'Use fixed factorization scales.',
    'scale': 'Fixed renormalization scale [GeV].',
    'dsqrt_q2fact1': 'Fixed beam-1 factorization scale [GeV].',
    'dsqrt_q2fact2': 'Fixed beam-2 factorization scale [GeV].',
    'cut_decays': 'Apply generation cuts to decay products.',
    'mass 23': 'Z-boson mass [GeV].',
    'decay 23': 'Z-boson total width [GeV].',
    'sminputs 1': 'Inverse electromagnetic coupling, 1/alpha.',
}


def parameter_description(name):
    if name in DESCRIPTIONS:
        return DESCRIPTIONS[name]
    if name.startswith('mass '):
        return f'Particle mass [GeV]; PDG ID {name.split()[1]}.'
    if name.startswith('decay '):
        return f'Total decay width [GeV]; PDG ID {name.split()[1]}.'
    return 'Model parameter (model units).' if ' ' in name else 'MadGraph generation setting.'
