from pathlib import Path
import pytest
from findingz.beams import com_energy
from findingz.catalog import ColliderEntry
from findingz.hep_pipeline import HepSimulationConfig, render_madevent_commands
from findingz.hypotheses import AnalysisSample


@pytest.mark.parametrize('beam,process,pdfs', [
    ('pp', 'generate p p > e+ e-', (1,1)),
    ('ee', 'generate e- e+ > mu- mu+', (0,0)),
    ('mumu', 'generate mu- mu+ > e- e+', (0,0)),
    ('ep', 'generate e- p > e- j', (0,1)),
    ('pe', 'generate p e- > j e-', (1,0)),
    ('ppbar', 'generate p p > e- e+', (1,-1)),
])
def test_beam_cards(beam, process, pdfs):
    config = HepSimulationConfig(collider=beam, process_lines=[process],
                                 beam_energy_gev=30, beam2_energy_gev=900, run_mode='madgraph')
    card = render_madevent_commands(config, 'run_01')
    assert f'set lpp1 {pdfs[0]}' in card
    assert f'set lpp2 {pdfs[1]}' in card
    assert 'set ebeam1 30' in card
    assert 'set ebeam2 900' in card


def test_asymmetric_energy_and_compatibility():
    collider = ColliderEntry(label='ep', beam_type='ep', beam_energy_gev=30, beam2_energy_gev=900)
    assert com_energy(collider.beam_energy_gev, collider.beam2_energy_gev) == pytest.approx(328.6335345)
    def sample(e2):
        return AnalysisSample('id','Test','generated',Path('unused'),'test',
            {'collider':'ep','beam_energy_gev':30,'beam2_energy_gev':e2,'run_mode':'madgraph'})
    assert sample(900).analysis_context != sample(920).analysis_context
    assert sample(None).analysis_context == sample(30).analysis_context


def test_new_beams_require_process():
    with pytest.raises(ValueError, match='explicit process_lines'):
        HepSimulationConfig(collider='ep')
