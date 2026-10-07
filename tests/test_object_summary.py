import numpy as np
import pandas as pd
import pytest
from findingz.object_summary import summarize_objects, empty_pair
from findingz.physics import add_observables
from findingz.hep_pipeline import extract_delphes_dileptons, extract_lhe_truth
from findingz.analysis_variables import apply_windows, AnalysisVariable


def test_rank_and_mass():
    result = summarize_objects('jet', [(20., 0., 0., 0.), (40., 0., np.pi, 0.)])
    assert result['leading_jet_pt'] == 40
    assert result['n_jet'] == 2
    assert result['m_jet_pair'] == pytest.approx(np.sqrt(3200))
    assert np.isnan(summarize_objects('jet', [])['m_jet_pair'])


def test_jet_only_delphes_preserves_events(tmp_path):
    ak = pytest.importorskip('awkward')
    uproot = pytest.importorskip('uproot')
    path = tmp_path / 'jets.root'
    with uproot.recreate(path) as root:
        root.mktree('Delphes', {
            'Jet.PT': ak.Array([[40., 20.], []]),
            'Jet.Eta': ak.Array([[0., 0.], []]),
            'Jet.Phi': ak.Array([[0., np.pi], []]),
            'Jet.Mass': ak.Array([[0., 0.], []]),
            'MissingET.MET': ak.Array([[15.], [0.]]),
            'MissingET.Phi': ak.Array([[0.], [0.]])})
    frame = add_observables(extract_delphes_dileptons(path))
    assert len(frame) == 2
    assert frame.event_id.tolist() == [0, 1]
    assert frame.n_jet.tolist() == [2, 0]
    assert frame.met.tolist() == [15., 0.]
    assert frame.mll.isna().all()
    assert 'n_electron' not in frame  # unavailable collection is not zero
    variable = AnalysisVariable(column='n_jet', label='Jets', description='Count', step=1.)
    selected = apply_windows(frame, {'jets': (2, 4)}, {'jets': variable})
    assert len(selected) == 1


def test_lhe_without_leptons(tmp_path):
    path = tmp_path / 'events.lhe'
    path.write_text('<event>\n2 1 1 1 1 1\n1 1 0 0 0 0 20 0 0 20 0\n-1 1 0 0 0 0 -20 0 0 20 0\n</event>\n')
    frame = add_observables(extract_lhe_truth(path))
    assert len(frame) == 1
    assert frame.n_parton.iloc[0] == 2
    assert frame.m_parton_pair.iloc[0] == pytest.approx(40.)
    assert frame.mll.isna().all()
    assert 'n_jet' not in frame


def test_jet_counting_and_plotting_with_absent_objects(tmp_path):
    from findingz.hypotheses import AnalysisSample
    from findingz.notebook_analysis import select_samples, plot_samples
    path = tmp_path / 'analysis.csv'
    frame = add_observables(pd.DataFrame([
        {'event_id': 0, 'channel': 'other', 'weight': 1., **empty_pair(), **summarize_objects('jet', [])},
        {'event_id': 1, 'channel': 'other', 'weight': 1., **empty_pair(),
         **summarize_objects('jet', [(40., 0., 0., 0.)])}]))
    frame.to_csv(path, index=False)
    sample = AnalysisSample('jets', 'Jets', 'generated', path, '',
                            {'collider': 'pp', 'beam_energy_gev': 6500., 'run_mode': 'full'},
                            generated_events=2, cross_section_pb=1.)
    library = {'jets': sample}
    definitions = {'pt': dict(column='leading_jet_pt', label='Jet pT', description='Jet', step=1.)}
    inclusive = select_samples(library, ['jets'], luminosity_fb=1., variables=definitions)
    assert len(inclusive['jets']) == 2
    assert inclusive['jets'].weight.sum() == pytest.approx(1000.)
    selected = select_samples(library, ['jets'], cuts={'pt': (30., 50.)},
                              luminosity_fb=1., variables=definitions)
    assert selected['jets'].weight.sum() == pytest.approx(500.)
    _, summary = plot_samples(inclusive, library, 'pt', variables=definitions)
    assert summary['selected rows'].iloc[0] == 1
