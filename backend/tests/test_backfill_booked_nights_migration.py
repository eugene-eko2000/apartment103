"""Guards on the booked_nights backfill migration.

The migration feeds a unique index that init_beanie rebuilds on every app
start, so backfilling data that already double-books would leave the app
unable to boot. It has to refuse, loudly and with the offending ids, while
the system is still up.
"""

import importlib.util
from datetime import datetime
from pathlib import Path

import pytest

@pytest.fixture
def anyio_backend():
    return "asyncio"


_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "20260821000000_backfill_booking_booked_nights.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("backfill_booked_nights", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _range(begin: str, end: str) -> dict:
    return {"begin_date": datetime.fromisoformat(begin), "end_date": datetime.fromisoformat(end)}


def test_nights_are_the_half_open_interval():
    module = _load()
    nights = module._nights([_range("2026-07-01", "2026-07-04")])
    # end_date is an exclusive checkout day: three nights, not four.
    assert [night.date().isoformat() for night in nights] == ["2026-07-01", "2026-07-02", "2026-07-03"]
    assert all(night.tzinfo is None for night in nights)


def test_nights_are_deduplicated_across_touching_ranges():
    module = _load()
    # One booking holding two ranges that share a night must not produce a
    # duplicate: a document may repeat a value without tripping its own
    # unique index, but the stored array should still be clean.
    nights = module._nights([_range("2026-07-01", "2026-07-03"), _range("2026-07-02", "2026-07-04")])
    assert [night.date().isoformat() for night in nights] == [
        "2026-07-01",
        "2026-07-02",
        "2026-07-03",
    ]


def test_no_conflicts_reported_for_adjacent_stays():
    module = _load()
    # A checkout on another booking's check-in day is not an overlap.
    conflicts = module._find_conflicts([
        {"_id": "a", "date_ranges": [_range("2026-07-01", "2026-07-04")]},
        {"_id": "b", "date_ranges": [_range("2026-07-04", "2026-07-07")]},
    ])
    assert conflicts == {}


def test_conflicts_name_every_booking_sharing_a_night():
    module = _load()
    conflicts = module._find_conflicts([
        {"_id": "a", "date_ranges": [_range("2026-07-01", "2026-07-04")]},
        {"_id": "b", "date_ranges": [_range("2026-07-03", "2026-07-06")]},
    ])
    assert [night.date().isoformat() for night in conflicts] == ["2026-07-03"]
    assert sorted(next(iter(conflicts.values()))) == ["a", "b"]


@pytest.mark.anyio
async def test_forward_refuses_to_backfill_conflicting_data(monkeypatch):
    module = _load()

    class _Cursor:
        async def to_list(self, _):
            return [
                {"_id": "a", "date_ranges": [_range("2026-07-01", "2026-07-04")]},
                {"_id": "b", "date_ranges": [_range("2026-07-03", "2026-07-06")]},
            ]

    written = []

    class _Collection:
        def find(self, *args, **kwargs):
            return _Cursor()

        async def update_one(self, *args, **kwargs):
            written.append(args)

    monkeypatch.setattr(module.Booking, "get_pymongo_collection", classmethod(lambda cls: _Collection()))

    with pytest.raises(RuntimeError) as excinfo:
        await module.Forward.backfill_booked_nights.function(module.Forward(), None)

    message = str(excinfo.value)
    assert "2026-07-03" in message
    assert "a" in message and "b" in message
    # Nothing partially written: the refusal has to leave the data as it was.
    assert written == []
