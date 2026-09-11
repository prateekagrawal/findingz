import json
import sys
from pathlib import Path
from types import SimpleNamespace

from findingz import notebook_kernel


def test_install_registers_both_kernel_names(monkeypatch):
    installed = {}

    class Manager:
        def install_kernel_spec(self, directory, kernel_name, prefix):
            assert prefix == sys.prefix
            assert Path(directory).stat().st_mode & 0o777 == 0o755
            installed[kernel_name] = json.loads((Path(directory) / "kernel.json").read_text())

    monkeypatch.setitem(sys.modules, "jupyter_client.kernelspec",
                        SimpleNamespace(KernelSpecManager=Manager))
    notebook_kernel.install()
    assert set(installed) == {"findingz", "python3"}
    for spec in installed.values():
        assert spec["argv"] == [sys.executable, "-Xfrozen_modules=off", "-m",
                                "findingz.notebook_kernel", "-f", "{connection_file}"]
        assert spec["metadata"]["debugger"] is True


def test_install_mode_does_not_launch_kernel(monkeypatch):
    calls = []
    monkeypatch.setattr(sys, "argv", ["notebook_kernel", "--install"])
    monkeypatch.setattr(notebook_kernel, "install", lambda: calls.append("install"))
    notebook_kernel.main()
    assert calls == ["install"]
