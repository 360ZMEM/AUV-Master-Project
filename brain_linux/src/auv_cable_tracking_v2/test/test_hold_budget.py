from __future__ import annotations

import unittest

from auv_cable_tracking_v2.hold_budget import HoldBudgetConfig, HoldBudgetMonitor


BOUNDARY = [[-270., -30.], [120., -30.], [120., 30.], [-270., 30.]]
WIDE_BOUNDARY = [[-280., -40.], [120., -40.], [120., 40.], [-280., 40.]]


def config(**overrides):
    values = dict(maximum_hold_s=30., boundary_stop_margin_m=10.,
                  zero_effort_coast_bound_m=5., current_bound_mps=.05,
                  disposition_delay_s=10., navigation_margin_m=.6,
                  maximum_navigation_age_s=.5)
    values.update(overrides)
    return HoldBudgetConfig.from_mapping(values)


class HoldBudgetTests(unittest.TestCase):
    def test_pvs_hold_position_has_no_conservative_clearance_budget(self):
        monitor = HoldBudgetMonitor(config(), BOUNDARY)
        result = monitor.evaluate(hold=True, now_s=100., position_xy_m=(-100., 15.52),
                                  navigation_age_s=.1, navigation_sigma_m=.3, covariance_age_s=.1)
        self.assertEqual(result["reason"], "hold_boundary_budget_exhausted")
        self.assertAlmostEqual(result["boundary_clearance_m"], 14.48, places=2)
        self.assertAlmostEqual(result["remaining_budget_m"], -3.12, places=2)
        self.assertTrue(monitor.evaluate(hold=False, now_s=101.)["recovery_required"])
        self.assertTrue(monitor.recovery_required)
        monitor.reset()
        self.assertFalse(monitor.recovery_required)
        self.assertFalse(monitor.evaluate(hold=False, now_s=102.)["recovery_required"])

    def test_time_expiry_even_when_boundary_is_wide(self):
        monitor = HoldBudgetMonitor(config(zero_effort_coast_bound_m=0., current_bound_mps=0.), BOUNDARY)
        initial = monitor.evaluate(hold=True, now_s=0., position_xy_m=(0., 0.),
                                   navigation_age_s=0., navigation_sigma_m=.1, covariance_age_s=0.)
        self.assertEqual(initial["state"], "WITHIN_BUDGET")
        expired = monitor.evaluate(hold=True, now_s=30., position_xy_m=(0., 0.),
                                   navigation_age_s=0., navigation_sigma_m=.1, covariance_age_s=0.)
        self.assertEqual(expired["reason"], "hold_time_budget_exhausted")

    def test_accelerated_sim_time_and_stalled_sim_clock_both_expire_hold(self):
        limits = config(zero_effort_coast_bound_m=0., current_bound_mps=0.)
        location = dict(position_xy_m=(0., 0.), navigation_age_s=0.,
                        navigation_sigma_m=.1, covariance_age_s=0.)
        accelerated = HoldBudgetMonitor(limits, BOUNDARY)
        self.assertEqual(accelerated.evaluate(
            hold=True, now_s=100., fallback_now_s=1000., **location)["state"],
            "WITHIN_BUDGET")
        result = accelerated.evaluate(
            hold=True, now_s=130., fallback_now_s=1002., **location)
        self.assertEqual(result["reason"], "hold_time_budget_exhausted")
        self.assertEqual(result["hold_elapsed_s"], 30.)

        frozen = HoldBudgetMonitor(limits, BOUNDARY)
        frozen.evaluate(hold=True, now_s=100., fallback_now_s=1000., **location)
        result = frozen.evaluate(hold=True, now_s=100., fallback_now_s=1030., **location)
        self.assertEqual(result["reason"], "hold_time_budget_exhausted")
        self.assertEqual(result["hold_elapsed_s"], 30.)

    def test_hold_clock_regression_latches_recovery(self):
        monitor = HoldBudgetMonitor(config(), BOUNDARY)
        location = dict(position_xy_m=(0., 0.), navigation_age_s=0.,
                        navigation_sigma_m=.1, covariance_age_s=0.)
        monitor.evaluate(hold=True, now_s=100., fallback_now_s=1000., **location)
        result = monitor.evaluate(hold=True, now_s=99., fallback_now_s=1001., **location)
        self.assertEqual(result["reason"], "hold_time_regressed")
        self.assertTrue(result["recovery_required"])

    def test_missing_budget_or_stale_navigation_escalates(self):
        monitor = HoldBudgetMonitor(None, BOUNDARY)
        self.assertEqual(monitor.evaluate(hold=True, now_s=1.)["reason"], "hold_budget_unconfigured")
        monitor = HoldBudgetMonitor(config(), BOUNDARY)
        self.assertEqual(monitor.evaluate(hold=True, now_s=1., position_xy_m=(0., 0.),
                                          navigation_age_s=.6)["reason"], "hold_navigation_unavailable")
        monitor = HoldBudgetMonitor(config(), BOUNDARY)
        self.assertEqual(monitor.evaluate(hold=True, now_s=1., position_xy_m=(0., 0.),
                                          navigation_age_s=0., navigation_sigma_m=.31,
                                          covariance_age_s=0.)["reason"],
                         "hold_navigation_uncertainty_exceeds_margin")

    def test_opt_in_input_stale_holds_then_recovers_or_expires(self):
        monitor = HoldBudgetMonitor(config(), WIDE_BOUNDARY,
                                    defer_navigation_unavailable=True)
        stale = dict(position_xy_m=(-100., 15.), navigation_age_s=.7,
                     navigation_sigma_m=.2, covariance_age_s=.1)
        result = monitor.evaluate_motion(now_s=1., **stale)
        self.assertEqual(result["state"], "INPUT_STALE_HOLD")
        self.assertFalse(result["recovery_required"])
        good = monitor.evaluate_motion(now_s=2., position_xy_m=(-100., 15.),
                                       navigation_age_s=.1, navigation_sigma_m=.2,
                                       covariance_age_s=.1)
        self.assertEqual(good["state"], "MOTION_BUDGET_OK")
        self.assertFalse(monitor.recovery_required)
        monitor.evaluate_motion(now_s=3., **stale)
        expired = monitor.evaluate_motion(now_s=33., **stale)
        self.assertEqual(expired["reason"], "hold_time_budget_exhausted")
        self.assertTrue(monitor.recovery_required)

    def test_opt_in_input_stale_does_not_defer_geometry_violation(self):
        monitor = HoldBudgetMonitor(config(), WIDE_BOUNDARY,
                                    defer_navigation_unavailable=True)
        result = monitor.evaluate_motion(now_s=1., position_xy_m=(-100., 23.),
                                         navigation_age_s=.1, navigation_sigma_m=.2,
                                         covariance_age_s=.1)
        self.assertEqual(result["reason"], "motion_hold_budget_insufficient")
        self.assertTrue(monitor.recovery_required)

    def test_invalid_configuration_is_rejected(self):
        with self.assertRaises(ValueError):
            HoldBudgetConfig.from_mapping(dict(maximum_hold_s=30.))
        with self.assertRaises(ValueError):
            config(current_bound_mps=float("nan"))

    def test_outside_boundary_has_no_remaining_budget(self):
        monitor = HoldBudgetMonitor(config(), BOUNDARY)
        result = monitor.evaluate(hold=True, now_s=2., position_xy_m=(121., 0.),
                                  navigation_age_s=0., navigation_sigma_m=.1, covariance_age_s=0.)
        self.assertEqual(result["boundary_clearance_m"], 0.)
        self.assertEqual(result["reason"], "hold_boundary_budget_exhausted")

    def test_route_admission_reserves_hold_budget_before_departure(self):
        route = [(-250., -15.), (-80., 15.)]
        old = HoldBudgetMonitor(config(), BOUNDARY).admit_convex_route(
            route, deviation_bound_m=2.)
        self.assertFalse(old["admitted"])
        self.assertEqual(old["reason"], "route_hold_budget_insufficient")
        self.assertAlmostEqual(old["minimum_clearance_m"], 15.)
        self.assertAlmostEqual(old["required_clearance_m"], 19.6)

        wide = HoldBudgetMonitor(config(), WIDE_BOUNDARY).admit_convex_route(
            route, deviation_bound_m=2.)
        self.assertTrue(wide["admitted"])
        self.assertAlmostEqual(wide["minimum_clearance_m"], 25.)

    def test_motion_budget_and_invalid_polygon_fail_closed(self):
        monitor = HoldBudgetMonitor(config(), WIDE_BOUNDARY)
        admitted = monitor.admit_convex_route([(-250., -15.), (-80., 15.)], deviation_bound_m=2.)
        self.assertTrue(admitted["admitted"])
        good = monitor.evaluate_motion(position_xy_m=(-100., 15.), navigation_age_s=.1,
                                       navigation_sigma_m=.2, covariance_age_s=.1)
        self.assertEqual(good["state"], "MOTION_BUDGET_OK")
        bad = monitor.evaluate_motion(position_xy_m=(-100., 23.), navigation_age_s=.1,
                                      navigation_sigma_m=.2, covariance_age_s=.1)
        self.assertEqual(bad["reason"], "motion_hold_budget_insufficient")
        self.assertTrue(monitor.recovery_required)
        polygon = [[0., 0.], [3., 0.], [1., 1.], [3., 3.], [0., 3.]]
        rejected = HoldBudgetMonitor(config(), polygon).admit_convex_route(
            [(1., 0.5), (1., 2.5)], deviation_bound_m=0.)
        self.assertEqual(rejected["reason"], "route_boundary_or_geometry_invalid")


if __name__ == "__main__":
    unittest.main()
