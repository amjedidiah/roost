import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from ask import ask
from decide import CATEGORIES, NEXT_ACTIONS, PRIORITIES, decide, find_dates
from ingest import chunk_text

TODAY = dt.date(2026, 11, 25)
SAMPLES = Path(__file__).resolve().parent.parent / "sample-docs"


def sample(name, score=0.4, file_id="F"):
    """Chunks of a sample doc, plus matches pointing at its first chunk."""
    chunks = chunk_text((SAMPLES / name).read_text())
    matches = [{"score": score, "metadata": {"file_id": file_id, "file_name": name,
                                              "chunk_index": 0, "chunk_text": chunks[0]}}]
    return matches, chunks


class DecideSamplesTest(unittest.TestCase):
    def check_schema(self, d):
        self.assertIn(d["category"], CATEGORIES)
        self.assertIn(d["priority"], PRIORITIES)
        self.assertIn(d["next_action"], NEXT_ACTIONS)
        self.assertIsInstance(d["answered"], bool)
        self.assertIsInstance(d["summary"], str)

    def test_lease_notice_is_urgent(self):
        d = decide("do I need to give notice on my apartment", *sample("apartment-lease-2026.md"), TODAY)
        self.check_schema(d)
        self.assertEqual((d["category"], d["priority"], d["next_action"], d["due"]),
                         ("home", "high", "act_now", "2026-12-02"))
        self.assertIn("notice deadline", d["action_item"])
        self.assertEqual(d["action_from"], "To do")

    def test_car_insurance_is_a_follow_up_call(self):
        d = decide("when does my car insurance renew", *sample("car-insurance-renewal.md"), TODAY)
        self.check_schema(d)
        self.assertEqual((d["category"], d["priority"], d["next_action"], d["due"]),
                         ("finance", "medium", "follow_up", "2026-12-10"))
        self.assertTrue(d["action_item"].startswith("Call Harbourline before 10 December"))
        self.assertNotIn("**", d["action_item"])

    def test_dentist_claim_picks_matching_todo(self):
        d = decide("has my filling claim been reimbursed", *sample("dentist-visit-notes.md"), TODAY)
        self.assertEqual((d["category"], d["next_action"], d["due"]), ("health", "follow_up", "2026-12-04"))
        self.assertIn("$180 filling claim", d["action_item"])

    def test_recipe_has_no_action(self):
        d = decide("how long should sourdough proof", *sample("sourdough-recipe.md"), TODAY)
        self.check_schema(d)
        self.assertEqual((d["category"], d["next_action"], d["action_item"]), ("personal", "review", None))
        self.assertIsNone(d["action_from"])

    def test_trip_and_warranty_categories(self):
        self.assertEqual(decide("trip", *sample("lisbon-trip-itinerary.md"), TODAY)["category"], "travel")
        self.assertEqual(decide("warranty", *sample("laptop-warranty.md"), TODAY)["category"], "purchases")
        self.assertEqual(decide("tax", *sample("2026-tax-receipts.md"), TODAY)["category"], "finance")
        self.assertEqual(decide("ideas", *sample("side-project-ideas.md"), TODAY)["category"], "work")

    def test_trip_prefers_urgent_todo_over_shared_filler_word(self):
        d = decide("what should I sort out before the Lisbon trip", *sample("lisbon-trip-itinerary.md"), TODAY)
        self.assertEqual(d["action_item"], "Buy travel insurance this week. The flights are non-refundable.")
        self.assertEqual((d["priority"], d["next_action"], d["due"]), ("high", "act_now", None))

    def test_laptop_undated_urgent_todo_gets_no_borrowed_date(self):
        d = decide("is my laptop still under warranty", *sample("laptop-warranty.md"), TODAY)
        self.assertIn("trackpad warranty claim this week", d["action_item"])
        self.assertEqual((d["priority"], d["next_action"], d["due"]), ("high", "act_now", None))

    def test_low_score_is_not_answered(self):
        d = decide("what is the capital of France", *sample("lisbon-trip-itinerary.md", score=0.18), TODAY)
        self.check_schema(d)
        self.assertEqual((d["answered"], d["source_file"], d["next_action"]), (False, None, "none"))

    def test_no_matches_is_not_answered(self):
        d = decide("anything", [], [], TODAY)
        self.assertFalse(d["answered"])
        self.assertEqual(d["matches"], [])

    def test_falls_back_to_matched_chunks_without_full_doc(self):
        matches, chunks = sample("apartment-lease-2026.md")
        d = decide("give notice", matches, [], TODAY)
        self.assertTrue(d["answered"])
        self.assertEqual(d["source_file"], "apartment-lease-2026.md")


class FindDatesTest(unittest.TestCase):
    def test_formats(self):
        text = "15 December 2026, Dec 16, 2 December, 2026-12-20, Tue 23 Dec, March 3rd"
        self.assertEqual(find_dates(text, TODAY), [
            dt.date(2026, 12, 15), dt.date(2026, 12, 2), dt.date(2026, 12, 23),
            dt.date(2026, 12, 16), dt.date(2027, 3, 3), dt.date(2026, 12, 20),
        ])

    def test_year_inference(self):
        self.assertEqual(find_dates("18 November", TODAY), [dt.date(2026, 11, 18)])  # recent past
        self.assertEqual(find_dates("1 January", TODAY), [dt.date(2027, 1, 1)])  # rolls forward

    def test_does_not_join_lines(self):
        self.assertEqual(find_dates("Options before 28 December\n\n1. Open a claim", TODAY),
                         [dt.date(2026, 12, 28)])

    def test_ignores_invalid_and_month_only(self):
        self.assertEqual(find_dates("31 February, April 2027, 01/27", TODAY), [])


class FakeNest:
    def __init__(self, chunks, score):
        self.chunks, self.score = chunks, score
        self.fetched = []

    def embed(self, texts, input_type):
        assert input_type == "query"
        return [[0.0]]

    def query(self, vector, top_k):
        return [{"score": self.score, "metadata": {"file_id": "F", "file_name": "apartment-lease-2026.md",
                                                   "chunk_index": 0, "chunk_text": self.chunks[0]}}]

    def fetch(self, ids):
        self.fetched = ids
        return {f"F#{i}": {"metadata": {"chunk_text": c}} for i, c in enumerate(self.chunks)}


class AskTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        (self.dir / "nest.json").write_text(json.dumps({"files": {"F": {"chunks": 5}}}))
        self.chunks = chunk_text((SAMPLES / "apartment-lease-2026.md").read_text())
        self.now = dt.datetime(2026, 11, 25, 12, 0, tzinfo=dt.timezone.utc)

    def tearDown(self):
        self.tmp.cleanup()

    def run_ask(self, nest):
        return ask("give notice on the apartment", nest, self.dir / "nest.json", self.dir / "history", self.now)

    def test_fetches_whole_file_and_logs_history(self):
        nest = FakeNest(self.chunks, 0.4)
        d = self.run_ask(nest)
        self.assertEqual(nest.fetched, [f"F#{i}" for i in range(5)])
        self.assertEqual(d["due"], "2026-12-02")  # from the To do chunk, which query alone didn't return
        lines = (self.dir / "history" / "2026-11-25.jsonl").read_text().splitlines()
        self.assertEqual(json.loads(lines[0])["question"], "give notice on the apartment")

    def test_low_score_skips_fetch(self):
        nest = FakeNest(self.chunks, 0.1)
        self.assertFalse(self.run_ask(nest)["answered"])
        self.assertEqual(nest.fetched, [])


if __name__ == "__main__":
    unittest.main()
