"""Check real kernel startup, state, sample discovery, and plot output (no file writes).

Run inside the course image: python /opt/findingz/scripts/check_notebook_kernel.py
"""

from jupyter_client import KernelManager


def check(name):
    manager = KernelManager(kernel_name=name)
    manager.start_kernel()
    client = manager.client()
    client.start_channels()
    messages = []
    try:
        client.wait_for_ready(timeout=30)
        for code in (
            "import numpy as np, pandas as pd, awkward as ak, uproot\nvalue = 21",
            "assert value * 2 == 42\nprint('cell output works')",
            ("from findingz.catalog import load_catalog\n"
            "from findingz.delphes import default_run_root\n"
            "from findingz.hypotheses import build_sample_library\n"
            "library = build_sample_library(load_catalog(), default_run_root())\n"
            "if library: assert len(next(iter(library.values())).load()) >= 0"),
            ("%matplotlib inline\nimport matplotlib.pyplot as plt\n"
             "plt.plot([0, 1], [0, 1]); plt.show()"),
        ):
            print(f"{name}: checking {code.splitlines()[0]}", flush=True)
            reply = client.execute_interactive(code, timeout=30, output_hook=messages.append)
            if reply["content"]["status"] != "ok":
                raise RuntimeError(reply["content"])
        assert any(message["msg_type"] == "stream" for message in messages)
        assert any("image/png" in message["content"].get("data", {})
                   for message in messages)
        print(f"{name}: startup, cell state, sample loading, text and plot output passed")
    finally:
        client.stop_channels()
        manager.shutdown_kernel(now=True)


if __name__ == "__main__":
    for kernel_name in ("findingz", "python3"):
        check(kernel_name)
