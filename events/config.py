"""Business and scoring settings in one place (override per site via environment variables)."""
import os


def _f(name, default):
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return float(default)


# --- money (ROI) -------------------------------------------------------------
LABOR_EUR_PER_HOUR = _f("KAIRO_LABOR_EUR_PER_HOUR", 35.0)   # fully loaded cost of one operator hour
SHIFT_HOURS = _f("KAIRO_SHIFT_HOURS", 8.0)
SHIFTS_PER_DAY = _f("KAIRO_SHIFTS_PER_DAY", 2.0)
WORKDAYS_PER_YEAR = _f("KAIRO_WORKDAYS_PER_YEAR", 230.0)

# share of each friction type a fix can realistically remove (shown to the user)
RECOVERABLE = {"search": 0.6, "transit": 0.4, "idle": 0.3, "hesitation": 0.5, "extra_reach": 0.3,
                "reattempt": 0.45}

# --- proficiency labels (thresholds on the WORKFLOW score, never on a person) --
PROFICIENCY_ADVANCED = _f("KAIRO_PROF_ADVANCED", 62.0)   # 50 = the station median workflow
PROFICIENCY_NEEDS_TRAINING = _f("KAIRO_PROF_NEEDS_TRAINING", 40.0)

# --- collaboration (precision first) -----------------------------------------
COLLAB_CONFIRMED = 0.90
COLLAB_POSSIBLE = 0.60
