"""Installed PDF choices and dependencies for card controls."""
import os
from pathlib import Path
import shutil
import subprocess
import yaml


def pdf_choices(executable):
    root = Path(executable).resolve().parent.parent
    data = root / 'Template/LO/lib/Pdfdata'
    files = {'cteq6_m': 'cteq6m.tbl', 'cteq6_l': 'cteq6l.tbl', 'cteq6l1': 'cteq6l1.tbl',
             'nn23lo': 'NNPDF23_lo_as_0119_qed_mem0.grid',
             'nn23lo1': 'NNPDF23_lo_as_0130_qed_mem0.grid',
             'nn23nlo': 'NNPDF23nlo_as_0119_qed_mem0.grid'}
    labels = {name: name for name, filename in files.items() if (data / filename).is_file()}
    configs = [Path(shutil.which('lhapdf-config') or '/nonexistent'),
               root / 'HEPTools/bin/lhapdf-config']
    paths = [Path(p) for p in os.environ.get('LHAPDF_DATA_PATH', '').split(':') if p]
    for config in configs:
        if config.is_file():
            try:
                result = subprocess.run([str(config), '--datadir'], capture_output=True,
                                        text=True, timeout=5, check=True)
                paths.append(Path(result.stdout.strip()))
                labels['lhapdf'] = 'LHAPDF (installed sets)'
                break
            except (OSError, subprocess.SubprocessError):
                continue
    sets = {}
    for path in paths:
        for info in path.glob('*/*.info'):
            try:
                metadata = yaml.safe_load(info.read_text())
                identifier = str(int(metadata['SetIndex']))
                if (info.parent / (info.stem + '_0000.dat')).is_file():
                    sets[identifier] = f'{info.stem} ({identifier})'
            except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError):
                continue
    return {'pdlabel': labels, 'lhaid': sets}


def inactive_reason(name, effective):
    if name == 'lhaid' and effective.get('pdlabel') != 'lhapdf':
        return 'Used only when pdlabel is LHAPDF.'
    if name == 'scale' and not effective.get('fixed_ren_scale', False):
        return 'Enable fixed_ren_scale to set a fixed scale.'
    if name in {'dsqrt_q2fact1', 'dsqrt_q2fact2'}:
        beam = name[-1]
        if not effective.get('fixed_fac_scale', False) and not effective.get('fixed_fac_scale' + beam, False):
            return 'Enable the fixed factorization scale to edit this value.'
    return None
