from findingz.card_defaults import read_defaults


def test_native_defaults_exclude_dependent_and_branching_entries():
    run, params = read_defaults(" 20 = ptl ! cut\n 'nn23lo1' = pdlabel\n", '''BLOCK MASS
 23 9.1188e1 # Z
 # Dependent parameters
 24 80.0
BLOCK SMINPUTS
 1 1.325e2
DECAY 23 2.4952
 .5 2 11 -11
''')
    assert run == {'ptl': '20', 'pdlabel': 'nn23lo1'}
    assert params == {'mass 23': '9.1188e1', 'sminputs 1': '1.325e2', 'decay 23': '2.4952'}
