"""Input drift detection for the code review inference endpoint.

Fix A4-004 / GATE-11: monitors diff size distribution vs. training baseline
using a two-sample Kolmogorov-Smirnov test. Triggers an automated retraining
callback when drift is detected — does not require manual intervention.

KS test: Kolmogorov (1933), Smirnov (1948) — standard non-parametric
distribution comparison test. No citation required; foundational statistics.

Threshold documentation (CMD-002 [D]):
  _KS_PVALUE_THRESHOLD = 0.05 — standard alpha for two-sample KS test.
  _WINDOW_SIZE = 500 — minimum sample size for KS test power at alpha=0.05.
    UNVERIFIED: set based on standard power tables; calibrate to daily traffic.
"""
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

import structlog
from scipy import stats

logger = structlog.get_logger()

# Baseline populated at application startup via set_baseline().
_BASELINE_DIFF_LENGTHS: list[float] = []

# Two-sample KS test alpha. [D] Standard 0.05 significance level.
_KS_PVALUE_THRESHOLD = 0.05

# Rolling window size. UNVERIFIED: 500 — calibrate to measured daily traffic.
_WINDOW_SIZE = 500

_retrain_callback: Callable[[], None] | None = None


@dataclass
class DriftMonitor:
    """Rolling window drift detector for diff size distribution."""

    diff_lengths: deque = field(default_factory=lambda: deque(maxlen=_WINDOW_SIZE))
    security_finding_rate: deque = field(default_factory=lambda: deque(maxlen=_WINDOW_SIZE))
    _lock: threading.Lock = field(default_factory=threading.Lock)
    checks_run: int = 0
    drift_detections: int = 0

    def record(self, diff_len: int, has_security_finding: bool) -> None:
        """Record one inference request and run drift check if window is full."""
        with self._lock:
            self.diff_lengths.append(float(diff_len))
            self.security_finding_rate.append(1.0 if has_security_finding else 0.0)
            if len(self.diff_lengths) >= _WINDOW_SIZE:
                self._check_drift()

    def _check_drift(self) -> None:
        """Run KS test. Trigger retraining callback if drift detected."""
        self.checks_run += 1
        if not _BASELINE_DIFF_LENGTHS:
            logger.warning("drift_check_skipped", reason="baseline_not_set")
            return

        ks_stat, p_value = stats.ks_2samp(
            _BASELINE_DIFF_LENGTHS,
            list(self.diff_lengths),
        )
        logger.info(
            "drift_check",
            ks_stat=round(ks_stat, 4),
            p_value=round(p_value, 4),
            window_size=len(self.diff_lengths),
        )
        if p_value < _KS_PVALUE_THRESHOLD:
            self.drift_detections += 1
            logger.warning(
                "drift_detected",
                ks_stat=round(ks_stat, 4),
                p_value=round(p_value, 4),
                action="triggering_retraining_callback",
            )
            if _retrain_callback is not None:
                _retrain_callback()
            else:
                logger.error(
                    "drift_detected_no_retrain_callback",
                    detail="Set a retraining callback via set_retrain_callback()",
                )


def set_baseline(diff_lengths: list[float]) -> None:
    """Set the training distribution baseline. Call at application startup.

    Args:
        diff_lengths: list of diff byte-lengths from the training dataset.
            Compute with: [len(row['diff'].encode()) for row in train_ds]
    """
    global _BASELINE_DIFF_LENGTHS
    _BASELINE_DIFF_LENGTHS = list(diff_lengths)
    logger.info("drift_baseline_set", n=len(_BASELINE_DIFF_LENGTHS))


def set_retrain_callback(fn: Callable[[], None]) -> None:
    """Register the function to call when drift is detected.

    In production, this should enqueue a retraining job (e.g. via Celery,
    Airflow, or a CI trigger) rather than running training inline.
    """
    global _retrain_callback
    _retrain_callback = fn


# Module-level singleton — one monitor per process
monitor = DriftMonitor()
