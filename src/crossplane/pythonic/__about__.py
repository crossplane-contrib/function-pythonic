from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version(
        "crossplane-function-pythonic"
    )  # Use the exact [project.name] from pyproject.toml
except PackageNotFoundError:
    __version__ = "0.0.0"
