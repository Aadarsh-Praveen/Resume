"""
Tests for pipeline/dedup.py — uses a temporary file-based SQLite DB.

Note: SQLite :memory: databases create a new empty database per connection,
so we use a NamedTemporaryFile to get a persistent file for the test session.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.dedup import init_db, is_duplicate, insert_job, get_unprocessed_jobs, mark_processed, get_job


class TestDedup(unittest.TestCase):

    def setUp(self):
        """Create a fresh temporary database file for each test."""
        self._tmpfile = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmpfile.close()
        self.db = self._tmpfile.name
        init_db(self.db)

    def tearDown(self):
        os.unlink(self.db)

    # ── init_db ──────────────────────────────────────────────────────────────

    def test_init_db_creates_table(self):
        # Calling twice is idempotent
        init_db(self.db)

    # ── is_duplicate ─────────────────────────────────────────────────────────

    def test_new_job_is_not_duplicate(self):
        self.assertFalse(is_duplicate("Stripe", "Data Scientist", self.db))

    def test_existing_job_is_duplicate(self):
        insert_job({"title": "Data Scientist", "company": "Stripe", "url": "https://example.com"}, self.db)
        self.assertTrue(is_duplicate("Stripe", "Data Scientist", self.db))

    def test_same_title_different_company_not_duplicate(self):
        insert_job({"title": "Data Scientist", "company": "Stripe", "url": "https://a.com"}, self.db)
        self.assertFalse(is_duplicate("Airbnb", "Data Scientist", self.db))

    def test_case_insensitive_company_strip(self):
        insert_job({"title": "ML Engineer", "company": "OpenAI", "url": "https://b.com"}, self.db)
        # Leading/trailing spaces should be stripped
        self.assertTrue(is_duplicate("  OpenAI  ", "ML Engineer", self.db))

    # ── insert_job ───────────────────────────────────────────────────────────

    def test_insert_returns_id(self):
        job_id = insert_job({"title": "AI Engineer", "company": "Anthropic", "url": "https://c.com"}, self.db)
        self.assertIsInstance(job_id, int)
        self.assertGreater(job_id, 0)

    def test_insert_stores_all_fields(self):
        job_id = insert_job({
            "title": "Senior Data Scientist",
            "company": "Databricks",
            "url": "https://d.com",
            "jd_text": "We need Python expertise",
            "source": "greenhouse",
            "posted_date": "2026-04-07",
        }, self.db)
        row = get_job(job_id, self.db)
        self.assertEqual(row["title"], "Senior Data Scientist")
        self.assertEqual(row["company"], "Databricks")
        self.assertEqual(row["source"], "greenhouse")
        self.assertEqual(row["jd_text"], "We need Python expertise")

    # ── get_unprocessed_jobs ─────────────────────────────────────────────────

    def test_get_unprocessed_returns_only_unprocessed(self):
        id1 = insert_job({"title": "Job A", "company": "Co A", "url": "https://e.com"}, self.db)
        id2 = insert_job({"title": "Job B", "company": "Co B", "url": "https://f.com"}, self.db)
        mark_processed(id1, "/resumes/a.pdf", 91.0, "ready", self.db)

        jobs = get_unprocessed_jobs(self.db)
        ids = [j["id"] for j in jobs]
        self.assertNotIn(id1, ids)
        self.assertIn(id2, ids)

    def test_get_unprocessed_empty_when_all_done(self):
        job_id = insert_job({"title": "Job X", "company": "Co X", "url": "https://g.com"}, self.db)
        mark_processed(job_id, "/resumes/x.pdf", 90.0, "ready", self.db)
        self.assertEqual(get_unprocessed_jobs(self.db), [])

    # ── mark_processed ───────────────────────────────────────────────────────

    def test_mark_processed_updates_fields(self):
        job_id = insert_job({"title": "Job Y", "company": "Co Y", "url": "https://h.com"}, self.db)
        mark_processed(job_id, "/resumes/y.pdf", 89.5, "ready", self.db)

        row = get_job(job_id, self.db)
        self.assertEqual(row["processed"], 1)
        self.assertEqual(row["pdf_path"], "/resumes/y.pdf")
        self.assertAlmostEqual(row["ats_score"], 89.5)
        self.assertEqual(row["status"], "ready")

    def test_mark_processed_with_none_values(self):
        job_id = insert_job({"title": "Job Z", "company": "Co Z", "url": "https://i.com"}, self.db)
        mark_processed(job_id, None, None, "failed", self.db)

        row = get_job(job_id, self.db)
        self.assertEqual(row["processed"], 1)
        self.assertIsNone(row["pdf_path"])
        self.assertEqual(row["status"], "failed")


if __name__ == "__main__":
    unittest.main()
