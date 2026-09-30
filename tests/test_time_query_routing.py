"""
Regression Test Suite: Deterministic Local Time Query Intent Detection & Routing.

Validates that:
1. All natural conversational variants of a local time request normalize and resolve
   deterministically via the local OS clock (datetime.now()) with zero LLM generation.
2. Conversational prefixes (can you, could you, please, tell me, do you know, etc.)
   do not prevent detection.
3. Contractions (what's, wt's) and casual typing (wt, u, pls) are normalized.
4. Metadata preserves: networkUsed=False, localClock=True, isOffline=True.
5. Actual current system time is reflected (not hardcoded).
6. Conceptual questions (What is time?, Explain time dilation) are strictly preserved
   for General AI / LLM processing.
7. Remote location queries (What time is it in Tokyo?) trigger truthful remote-location
   behavior and are not confused with local clock queries.
"""

import os
import unittest
from datetime import datetime

os.environ["AIGIS_COMPETITION_MODE"] = "true"

from ai_engine.engine.router import IntentTaskRouter
from ai_engine.engine.deterministic import parse_time_date_query


class TestTimeQueryRouting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.router = IntentTaskRouter()

    def test_01_local_time_exact_cases(self):
        """
        Tests the exact required user test cases:
        - "What is the time?"
        - "What's the time?"
        - "can you tell me the time?"
        - "Can you tell me what the time is?"
        - "wt is the time"
        - "what time is it now?"
        - "please tell me the current time"
        - "Do you know what time it is?"
        """
        cases = [
            "What is the time?",
            "What's the time?",
            "can you tell me the time?",
            "Can you tell me what the time is?",
            "wt is the time",
            "what time is it now?",
            "please tell me the current time",
            "Do you know what time it is?",
        ]

        for query in cases:
            with self.subTest(query=query):
                # 1. Deterministic parser verification
                is_time, is_date, is_remote = parse_time_date_query(query)
                self.assertTrue(is_time, f"Failed parse_time_date_query for: {query}")
                self.assertFalse(is_remote, f"Incorrectly marked remote for: {query}")

                # 2. Router classification verification
                classification = self.router.classify_intent(query)
                self.assertEqual(classification["intent"], "SYSTEM_INFO", f"Wrong intent for: {query}")
                self.assertIn(classification.get("systemInfoType"), ["time", "time_date"])

                # 3. Router generation verification
                resp = self.router.route_and_generate(query)
                self.assertEqual(resp.metadata.get("intent"), "time")
                self.assertTrue(resp.metadata.get("localClock"), f"localClock flag missing for: {query}")
                self.assertFalse(resp.metadata.get("networkUsed", True), f"networkUsed should be False for: {query}")
                self.assertTrue(resp.metadata.get("isOffline", False), f"isOffline should be True for: {query}")

                # 4. Actual system time verification (not hardcoded)
                now = datetime.now()
                expected_hour_12 = now.strftime("%I")
                expected_ampm = now.strftime("%p")
                self.assertIn(expected_ampm, resp.reply)
                self.assertIn(expected_hour_12, resp.reply)
                self.assertIn("The current time is", resp.reply)

                # 5. Zero LLM disclaimer / garbage text
                disclaimers = [
                    "I'm programmed to provide",
                    "I'm not programmed to provide specific time",
                    "check your watch",
                    "large language model",
                    "don't have access to your device",
                ]
                for d in disclaimers:
                    self.assertNotIn(d, resp.reply)

    def test_02_additional_conversational_and_casual_variants(self):
        """
        Tests additional conversational, polite, casual, and typo-tolerant variations:
        - what is the time
        - Could you tell me the time?
        - Do you know the time?
        - What time is it?
        - What's the current time?
        - Tell me the current time
        - Please tell me the time
        - What is the current time?
        - wt's the time
        - can u tell me the time
        - can you tell me wt the time is
        - would you tell me the time?
        """
        additional_cases = [
            "what is the time",
            "Could you tell me the time?",
            "Do you know the time?",
            "What time is it?",
            "What's the current time?",
            "Tell me the current time",
            "Please tell me the time",
            "What is the current time?",
            "wt's the time",
            "can u tell me the time",
            "can you tell me wt the time is",
            "would you tell me the time?",
            "pls tell me the time",
            "can u pls tell me what time it is",
        ]

        for query in additional_cases:
            with self.subTest(query=query):
                is_time, is_date, is_remote = parse_time_date_query(query)
                self.assertTrue(is_time, f"Failed parse_time_date_query for: {query}")
                self.assertFalse(is_remote, f"Incorrectly marked remote for: {query}")

                resp = self.router.route_and_generate(query)
                self.assertEqual(resp.metadata.get("intent"), "time")
                self.assertTrue(resp.metadata.get("localClock"))
                self.assertFalse(resp.metadata.get("networkUsed", True))
                self.assertTrue(resp.metadata.get("isOffline", False))
                self.assertIn("The current time is", resp.reply)

    def test_03_conceptual_questions_protected_for_general_ai(self):
        """
        Tests that conceptual questions are NEVER treated as clock requests:
        - "what is time?"
        - "Explain time dilation"
        - "What does time mean?"
        - "Explain time travel"
        - "What is spacetime?"
        """
        conceptual_queries = [
            "what is time?",
            "Explain time dilation",
            "What does time mean?",
            "Explain time travel",
            "what is spacetime",
            "concept of time",
            "how does time work",
        ]

        for query in conceptual_queries:
            with self.subTest(query=query):
                is_time, is_date, is_remote = parse_time_date_query(query)
                self.assertFalse(is_time, f"Conceptual query falsely marked as time: {query}")
                self.assertFalse(is_date, f"Conceptual query falsely marked as date: {query}")

                classification = self.router.classify_intent(query)
                self.assertEqual(classification["intent"], "GENERAL_AI", f"Expected GENERAL_AI for: {query}")

    def test_04_remote_location_time_preserved(self):
        """
        Tests that remote location queries:
        - "What time is it in Tokyo?"
        - "What's the time in London?"
        are not confused with local clock requests and trigger truthful remote handling.
        """
        remote_queries = [
            "What time is it in Tokyo?",
            "What's the time in London?",
            "can you tell me the time in Paris?",
        ]

        for query in remote_queries:
            with self.subTest(query=query):
                is_time, is_date, is_remote = parse_time_date_query(query)
                self.assertTrue(is_remote, f"Expected is_remote=True for: {query}")
                self.assertFalse(is_time, f"Remote query should have is_time=False for local: {query}")

                # Under competition mode, router routes remote time to local guard response truthfully
                classification = self.router.classify_intent(query)
                self.assertEqual(classification["intent"], "LIVE_WEB")

                resp = self.router.route_and_generate(query)
                self.assertNotIn("The current time is", resp.reply)
                self.assertIn("cannot be verified in", resp.reply)


if __name__ == "__main__":
    unittest.main()
