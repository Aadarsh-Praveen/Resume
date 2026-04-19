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

from pipeline.dedup import (
    init_db, is_duplicate, insert_job, get_unprocessed_jobs, mark_processed, get_job,
    insert_recruiter, get_all_recruiters, update_recruiter, get_recruiter_stats,
    get_weekly_submissions, get_ats_distribution, get_funnel_data, get_portal_mix,
    mark_applied, get_stats,
)


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

    def test_init_db_creates_recruiters_table(self):
        # recruiters table must exist after init
        import sqlite3
        with sqlite3.connect(self.db) as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='recruiters'"
            ).fetchone()
        self.assertIsNotNone(row)

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

    # ── Recruiter functions ───────────────────────────────────────────────────

    def _make_job(self, company="Acme", title="ML Engineer"):
        return insert_job({"title": title, "company": company, "url": "https://x.com"}, self.db)

    def test_insert_recruiter_returns_id(self):
        job_id = self._make_job()
        rec = {"name": "Alice Smith", "title": "Head of Talent", "company": "Acme",
               "email": "alice@acme.com", "linkedin_url": "https://linkedin.com/in/alice"}
        rid = insert_recruiter(job_id, rec, "Hi Alice...", self.db)
        self.assertIsInstance(rid, int)
        self.assertGreater(rid, 0)

    def test_get_all_recruiters_returns_inserted(self):
        job_id = self._make_job()
        rec = {"name": "Bob Jones", "title": "Recruiter", "company": "Acme",
               "email": "bob@acme.com", "linkedin_url": None}
        insert_recruiter(job_id, rec, None, self.db)
        rows = get_all_recruiters(db_path=self.db)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Bob Jones")
        self.assertEqual(rows[0]["email_sent"], 0)

    def test_get_all_recruiters_company_filter(self):
        j1 = self._make_job("Acme")
        j2 = self._make_job("Globex")
        insert_recruiter(j1, {"name": "A", "company": "Acme", "email": "a@acme.com"}, None, self.db)
        insert_recruiter(j2, {"name": "B", "company": "Globex", "email": "b@globex.com"}, None, self.db)

        acme = get_all_recruiters(company="Acme", db_path=self.db)
        self.assertEqual(len(acme), 1)
        self.assertEqual(acme[0]["name"], "A")

    def test_update_recruiter_email_sent(self):
        job_id = self._make_job()
        rid = insert_recruiter(job_id, {"name": "C", "company": "Acme"}, None, self.db)
        update_recruiter(rid, "email_sent", 1, self.db)
        rows = get_all_recruiters(db_path=self.db)
        self.assertEqual(rows[0]["email_sent"], 1)

    def test_update_recruiter_replied_via(self):
        job_id = self._make_job()
        rid = insert_recruiter(job_id, {"name": "D", "company": "Acme"}, None, self.db)
        update_recruiter(rid, "replied", 1, self.db)
        update_recruiter(rid, "replied_via", "LinkedIn", self.db)
        rows = get_all_recruiters(db_path=self.db)
        self.assertEqual(rows[0]["replied"], 1)
        self.assertEqual(rows[0]["replied_via"], "LinkedIn")

    def test_update_recruiter_disallows_unknown_field(self):
        job_id = self._make_job()
        rid = insert_recruiter(job_id, {"name": "E", "company": "Acme"}, None, self.db)
        with self.assertRaises(ValueError):
            update_recruiter(rid, "name", "Hacked", self.db)

    def test_get_recruiter_stats(self):
        j1, j2, j3 = self._make_job(), self._make_job("B"), self._make_job("C")
        r1 = insert_recruiter(j1, {"name": "R1", "company": "Acme"}, None, self.db)
        r2 = insert_recruiter(j2, {"name": "R2", "company": "B"}, None, self.db)
        r3 = insert_recruiter(j3, {"name": "R3", "company": "C"}, None, self.db)

        update_recruiter(r1, "email_sent", 1, self.db)
        update_recruiter(r2, "email_sent", 1, self.db)
        update_recruiter(r1, "replied", 1, self.db)
        update_recruiter(r3, "linkedin_sent", 1, self.db)

        stats = get_recruiter_stats(self.db)
        self.assertEqual(stats["tracked"], 3)
        self.assertEqual(stats["emails_sent"], 2)
        self.assertEqual(stats["linkedin_sent"], 1)
        self.assertEqual(stats["replied"], 1)
        self.assertEqual(stats["companies"], 3)

    # ── Analytics functions ───────────────────────────────────────────────────

    def test_get_weekly_submissions_returns_correct_weeks(self):
        data = get_weekly_submissions(weeks=4, db_path=self.db)
        self.assertEqual(len(data), 4)
        for entry in data:
            self.assertIn("week", entry)
            self.assertIn("prepared", entry)
            self.assertIn("applied", entry)

    def test_get_weekly_submissions_counts_prepared(self):
        job_id = self._make_job()
        mark_processed(job_id, "/tmp/x.pdf", 90.0, "ready", self.db)
        data = get_weekly_submissions(weeks=1, db_path=self.db)
        # Current week's prepared count must be at least 1
        self.assertGreaterEqual(data[0]["prepared"], 1)

    def test_get_ats_distribution_all_buckets(self):
        dist = get_ats_distribution(self.db)
        buckets = [d["bucket"] for d in dist]
        self.assertIn("<60", buckets)
        self.assertIn("60-69", buckets)
        self.assertIn("70-79", buckets)
        self.assertIn("80-89", buckets)
        self.assertIn("90+", buckets)

    def test_get_ats_distribution_counts(self):
        for score in [55.0, 65.0, 75.0, 85.0, 95.0]:
            jid = insert_job({"title": f"Job {score}", "company": "Co", "url": "https://x.com"}, self.db)
            mark_processed(jid, "/tmp/x.pdf", score, "ready", self.db)

        dist = {d["bucket"]: d["count"] for d in get_ats_distribution(self.db)}
        self.assertEqual(dist["<60"], 1)
        self.assertEqual(dist["60-69"], 1)
        self.assertEqual(dist["70-79"], 1)
        self.assertEqual(dist["80-89"], 1)
        self.assertEqual(dist["90+"], 1)

    def test_get_funnel_data_structure(self):
        funnel = get_funnel_data(self.db)
        self.assertIn("discovered", funnel)
        self.assertIn("prepared", funnel)
        self.assertIn("applied", funnel)

    def test_get_funnel_data_counts(self):
        j1 = insert_job({"title": "A", "company": "X", "url": "https://a.com"}, self.db)
        j2 = insert_job({"title": "B", "company": "Y", "url": "https://b.com"}, self.db)
        mark_processed(j1, "/tmp/a.pdf", 90.0, "ready", self.db)
        mark_applied(j1, "app-123", self.db)

        funnel = get_funnel_data(self.db)
        self.assertEqual(funnel["discovered"], 2)
        self.assertEqual(funnel["prepared"], 1)
        self.assertEqual(funnel["applied"], 1)

    def test_get_portal_mix_groups_by_source(self):
        for src in ["greenhouse", "greenhouse", "lever", "ashby"]:
            insert_job({"title": "T", "company": "C", "url": f"https://{src}.com/{src}", "source": src}, self.db)

        mix = {d["source"]: d["count"] for d in get_portal_mix(self.db)}
        self.assertEqual(mix["greenhouse"], 2)
        self.assertEqual(mix["lever"], 1)
        self.assertEqual(mix["ashby"], 1)

    def test_get_portal_mix_pct_sums_to_100(self):
        for src in ["a", "b", "c", "d"]:
            insert_job({"title": "T", "company": src, "url": f"https://{src}.com", "source": src}, self.db)
        mix = get_portal_mix(self.db)
        total_pct = sum(d["pct"] for d in mix)
        self.assertAlmostEqual(total_pct, 100, delta=2)  # rounding tolerance

    def test_get_stats_counts(self):
        j1 = insert_job({"title": "A", "company": "X", "url": "https://a.com"}, self.db)
        j2 = insert_job({"title": "B", "company": "Y", "url": "https://b.com"}, self.db)
        mark_processed(j1, "/tmp/a.pdf", 90.0, "ready", self.db)
        mark_applied(j1, "app-999", self.db)

        stats = get_stats(self.db)
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats["applied"], 1)


if __name__ == "__main__":
    unittest.main()
