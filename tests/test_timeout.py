"""A request that never answers must end the request, not the run.

Written after a run of 91 documents stopped at document 19 and sat for
forty-two minutes holding an established connection at zero percent CPU. There
was no timeout on the call, so a stalled read was indistinguishable from work
in progress — and the log, which reports every step, had nothing to report
because nothing had happened.
"""

import httpx

from lawscan.llm.client import REQUEST_TIMEOUT, _is_timeout


class TestRecognisingAStall:
    def test_the_transport_timeouts(self):
        assert _is_timeout(httpx.ReadTimeout("no answer"))
        assert _is_timeout(httpx.ConnectTimeout("no route"))
        assert _is_timeout(httpx.WriteTimeout("blocked"))
        assert _is_timeout(httpx.PoolTimeout("no slot"))

    def test_the_builtin_one(self):
        assert _is_timeout(TimeoutError())

    def test_a_real_failure_is_not_a_stall(self):
        """A wrong answer must not be retried as if it were a slow one."""
        assert not _is_timeout(ValueError("คำตอบไม่ใช่ JSON"))
        assert not _is_timeout(KeyError("core"))
        assert not _is_timeout(httpx.HTTPStatusError("400", request=None, response=None))


class TestTheValue:
    def test_long_enough_for_the_slowest_real_question(self):
        # The business question carries a 34,000-character taxonomy and takes
        # about thirteen seconds. The timeout breaks stalls, not slow work.
        assert REQUEST_TIMEOUT >= 60

    def test_short_enough_to_notice(self):
        # A run of 240 documents cannot afford to wait an hour on one of them.
        assert REQUEST_TIMEOUT <= 600
