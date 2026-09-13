import pandas as pd
import pytest
from findingz.hypotheses import AnalysisSample
from findingz.notebook_analysis import select_samples, plot_samples, count_samples

@pytest.fixture
def library(tmp_path):
    path = tmp_path / "events.csv"
    pd.DataFrame({"mll":[80.,90.,100.],"channel":["ee","mumu","ee"],
                  "weight":[1.,1.,1.]}).to_csv(path,index=False)
    return {k:AnalysisSample(k,k,"generated",path,"test",
           {"collider_id":"lhc13","beam_energy_gev":6500.,"run_mode":"madgraph"},
           generated_events=3,cross_section_pb=3.) for k in ["signal","background"]}

def test_selection_and_normalization(library):
    frames = select_samples(library,["signal"],cuts={"mll":(80.,90.)},channels=None,luminosity_fb=2)
    assert len(frames["signal"])==2
    assert frames["signal"].weight.sum()==4000
    none = select_samples(library,["signal"],channels=[])
    assert none["signal"].empty

def test_plot_and_count(library):
    frames = select_samples(library,["signal"])
    fig, table = plot_samples(frames,library,"mll")
    assert fig.axes[0].get_ylabel()=="Fraction of sample"
    assert table.iloc[0]["yield before shape normalization"]==3
    result = count_samples(library,"signal",["background"],cuts={"mll":(90.,100.)})
    assert result.signal_yield==2000
    assert result.background_yield==2000
    assert count_samples(library,None,[]) is None

def test_missing_sample_and_cut_errors(library):
    with pytest.raises(ValueError,match="unavailable"):
        select_samples(library,["missing"])
    with pytest.raises(ValueError,match="Unknown cut"):
        select_samples(library,["signal"],cuts={"typo":(0,1)})

