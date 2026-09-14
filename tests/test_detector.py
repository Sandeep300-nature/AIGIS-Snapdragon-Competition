import os
import sys
import unittest

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from ai_engine.hardware.test_detector import TestHardwareDetector

__all__ = ["TestHardwareDetector"]

if __name__ == "__main__":
    unittest.main()
