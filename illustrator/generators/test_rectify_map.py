"""Tests for rectify_map.py (python test_rectify_map.py). Pure numpy/OpenCV."""
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rectify_map as R  # noqa: E402

try:
    import cv2  # noqa: F401
except ImportError:
    cv2 = None


class Homography(unittest.TestCase):
    def test_identity(self):
        pts = np.array([[0, 0], [10, 5], [300, 200.0]])
        self.assertTrue(np.allclose(R.apply_h(np.eye(3), pts), pts))

    def test_round_trip(self):
        H = np.array([[1.2, 0.1, 30], [-0.05, 0.9, 12], [1e-4, 2e-4, 1.0]])
        pts = np.random.RandomState(0).uniform(0, 1000, (50, 2))
        back = R.apply_h(R.invert(H), R.apply_h(H, pts))
        self.assertTrue(np.allclose(back, pts, atol=1e-6))

    def test_zero_tilt_is_similarity(self):
        Hg = R.camera_h(0, 1000, 0)
        p = R.apply_h(Hg, [(724, 543), (824, 543), (724, 643)])
        self.assertAlmostEqual(np.linalg.norm(p[1] - p[0]), np.linalg.norm(p[2] - p[0]), places=9)

    def test_tilt_foreshortens_vertical(self):
        Hg = R.camera_h(55, 1e6, 0)
        a = R.apply_h(Hg, [(724, 543), (824, 543), (724, 643)])
        ratio = np.linalg.norm(a[2] - a[0]) / np.linalg.norm(a[1] - a[0])
        self.assertAlmostEqual(ratio, 1 / np.cos(np.radians(55)), places=2)

    def test_output_round_trip(self):
        Ho, size, s = R.to_output(R.camera_h(50, 3000, 3), 1000)
        self.assertEqual(size[0], 1000)
        p = np.array([[100, 200.0], [1300, 900.0]])
        self.assertTrue(np.allclose(R.apply_h(R.invert(Ho), R.apply_h(Ho, p)), p, atol=1e-6))

    @unittest.skipUnless(cv2 is not None, "OpenCV (pip install opencv-python) not installed")
    def test_fit_makes_circle_round(self):
        best = R.fit()
        q = R.quality(R.camera_h(*best.x[:3]))
        self.assertGreater(q["circles"]["churchyard"]["rectified_axis_ratio"], 0.9)


if __name__ == "__main__":
    unittest.main()
