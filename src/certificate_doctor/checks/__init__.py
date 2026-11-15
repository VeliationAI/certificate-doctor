from certificate_doctor.checks.copy_move import check_copy_move
from certificate_doctor.checks.ela import check_ela
from certificate_doctor.checks.logic import check_logic
from certificate_doctor.checks.metadata import check_metadata
from certificate_doctor.checks.text_font import check_text_font

__all__ = [
    "check_ela",
    "check_text_font",
    "check_metadata",
    "check_copy_move",
    "check_logic",
]
