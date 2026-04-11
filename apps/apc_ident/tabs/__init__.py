"""apc_ident sub-tab widgets.

Each tab gets its own module so C4 can replace one at a time without
disturbing the rest of the studio shell.
"""
from .data_tab import DataTab
from .tags_tab import TagsTab
from .identification_tab import IdentificationTab
from .results_tab import ResultsTab
from .validation_tab import ValidationTab

__all__ = [
    "DataTab", "TagsTab", "IdentificationTab", "ResultsTab", "ValidationTab",
]
