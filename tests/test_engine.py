import os
import sys
import unittest

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from ai_engine.engine.test_engine import TestModularAIEngine

__all__ = ["TestModularAIEngine"]

if __name__ == "__main__":
    unittest.main()
