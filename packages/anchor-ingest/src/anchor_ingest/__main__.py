"""Allow running as `python -m anchor_ingest`."""
import sys
from .cli import main

sys.exit(main())
