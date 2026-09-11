"""Notebook launcher with debugger imports completed before output redirection."""

import json
import sys
import tempfile
from pathlib import Path


def install() -> None:
    """Register both Python choices with the tested launcher in this environment."""
    from jupyter_client.kernelspec import KernelSpecManager

    with tempfile.TemporaryDirectory() as directory:
        # The image builds as root but notebooks run as an unprivileged user.
        # install_kernel_spec copies directory permissions along with the files.
        Path(directory).chmod(0o755)
        spec = {
            "argv": [sys.executable, "-Xfrozen_modules=off", "-m",
                     "findingz.notebook_kernel", "-f", "{connection_file}"],
            "display_name": "Python (Finding Z)",
            "language": "python",
            "metadata": {"debugger": True},
        }
        path = Path(directory) / "kernel.json"
        manager = KernelSpecManager()
        for name in ("findingz", "python3"):
            spec["display_name"] = "Python (Finding Z)" if name == "findingz" else "Python 3"
            path.write_text(json.dumps(spec, indent=2) + "\n")
            manager.install_kernel_spec(directory, kernel_name=name, prefix=sys.prefix)


def main() -> None:
    if sys.argv[1:] == ["--install"]:
        install()
        return

    # Importing debugger support after IPKernelApp.init_io reproducibly stalls
    # startup in our amd64 Docker runtime on Mac. Preloading preserves debugging
    # and normal notebook output without patching third-party package internals.
    import ipykernel.debugger  # noqa: F401
    from ipykernel.kernelapp import IPKernelApp

    IPKernelApp.launch_instance()


if __name__ == "__main__":
    main()
