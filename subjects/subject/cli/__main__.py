"""支持 ``python -m subject.cli`` 调用."""
from .main import main
import sys

sys.exit(main())
