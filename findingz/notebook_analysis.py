"""Small notebook helpers; return ordinary pandas tables and matplotlib figures."""
import json
import warnings
from pathlib import Path
import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from .catalog import load_catalog
from .delphes import default_run_root
from .hypotheses import build_sample_library, validate_counting_samples, compatibility_warnings
from .analysis_variables import AnalysisVariable, load_variable_catalog, apply_windows
from .counting import summarize_cut_and_count, compare_hypotheses


def enable_inline_plots():
    """Enable figure rendering in a notebook; do nothing in ordinary Python."""
    try:
        from IPython import get_ipython
    except ImportError:
        return
    shell = get_ipython()
    if shell is not None:
        shell.run_line_magic("matplotlib", "inline")


def load_analysis(filename):
    """Load the settings saved beside a notebook, or in its configured directory."""
    from .notebook_export import notebook_directory
    path = Path(filename)
    if not path.is_file() and not path.is_absolute():
        path = notebook_directory() / path
    if not path.is_file():
        raise FileNotFoundError(
            f"Cannot find {filename}. Keep the .settings.json file beside your notebook "
            "and start the notebook from that directory."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def available_samples():
    return build_sample_library(load_catalog(), default_run_root())


def sample_table(library):
    return pd.DataFrame([{"sample_id": key, "name": s.label,
                         "cross section [pb]": s.cross_section_pb,
                         "generated events": s.generated_events} for key, s in library.items()],
                        columns=["sample_id", "name", "cross section [pb]", "generated events"])


def definitions(saved=None):
    return ({k: AnalysisVariable(**v) for k, v in saved.items()}
            if saved else load_variable_catalog().variables)


def select_samples(library, sample_ids, *, cuts=None, channels=None, luminosity_fb=None,
                   variables=None):
    """Inclusive range cuts; channels=None keeps all. Luminosity enables rate weights."""
    variables = definitions(variables)
    cuts = cuts or {}
    unknown = set(cuts)-variables.keys()
    if unknown:
        raise ValueError(f"Unknown cut variables: {sorted(unknown)}")
    result = {}
    for key in sample_ids:
        if key not in library:
            raise ValueError(f"Sample {key!r} is unavailable. Select an ID from the sample table.")
        sample = library[key]
        frame = sample.load() if luminosity_fb is None else sample.expected_frame(luminosity_fb)
        if channels is not None and "channel" in frame:
            frame = frame.loc[frame.channel.isin(channels)]
        result[key] = apply_windows(frame, cuts, variables)
    return result


def plot_samples(frames, library, observable="mll", *, shape_only=True, variables=None):
    """40 shared bins, matching the web plot. Returns figure and selected-yield table."""
    variable = definitions(variables)[observable]
    if not frames:
        return None, pd.DataFrame()
    series = [f[variable.column] for f in frames.values() if not f.empty]
    values = (pd.to_numeric(pd.concat(series, ignore_index=True), errors="coerce")
              .replace([np.inf,-np.inf],np.nan).dropna() if series else pd.Series(dtype=float))
    low, high = (float(values.min()),float(values.max())) if not values.empty else (0.,1.)
    if low == high:
        pad = max(abs(low)*.05,.5)
        low, high = low-pad, high+pad
    bins = np.linspace(low,high,41)
    fig = Figure(figsize=(7,4))
    ax = fig.subplots()
    rows = []
    for key, frame in frames.items():
        frame = frame.loc[np.isfinite(pd.to_numeric(frame[variable.column], errors="coerce"))]
        weights = pd.to_numeric(frame.get("weight",pd.Series(1.,index=frame.index)))
        integral = float(weights.sum())
        rows.append({"sample":library[key].label,"selected rows":len(frame),
                     "yield before shape normalization":integral})
        if shape_only and integral > 0:
            weights = weights/integral
        ax.hist(frame[variable.column],bins=bins,weights=weights,histtype="step",
                linewidth=2,label=library[key].label)
    ax.set_xlabel(variable.label)
    ax.set_ylabel("Fraction of sample" if shape_only else "Expected events")
    ax.grid(alpha=.2)
    ax.legend()
    fig.tight_layout()
    return fig,pd.DataFrame(rows)


def compare_samples(library, null, alternative, *, cuts=None, channels=None,
                    luminosity_fb=1., null_uncertainty=0., variables=None):
    """Two complete predictions with identical selections; never sum hypotheses."""
    if not null or not alternative:
        return None
    if null == alternative:
        raise ValueError("Choose two different samples")
    ids = [null, alternative]
    missing = set(ids) - library.keys()
    if missing:
        raise ValueError(f"Unavailable samples: {sorted(missing)}")
    validate_counting_samples([library[key] for key in ids])
    messages = compatibility_warnings([library[key] for key in ids])
    if messages:
        warnings.warn(" ".join(messages), UserWarning, stacklevel=2)
    frames = select_samples(library, ids, cuts=cuts, channels=channels,
                            luminosity_fb=luminosity_fb, variables=variables)
    return compare_hypotheses(frames[null], frames[alternative],
                              null_uncertainty_fraction=null_uncertainty)


def comparison_table(result):
    if result is None:
        return pd.Series({"Next step": "Choose a null and a complete alternative prediction."})
    return pd.Series({"Null prediction": result.null_yield,
                      "Alternative prediction": result.alternative_yield,
                      "Excess / deficit (alternative - null)": result.difference,
                      "Expected discovery / deficit sensitivity [sigma]": result.signed_significance})


def count_samples(library, signal, backgrounds, *, cuts=None, channels=None,
                  luminosity_fb=1., background_uncertainty=.1, variables=None):
    """Legacy additive API retained for old saved notebooks, not the current UI."""
    if not signal or not backgrounds:
        return None
    ids = [signal,*backgrounds]
    missing = set(ids)-library.keys()
    if missing:
        raise ValueError(f"Unavailable samples: {sorted(missing)}")
    validate_counting_samples([library[key] for key in ids])
    messages = compatibility_warnings([library[key] for key in ids])
    if messages:
        warnings.warn(" ".join(messages), UserWarning, stacklevel=2)
    frames = select_samples(library,ids,cuts=cuts,channels=channels,
                            luminosity_fb=luminosity_fb,variables=variables)
    return summarize_cut_and_count(frames[signal],
        pd.concat([frames[key] for key in backgrounds],ignore_index=True),
        background_uncertainty_fraction=background_uncertainty)


def count_table(result, *, details=False):
    """Predicted counts and rough discovery sensitivity, not an observed result."""
    if result is None:
        return pd.Series({"Next step":"Choose a signal and at least one background."})
    summary = {
        "Expected signal":result.signal_yield,
        "Expected background":result.background_yield,
        "Estimated discovery significance [sigma]":
            result.approximate_significance_with_systematic if result.background_yield > 0 else float("nan"),
    }
    if details:
        summary.update({
            "Signal + background":result.signal_yield + result.background_yield,
            "Fractional background uncertainty":result.background_uncertainty_fraction,
        })
    return pd.Series(summary)
