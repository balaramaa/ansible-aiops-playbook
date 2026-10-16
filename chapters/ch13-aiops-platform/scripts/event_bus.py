#!/usr/bin/env python3
"""
event_bus.py — Chapter 13, Listing 13-3
AIOps platform event bus backed by Redis Streams.

Author : Balaramakrishna Alti
GitHub : https://github.com/balaramaa/ansible-aiops-playbook

Usage:
    # Publish a test event
    from event_bus import EventBus
    bus = EventBus(mock=True)
    eid = bus.publish("alert", "node01", "critical",
                      {"alert_name": "HighMemoryUsage"})

    # Subscribe and process events
    for event in bus.subscribe("my-consumer"):
        print(event)
"""

import json, logging, os, uuid
from datetime import datetime, timezone
from typing import Iterator

log = logging.getLogger(__name__)

STREAM_KEY     = "aiops:events"
CONSUMER_GROUP = "aiops-consumers"

try:
    import redis as _redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    log.debug("redis-py not installed — EventBus will use mock mode")


class EventBus:
    """
    AIOps platform event bus backed by Redis Streams.
    Falls back transparently to an in-memory queue for lab/testing.

    Args:
        redis_url: Redis connection URL (default: REDIS_URL env var or localhost:6379)
        mock:      Force mock mode regardless of Redis availability
    """

    def __init__(self, redis_url: str = None, mock: bool = False):
        self.mock = mock or not REDIS_AVAILABLE
        self._mock_queue: list = []

        if not self.mock:
            url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379")
            try:
                self._redis = _redis.from_url(url, decode_responses=True)
                self._redis.ping()
                # Ensure consumer group exists
                try:
                    self._redis.xgroup_create(STREAM_KEY, CONSUMER_GROUP, "$",
                                               mkstream=True)
                except _redis.exceptions.ResponseError as e:
                    if "BUSYGROUP" not in str(e):
                        raise
                log.info(f"Event bus connected: {url}")
            except Exception as e:
                log.warning(f"Redis unavailable ({e}) — using mock mode")
                self.mock = True
        else:
            log.info("Event bus: mock mode (in-memory queue)")

    def publish(self,
                event_type:      str,
                hostname:        str,
                severity:        str,
                payload:         dict,
                source:          str  = "platform",
                environment:     str  = "unknown",
                auto_remediate:  bool = True) -> str:
        """
        Publish an event to the AIOps event bus.

        Args:
            event_type:     Type of event (alert, compliance_drift, security, etc.)
            hostname:       Affected host FQDN
            severity:       critical | high | medium | low | info
            payload:        Event-specific data dict
            source:         Originating system (prometheus, openscap, eda, etc.)
            environment:    production | staging | lab
            auto_remediate: Whether automated response is approved

        Returns:
            event_id (UUID string)
        """
        event = {
            "event_id":       str(uuid.uuid4()),
            "event_type":     event_type,
            "source":         source,
            "severity":       severity,
            "hostname":       hostname,
            "environment":    environment,
            "timestamp":      datetime.now(timezone.utc).isoformat(),
            "payload":        payload,
            "correlation_id": (
                f"incident-{hostname.split('.')[0]}-"
                f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
            ),
            "auto_remediate": auto_remediate,
            "ttl_seconds":    3600,
        }

        if self.mock:
            self._mock_queue.append(event)
            log.info(f"[BUS-MOCK] Published: {event_type}/{severity} on {hostname}")
        else:
            self._redis.xadd(STREAM_KEY, {"data": json.dumps(event)},
                             maxlen=10000, approximate=True)
            log.info(f"[BUS] Published: {event_type}/{severity} on {hostname}")

        return event["event_id"]

    def subscribe(self,
                  consumer_name: str,
                  count:         int = 10,
                  block_ms:      int = 5000) -> Iterator[dict]:
        """
        Subscribe to the event bus as a named consumer.

        Yields events one at a time. In Redis mode, acknowledges each event
        after it is yielded (caller must process before the next iteration).
        In mock mode, drains the in-memory queue.

        Args:
            consumer_name: Unique consumer identifier
            count:         Max events per batch read
            block_ms:      Milliseconds to block waiting for new events
        """
        if self.mock:
            while self._mock_queue:
                yield self._mock_queue.pop(0)
            return

        while True:
            try:
                messages = self._redis.xreadgroup(
                    CONSUMER_GROUP, consumer_name,
                    {STREAM_KEY: ">"},
                    count=count, block=block_ms
                )
                for stream, entries in (messages or []):
                    for msg_id, fields in entries:
                        try:
                            event = json.loads(fields["data"])
                            yield event
                            # Acknowledge successful processing
                            self._redis.xack(STREAM_KEY, CONSUMER_GROUP, msg_id)
                        except Exception as e:
                            log.error(f"Failed to process event {msg_id}: {e}")
            except _redis.exceptions.ConnectionError as e:
                log.error(f"Event bus connection lost: {e}")
                break
            except Exception as e:
                log.error(f"Event bus subscribe error: {e}")
                break

    def get_pending_count(self) -> int:
        """Return number of unacknowledged events in the consumer group."""
        if self.mock:
            return len(self._mock_queue)
        try:
            info = self._redis.xpending(STREAM_KEY, CONSUMER_GROUP)
            return info.get("pending", 0)
        except Exception:
            return 0

    def stream_length(self) -> int:
        """Return total events in stream."""
        if self.mock:
            return len(self._mock_queue)
        try:
            return self._redis.xlen(STREAM_KEY)
        except Exception:
            return 0


if __name__ == "__main__":
    import argparse, time

    parser = argparse.ArgumentParser(description="AIOps event bus test client")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--subscribe", action="store_true")
    parser.add_argument("--mock", action="store_true", default=True)
    parser.add_argument("--hostname", default="node01.company.com")
    parser.add_argument("--event-type", default="alert")
    parser.add_argument("--severity", default="critical")
    args = parser.parse_args()

    bus = EventBus(mock=args.mock)

    if args.publish:
        eid = bus.publish(
            event_type=args.event_type,
            hostname=args.hostname,
            severity=args.severity,
            payload={"test": True, "alert_name": "TestAlert", "value": 94.2},
            source="test_client",
            environment="lab",
        )
        print(f"Published event: {eid}")
        print(f"Pending events: {bus.get_pending_count()}")

    if args.subscribe:
        print("Subscribing to event bus (Ctrl-C to stop)...")
        for event in bus.subscribe("test-consumer"):
            print(json.dumps(event, indent=2))
