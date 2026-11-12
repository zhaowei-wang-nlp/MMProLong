"""All inference attempts share one rolling request budget, including retries."""

import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch


sys.path.insert(0, str(Path(__file__).parents[2] / "data_synthesis_doc_vqa"))
import agentic_vqa
from agentic_vqa import RequestRateGate


class Clock:
    def __init__(self):
        self.value = 0.0
        self.lock = threading.Lock()

    def now(self):
        with self.lock:
            return self.value

    def sleep(self, seconds):
        with self.lock:
            self.value += seconds


class RequestRateTests(unittest.TestCase):
    def test_window_expiry_and_configuration_do_not_erase_recent_requests(self):
        clock = Clock()
        gate = RequestRateGate(2, clock=clock.now, sleeper=clock.sleep)
        self.assertEqual([gate.wait(), gate.wait(), gate.wait()], [0.0, 0.0, 60.0])
        gate.set_limit(1)
        self.assertEqual(gate.wait(), 120.0)

    def test_concurrent_admissions_stay_within_rolling_window(self):
        clock = Clock()
        gate = RequestRateGate(5, clock=clock.now, sleeper=clock.sleep)
        with ThreadPoolExecutor(max_workers=64) as pool:
            starts = sorted(pool.map(lambda _: gate.wait(), range(64)))
        for instant in set(starts):
            self.assertLessEqual(sum(instant - 60 < t <= instant for t in starts), 5)

    def test_retry_consumes_another_request_slot_and_balances_activity(self):
        class Limited(Exception):
            status_code = 429

        rate = Mock()
        cooldown = Mock()
        activity = Mock()
        response = object()
        call = Mock(side_effect=[Limited(), response])
        with (
            patch.object(agentic_vqa, "_REQUEST_RATE", rate),
            patch.object(agentic_vqa, "_RATE_GATE", cooldown),
            patch.object(agentic_vqa, "retry_after_seconds", return_value=0),
        ):
            actual, attempts = agentic_vqa.complete_with_retry(call, activity=activity, job_id="test")
        self.assertIs(actual, response)
        self.assertEqual(rate.wait.call_count, 2)
        self.assertEqual(len(attempts), 2)
        self.assertEqual([x.args[0] for x in activity.call_args_list], [1, -1, 1, -1])
        cooldown.defer.assert_called_once_with(0)


if __name__ == "__main__":
    unittest.main()
