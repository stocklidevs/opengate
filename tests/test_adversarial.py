from __future__ import annotations

import unittest

from open_gate.adversarial import run_adversarial_checks


class AdversarialNormalizerTests(unittest.TestCase):
    def test_glm_tag_whitespace_fuzz_does_not_leak(self) -> None:
        failures = run_adversarial_checks(iterations=75, seed=6047)

        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
