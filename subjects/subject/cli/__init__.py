"""subject CLI 统一入口. 见 subject_structure.md §6.4 / subject.md §5.1.

用法::

    python -m subject.cli run --strategy <name> --mode params
    python -m subject.cli run --strategy <name> --mode weight --weight-test <name>
    python -m subject.cli run --strategy <name> --mode params --monitor
"""

from .main import main

__all__ = ["main"]
