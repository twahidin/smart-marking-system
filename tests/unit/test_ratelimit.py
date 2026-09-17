from sms.providers.ratelimit import BucketPool, RateLimitedAgent, TokenBucket


class FakeClock:
    def __init__(self):
        self.t = 0.0
        self.slept = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(s)
        self.t += s


def test_bucket_allows_rpm_calls_then_waits():
    clock = FakeClock()
    b = TokenBucket(rpm=2, clock=clock.now, sleep=clock.sleep)
    b.acquire(); b.acquire()
    assert clock.slept == []
    b.acquire()
    assert len(clock.slept) == 1 and 0 < clock.slept[0] <= 60


def test_bucket_zero_rpm_never_waits():
    clock = FakeClock()
    b = TokenBucket(rpm=0, clock=clock.now, sleep=clock.sleep)
    for _ in range(50):
        b.acquire()
    assert clock.slept == []


def test_rate_limited_agent_delegates_and_exposes_client_model():
    class Agent:
        client = object(); model = "m"
        def run(self, x): return x + 1
    calls = []
    class Bucket:
        def acquire(self): calls.append(1)
    wrapped = RateLimitedAgent(Agent(), Bucket())
    assert wrapped.run(1) == 2 and calls == [1]
    assert wrapped.model == "m" and wrapped.client is Agent.client


def test_bucket_pool_one_bucket_per_provider_replaced_when_rpm_changes():
    pool = BucketPool()
    a = pool.get("openai", 60); b = pool.get("openrouter", 60)
    assert a is not b and pool.get("openai", 60) is a
    assert pool.get("openai", 8) is not a and pool.get("openai", 8).rpm == 8
