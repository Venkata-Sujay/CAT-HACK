"""Runtime environment fixes that must run before scientific libraries import.

Import this module FIRST, before joblib / scikit-learn / pandas, in every
entrypoint (API, ML scripts, tests).
"""

import os
import warnings


def silence_loky_core_probe() -> None:
    """Stop joblib/loky shelling out to `wmic` to count physical CPU cores.

    On this Windows build `wmic` is absent, so the probe raises. loky then does
    three unhelpful things: warns, calls ``traceback.print_exc()`` directly to
    stderr (which no ``warnings`` filter can suppress), and falls back to the
    logical core count anyway. The result is a multi-line traceback in the API
    startup log and on some ``predict()`` calls -- alarming to read, and
    completely cosmetic.

    Pre-seeding ``physical_cores_cache`` makes the probe short-circuit, so the
    exception never happens in the first place. The env var and warning filter
    are belt-and-braces for loky versions that cache differently.

    Safe no-op if loky's internals move: the import is guarded.
    """
    cores = os.cpu_count() or 4
    os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(cores))
    warnings.filterwarnings(
        "ignore",
        message=r"(?s).*Could not find the number of physical cores.*",
        category=UserWarning,
    )
    try:
        from joblib.externals.loky.backend import context

        if getattr(context, "physical_cores_cache", None) is None:
            context.physical_cores_cache = cores
    except Exception:  # noqa: BLE001 - a cosmetic fix must never break startup
        pass


def apply_all() -> None:
    silence_loky_core_probe()
