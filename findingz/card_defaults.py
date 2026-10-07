"""Read actual process cards without generating events."""
from pathlib import Path
import re
import subprocess
import tempfile

from .hep_pipeline import HepSimulationConfig, render_madgraph_process_card
from .param_card import apply_overrides as apply_parameter


def read_defaults(run_card, param_card):
    run = {}
    for line in run_card.splitlines():
        fields = re.split(r'[!#]', line, maxsplit=1)[0].split('=')
        if len(fields) == 2:
            run[fields[1].strip().lower()] = fields[0].strip().strip("\"'")
    params = {}
    block = None
    for line in param_card.splitlines():
        fields = line.split('#', 1)[0].split()
        if not fields:
            continue
        if fields[0].lower() == 'block':
            block = fields[1].lower()
            continue
        if fields[0].lower() == 'decay':
            block = None
            key = 'decay ' + fields[1]
        elif block:
            key = ' '.join([block, *fields[:-1]])
        else:
            continue
        try:
            value = float(re.sub('[dD]', 'e', fields[-1]))
            apply_parameter(param_card, {key: value})
        except ValueError:
            continue  # Derived parameters and nonnumeric widths are not editable.
        params[key] = fields[-1]
    return run, params


def prepare_defaults(executable, model, model_path, process_lines):
    config = HepSimulationConfig(model=model, model_ufo_path=model_path,
                                 process_lines=list(process_lines), run_mode='madgraph')
    with tempfile.TemporaryDirectory(prefix='findingz-card-preview-') as directory:
        root = Path(directory)
        card = root / 'preview.mg5'
        card.write_text(render_madgraph_process_card(config, root / 'process'))
        try:
            result = subprocess.run([executable, str(card)], cwd=root, capture_output=True,
                                    text=True, timeout=120)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("Preparing default cards timed out; try again or check this model/process") from error
        cards = root / 'process' / 'Cards'
        if result.returncode or not (cards / 'param_card.dat').is_file():
            raise RuntimeError('Could not prepare this process’s default cards. ' +
                               (result.stderr or result.stdout)[-1000:])
        return read_defaults((cards / 'run_card.dat').read_text(),
                             (cards / 'param_card.dat').read_text())
