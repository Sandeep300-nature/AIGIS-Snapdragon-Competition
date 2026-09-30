"""
Test Suite: Voice Interaction & Response Presentation Polish.
Covers:
1. TTS symbol and formatting cleanup (avoiding reading markdown/symbols aloud).
2. AIGIS pronunciation normalization (AIGIS / A-I-G-I-S / A I G I S -> Aigis).
3. Qwen3-4B and GenieX speech normalization.
4. Technical hyphen normalization (on-device -> on device, real-time -> real time).
5. STT conservative normalization (A I G I S / A-I-G-I-S -> AIGIS, whitespace cleanup).
6. Response immutability: Displayed response object remains completely unchanged for UI.
7. Competition system prompt personality validation.
"""

import unittest
from ai_engine.engine.speech_sanitizer import sanitize_speech_text, normalize_stt_transcript
from ai_engine.engine.prompts import AIGIS_COMPETITION_SYSTEM_PROMPT, get_competition_system_prompt


class TestSpeechVoicePolish(unittest.TestCase):
    """Focused tests for competition version's voice interaction and response presentation."""

    # --------------------------------------------------------------------------
    # 1. TTS Symbol and Markdown Formatting Cleanup
    # --------------------------------------------------------------------------
    def test_01_markdown_formatting_symbols_cleaned_for_tts(self):
        """Verifies markdown markers (bold, italics, code, headers) are not read aloud."""
        # Bold and italics
        raw = "This is **extremely important** and *noteworthy*."
        spoken = sanitize_speech_text(raw)
        self.assertEqual(spoken, "This is extremely important and noteworthy.")
        self.assertNotIn("*", spoken)

        # Inline code backticks
        raw_code = "Inspect `config.json` and run `execute_task()`."
        spoken_code = sanitize_speech_text(raw_code)
        self.assertEqual(spoken_code, "Inspect config.json and run execute task.")
        self.assertNotIn("`", spoken_code)

        # Markdown headings
        raw_heading = "# System Overview\n## Hardware Status\n### NPU Diagnostics"
        spoken_heading = sanitize_speech_text(raw_heading)
        self.assertEqual(spoken_heading, "System Overview\nHardware Status\nNPU Diagnostics")
        self.assertNotIn("#", spoken_heading)

        # Code blocks
        raw_block = "Here is the snippet:\n```python\nx = 42\nprint(x)\n```\nDone."
        spoken_block = sanitize_speech_text(raw_block)
        self.assertNotIn("```", spoken_block)
        self.assertIn("x = 42", spoken_block)
        self.assertIn("print x", spoken_block)
        self.assertNotIn("(", spoken_block)
        self.assertNotIn(")", spoken_block)

    def test_02_brackets_braces_parentheses_cleanup(self):
        """Verifies brackets, braces, and parentheses are not read as punctuation names."""
        raw = "The model is [local], data is {encrypted}, and settings are (private)."
        spoken = sanitize_speech_text(raw)
        self.assertEqual(spoken, "The model is local, data is encrypted, and settings are private.")
        for symbol in ["[", "]", "{", "}", "(", ")"]:
            self.assertNotIn(symbol, spoken)

    def test_03_bullets_and_dividers_cleanup(self):
        """Verifies list bullets and separator lines are cleaned for natural speech."""
        raw = "Features:\n- First capability\n* Second capability\n• Third capability\n---\nAll verified."
        spoken = sanitize_speech_text(raw)
        self.assertNotIn("- First", spoken)
        self.assertNotIn("* Second", spoken)
        self.assertNotIn("• Third", spoken)
        self.assertNotIn("---", spoken)
        self.assertIn("First capability", spoken)
        self.assertIn("Second capability", spoken)
        self.assertIn("Third capability", spoken)
        self.assertIn("All verified.", spoken)

    def test_04_emoji_and_decorative_cleanup(self):
        """Verifies status emojis are stripped so TTS does not speak emoji names."""
        raw = "⚡ Fast on-device inference with 🛡️ Action Guard and 🌐 Web Search."
        spoken = sanitize_speech_text(raw)
        self.assertNotIn("⚡", spoken)
        self.assertNotIn("🛡️", spoken)
        self.assertNotIn("🌐", spoken)
        self.assertIn("Fast on device inference", spoken)

    # --------------------------------------------------------------------------
    # 2. AIGIS Pronunciation Normalization
    # --------------------------------------------------------------------------
    def test_05_aigis_pronunciation_mappings(self):
        """Verifies AIGIS variations are normalized to 'Aigis' for natural speech pronunciation."""
        cases = [
            ("I am AIGIS, your assistant.", "I am Aigis, your assistant."),
            ("Hello from A-I-G-I-S system.", "Hello from Aigis system."),
            ("Call me A I G I S whenever needed.", "Call me Aigis whenever needed."),
            ("Welcome to A.I.G.I.S. on-device.", "Welcome to Aigis on device."),
        ]
        for raw, expected in cases:
            spoken = sanitize_speech_text(raw)
            self.assertEqual(spoken, expected)

    # --------------------------------------------------------------------------
    # 3. Qwen3 and GenieX Speech Normalization
    # --------------------------------------------------------------------------
    def test_06_qwen3_and_geniex_speech_mappings(self):
        """Verifies GenieX and Qwen3-4B are mapped for natural conversational speech."""
        raw = "Running Qwen3-4B accelerated by Qualcomm GenieX provider."
        spoken = sanitize_speech_text(raw)
        self.assertIn("Qwen 3 4B", spoken)
        self.assertIn("Genie X", spoken)
        self.assertEqual(spoken, "Running Qwen 3 4B accelerated by Qualcomm Genie X provider.")

    # --------------------------------------------------------------------------
    # 4. Technical Hyphen Normalization
    # --------------------------------------------------------------------------
    def test_07_technical_hyphens_become_natural_pauses(self):
        """Verifies technical hyphens become spaces/pauses rather than spoken 'hyphen'."""
        cases = [
            ("Execution is on-device.", "Execution is on device."),
            ("Processing telemetry in real-time.", "Processing telemetry in real time."),
            ("Includes built-in privacy protection.", "Includes built in privacy protection."),
        ]
        for raw, expected in cases:
            spoken = sanitize_speech_text(raw)
            self.assertEqual(spoken, expected)

    # --------------------------------------------------------------------------
    # 5. Speech-to-Text (STT) Conservative Normalization
    # --------------------------------------------------------------------------
    def test_08_stt_conservative_normalization(self):
        """Verifies STT normalizes AIGIS brand spellings and whitespace while preserving user intent."""
        # A I G I S -> AIGIS
        t1 = normalize_stt_transcript("Hello   A I G I S   what time is it?")
        self.assertEqual(t1, "Hello AIGIS what time is it?")

        # A-I-G-I-S -> AIGIS
        t2 = normalize_stt_transcript("wake up A-I-G-I-S please")
        self.assertEqual(t2, "wake up AIGIS please")

        # A.I.G.I.S. -> AIGIS
        t3 = normalize_stt_transcript("is A.I.G.I.S. running?")
        self.assertEqual(t3, "is AIGIS running?")

        # Preserves user's intended wording without aggressive autocorrect
        t4 = normalize_stt_transcript("launch notepad and check my project notes")
        self.assertEqual(t4, "launch notepad and check my project notes")

        # Accidental whitespace cleanup
        t5 = normalize_stt_transcript("   turn    on   the    microphone   ")
        self.assertEqual(t5, "turn on the microphone")

    # --------------------------------------------------------------------------
    # 6. Response Immutability (Displayed Response Unchanged)
    # --------------------------------------------------------------------------
    def test_09_original_response_remains_completely_unchanged(self):
        """Verifies the original response string/object is not mutated by speech sanitization."""
        original_ui_response = (
            "### System Status\n"
            "* **NPU Engine**: [Active]\n"
            "* **Model**: `Qwen3-4B` via GenieX\n"
            "* **Privacy**: {Guarded} (on-device)\n"
            "---\n"
            "AIGIS is ready."
        )

        # Generate separate speech-only string
        speech_string = sanitize_speech_text(original_ui_response)

        # 1. Original response retains full markdown structure
        self.assertIn("### System Status", original_ui_response)
        self.assertIn("**NPU Engine**", original_ui_response)
        self.assertIn("[Active]", original_ui_response)
        self.assertIn("`Qwen3-4B`", original_ui_response)
        self.assertIn("{Guarded}", original_ui_response)
        self.assertIn("---", original_ui_response)
        self.assertIn("AIGIS", original_ui_response)

        # 2. Speech string is sanitized for natural speech
        self.assertNotIn("###", speech_string)
        self.assertNotIn("**", speech_string)
        self.assertNotIn("[", speech_string)
        self.assertNotIn("]", speech_string)
        self.assertNotIn("`", speech_string)
        self.assertNotIn("{", speech_string)
        self.assertNotIn("}", speech_string)
        self.assertNotIn("---", speech_string)
        self.assertIn("Qwen 3 4B", speech_string)
        self.assertIn("Genie X", speech_string)
        self.assertIn("Aigis", speech_string)
        self.assertIn("on device", speech_string)

    # --------------------------------------------------------------------------
    # 7. Competition System Prompt Personality Validation
    # --------------------------------------------------------------------------
    def test_10_competition_system_prompt_personality(self):
        """Verifies the competition system prompt contains all required personality instructions."""
        prompt = get_competition_system_prompt()

        # Core Snapdragon platform attributes
        self.assertIn("powered by Qualcomm Snapdragon", prompt)
        self.assertIn("friendly and autonomous on-device personal AI assistant", prompt)
        self.assertIn("Prioritize concise, clear answers", prompt)
        self.assertIn("Your name is AIGIS.", prompt)

        # Conversational and voice-first personality
        self.assertIn("Prefer natural conversational language.", prompt)
        self.assertIn("Avoid unnecessary symbols, excessive Markdown, raw formatting characters", prompt)
        self.assertIn("When giving an answer intended to be spoken aloud, use natural language", prompt)
        self.assertIn("Refer to yourself as Aigis in spoken conversation.", prompt)

        # Truthfulness / no false claims
        self.assertIn("never pretend to have performed an action that you did not actually perform.", prompt)

    # --------------------------------------------------------------------------
    # 8. Competition Version Label Validation
    # --------------------------------------------------------------------------
    def test_11_competition_version_label_rendering(self):
        """Verifies the competition version label is present in the frontend UI source and styled."""
        import os

        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        navbar_jsx = os.path.join(repo_root, "frontend", "src", "Navbar.jsx")
        navbar_css = os.path.join(repo_root, "frontend", "src", "Navbar.css")

        self.assertTrue(os.path.exists(navbar_jsx), "Navbar.jsx must exist")
        self.assertTrue(os.path.exists(navbar_css), "Navbar.css must exist")

        with open(navbar_jsx, "r", encoding="utf-8") as f:
            jsx_content = f.read()

        with open(navbar_css, "r", encoding="utf-8") as f:
            css_content = f.read()

        # Unobtrusive version/build label in brand section
        self.assertIn("(Snapdragon Competition v_3)", jsx_content)
        self.assertIn("brand-competition-label", jsx_content)

        # CSS styling exists for the label
        self.assertIn(".brand-competition-label", css_content)

    # --------------------------------------------------------------------------
    # 9. Structured Hardware Telemetry Report (Requirement 8)
    # --------------------------------------------------------------------------
    def test_12_structured_hardware_telemetry_report(self):
        """
        Verifies structured telemetry reports are transformed into natural spoken sentences
        with sentence boundaries and pauses, rather than a single flat stream of words.
        """
        raw_telemetry = (
            "Workstation Hardware Telemetry, sir:\n\n"
            "• Device Environment: Development Environment — x64\n"
            "• Architecture: x86_64\n"
            "• Processor: Intel(R) Core(TM) 5 210H (12 threads)\n"
            "• Physical GPU: NVIDIA GeForce RTX 4050 Laptop GPU\n"
            "• Snapdragon NPU Status: Not detected (running on x64 development machine)\n"
            "• Active AI Execution Runtime: Local On-Device (x86_64 CPU)"
        )

        spoken = sanitize_speech_text(raw_telemetry)

        # 1. Structure is preserved as distinct spoken lines/sentences
        lines = spoken.split("\n")
        self.assertGreaterEqual(len(lines), 6)

        # 2. Intro line ends with period instead of colon
        self.assertTrue(lines[0].startswith("Workstation Hardware Telemetry, sir"))
        self.assertTrue(lines[0].endswith("."))

        # 3. Bullets are removed and each list item ends with terminal punctuation
        for line in lines[1:]:
            self.assertFalse(line.startswith("•"), f"Bullet not removed from line: {line}")
            self.assertTrue(line.endswith((".", "!", "?")), f"Line lacks terminal punctuation: {line}")

        # 4. Em-dash converted to natural comma pause
        self.assertIn("Development Environment, x64", spoken)
        self.assertNotIn("—", spoken)

        # 5. Architecture identifier x86_64 converted to x86-64
        self.assertIn("Architecture: x86-64", spoken)

        # 6. Trademarks (R) and (TM) stripped cleanly
        self.assertIn("Processor: Intel Core 5 210H, 12 threads", spoken)
        self.assertNotIn("(R)", spoken)
        self.assertNotIn("(TM)", spoken)
        self.assertNotIn("Intel R", spoken)

        # 7. Parenthetical clause converted naturally
        self.assertIn("Snapdragon NPU Status: Not detected. The system is running on an x64 development machine", spoken)

        # 8. Runtime line with x86-64 CPU parenthetical
        self.assertIn("Active AI Execution Runtime: Local On Device, x86-64 CPU", spoken)

    # --------------------------------------------------------------------------
    # 10. Normal Conversational Text
    # --------------------------------------------------------------------------
    def test_13_normal_conversational_text(self):
        """Verifies normal conversational prose preserves natural sentence flow and punctuation."""
        raw = "Good morning, sir. I am ready to assist you with your tasks today. How may I help?"
        spoken = sanitize_speech_text(raw)
        self.assertEqual(spoken, "Good morning, sir. I am ready to assist you with your tasks today. How may I help?")

    # --------------------------------------------------------------------------
    # 11. Markdown Response Formatting
    # --------------------------------------------------------------------------
    def test_14_markdown_response_preservation(self):
        """Verifies markdown bold, links, code, and headers are cleaned while preserving text."""
        raw = (
            "# System Report\n"
            "**Status:** Operational\n"
            "Refer to [documentation](https://example.com/docs) or `settings.yaml`."
        )
        spoken = sanitize_speech_text(raw)
        self.assertNotIn("#", spoken)
        self.assertNotIn("**", spoken)
        self.assertNotIn("[", spoken)
        self.assertNotIn("]", spoken)
        self.assertNotIn("`", spoken)
        self.assertNotIn("https://", spoken)
        self.assertIn("System Report", spoken)
        self.assertIn("Status: Operational", spoken)
        self.assertIn("documentation", spoken)
        self.assertIn("settings.yaml", spoken)

    # --------------------------------------------------------------------------
    # 12. Parentheses Clause Handling
    # --------------------------------------------------------------------------
    def test_15_parentheses_clause_handling(self):
        """Verifies parentheses information is preserved naturally without reading symbol names."""
        cases = [
            ("Core configuration: 8 cores (16 threads).", "Core configuration: 8 cores, 16 threads."),
            ("The memory is (unified LPDDR5X).", "The memory is unified LPDDR5X."),
            ("System status is (online).", "System status is online."),
            ("Running local NPU (x86_64 CPU fallback).", "Running local NPU, x86-64 CPU fallback."),
        ]
        for raw, expected in cases:
            spoken = sanitize_speech_text(raw)
            self.assertEqual(spoken, expected)
            self.assertNotIn("(", spoken)
            self.assertNotIn(")", spoken)

    # --------------------------------------------------------------------------
    # 13. Technical Identifiers
    # --------------------------------------------------------------------------
    def test_16_technical_identifiers(self):
        """Verifies technical identifiers preserve semantic meaning without character mangling."""
        raw = "Running Qwen3-4B on-device in real-time with built-in Snapdragon acceleration on x86_64 architecture."
        spoken = sanitize_speech_text(raw)
        self.assertIn("Qwen 3 4B", spoken)
        self.assertIn("on device", spoken)
        self.assertIn("real time", spoken)
        self.assertIn("built in", spoken)
        self.assertIn("x86-64", spoken)

    # --------------------------------------------------------------------------
    # 14. Mixed Prose + Structured Report
    # --------------------------------------------------------------------------
    def test_17_mixed_prose_and_structured_report(self):
        """Verifies mixed prose followed by a bullet list and a concluding remark."""
        raw = (
            "Here is the hardware summary, sir:\n\n"
            "• CPU: Intel Core 5\n"
            "• NPU: Qualcomm Hexagon\n"
            "• Memory: 16 GB\n\n"
            "All hardware components are verified and operational."
        )
        spoken = sanitize_speech_text(raw)
        lines = spoken.split("\n")
        self.assertEqual(len(lines), 5)
        self.assertEqual(lines[0], "Here is the hardware summary, sir.")
        self.assertEqual(lines[1], "CPU: Intel Core 5.")
        self.assertEqual(lines[2], "NPU: Qualcomm Hexagon.")
        self.assertEqual(lines[3], "Memory: 16 GB.")
        self.assertEqual(lines[4], "All hardware components are verified and operational.")

    # --------------------------------------------------------------------------
    # 15. TTS Never Pronounces Symbol Names
    # --------------------------------------------------------------------------
    def test_18_tts_never_receives_symbol_names(self):
        """Verifies the TTS string never contains literal words like 'opening bracket', 'asterisk', etc."""
        raw = "System [status] {mode} (threads) *bold* _italic_ - item # header"
        spoken = sanitize_speech_text(raw)
        forbidden_phrases = [
            "opening bracket", "closing bracket",
            "opening brace", "closing brace",
            "opening parenthesis", "closing parenthesis",
            "open bracket", "close bracket",
            "open brace", "close brace",
            "open parenthesis", "close parenthesis",
            "asterisk", "hyphen", "underscore"
        ]
        for phrase in forbidden_phrases:
            self.assertNotIn(phrase, spoken.lower())


if __name__ == "__main__":
    unittest.main()
