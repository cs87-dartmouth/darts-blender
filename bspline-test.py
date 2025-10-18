import numpy as np
import bspline as bs

try:
    import matplotlib.pyplot as plt

    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False


# ANSI color codes for terminal output
class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def generate_master_control_points(n_points, dimension=2, scale=10.0, rational=True):
    """
    Generate a master set of control points for all tests.

    Control points are laid out uniformly along x, but randomly along y.
    This creates visually interpretable test curves.

    If rational=True, returns homogeneous coordinates with random weights.
    """
    points = np.zeros((n_points, dimension))
    points[:, 0] = np.linspace(0, n_points - 1, n_points)
    if dimension > 1:
        points[:, 1:] = np.random.randn(n_points, dimension - 1) * scale

    if rational:
        # Convert to homogeneous coordinates with random weights
        weights = 0.5 + 3.0 * np.random.rand(n_points)  # Weights between 0.5 and 3.5
        homogeneous = np.zeros((n_points, dimension + 1))
        homogeneous[:, :-1] = points * weights[:, np.newaxis]  # Multiply by weights
        homogeneous[:, -1] = weights  # Last column is the weight
        return homogeneous

    return points


def visualize_comparison(bspline, beziers, control_points, title, filename=None):
    """
    Visualize B-spline and its Bezier curve decomposition.
    """
    if not MATPLOTLIB_AVAILABLE:
        return

    # Determine parameter range
    k = bspline.k
    t_start = bspline.t[k]
    t_end = bspline.t[len(bspline.c)]

    # Check if rational (homogeneous coordinates)
    is_rational = bspline.c.shape[1] > 2

    # Evaluate original B-spline
    t_samples = np.linspace(t_start, t_end - 1e-10, 200)
    bspline_curve = bspline(t_samples)

    # Convert from homogeneous if needed
    if is_rational:
        weights = bspline_curve[:, -1]
        bspline_curve = bspline_curve[:, :-1] / weights[:, np.newaxis]

        # Convert control points
        ctrl_weights = control_points[:, -1]
        control_points_cart = control_points[:, :-1] / ctrl_weights[:, np.newaxis]
    else:
        control_points_cart = control_points

    # Evaluate all Bezier curves
    bezier_curves = []
    for bezier in beziers:
        # Sample in Bezier's own parameter space [0, 1]
        u_bezier = np.linspace(0, 1, 50)
        bezier_vals = bezier(u_bezier)

        # Convert from homogeneous if needed
        if is_rational:
            bez_weights = bezier_vals[:, -1]
            bezier_vals = bezier_vals[:, :-1] / bez_weights[:, np.newaxis]

        bezier_curves.append(bezier_vals)

    # Create figure
    fig, ax = plt.subplots(figsize=(12, 8))

    # Plot original B-spline
    ax.plot(
        bspline_curve[:, 0],
        bspline_curve[:, 1],
        "b-",
        linewidth=3,
        label="B-spline",
        alpha=0.7,
    )

    # Plot individual Bezier curves
    colors = plt.cm.rainbow(np.linspace(0, 1, len(bezier_curves)))
    for i, (bezier_vals, color) in enumerate(zip(bezier_curves, colors)):
        ax.plot(
            bezier_vals[:, 0],
            bezier_vals[:, 1],
            "--",
            color=color,
            linewidth=1.5,
            label=f"Bezier {i+1}",
            alpha=0.8,
        )

        # Add numbered circle at midpoint of each Bezier curve
        mid_idx = len(bezier_vals) // 2
        ax.text(
            bezier_vals[mid_idx, 0],
            bezier_vals[mid_idx, 1],
            f"{i+1}",
            fontsize=10,
            fontweight="bold",
            bbox=dict(
                boxstyle="circle",
                facecolor=color,
                alpha=0.7,
                edgecolor="white",
                linewidth=1,
            ),
            ha="center",
            va="center",
            zorder=6,
            color="white",
        )

        # Plot Bezier control cage
        bezier_ctrl_pts = beziers[i].control_points

        # Convert from homogeneous if needed
        if is_rational:
            bez_ctrl_weights = bezier_ctrl_pts[:, -1]
            bezier_ctrl_pts_cart = (
                bezier_ctrl_pts[:, :-1] / bez_ctrl_weights[:, np.newaxis]
            )
        else:
            bezier_ctrl_pts_cart = bezier_ctrl_pts

        # Plot control polygon with matching color but lighter
        ax.plot(
            bezier_ctrl_pts_cart[:, 0],
            bezier_ctrl_pts_cart[:, 1],
            "o-",
            color=color,
            markersize=3,
            linewidth=0.8,
            alpha=0.3,
            zorder=1,
        )

    # Plot control points
    ax.plot(
        control_points_cart[:, 0],
        control_points_cart[:, 1],
        "ko-",
        markersize=4,
        linewidth=0.5,
        alpha=0.4,
        label="Control points",
    )

    # Highlight start/end
    ax.plot(
        control_points_cart[0, 0],
        control_points_cart[0, 1],
        "go",
        markersize=10,
        label="Start",
        zorder=5,
    )
    ax.plot(
        control_points_cart[-1, 0],
        control_points_cart[-1, 1],
        "ms",
        markersize=10,
        label="End",
        zorder=5,
    )

    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.set_title(title)
    ax.legend(loc="best", ncol=2, fontsize=9)
    ax.grid(True, alpha=0.3)
    # ax.axis("equal")

    if filename:
        plt.savefig(filename, dpi=150, bbox_inches="tight")
        print(f"  Saved: {filename}")
    else:
        plt.tight_layout()
        plt.show()

    plt.close(fig)


def test_configuration(
    master_points, degree, cyclic, clamped, bezier, test_results, visualize=False
):
    """
    Test a specific configuration of B-spline parameters.
    """
    # Create descriptive label
    mode_parts = []
    if cyclic:
        mode_parts.append("Cyclic")
    if clamped:
        mode_parts.append("Clamped")
    if bezier:
        mode_parts.append("Bezier")
    if not mode_parts:
        mode_parts.append("Uniform")
    mode_str = "+".join(mode_parts)

    test_name = f"{mode_str} (deg={degree})"

    print(f"\n{'='*60}")
    print(f"Testing: {test_name}")
    print(f"{'='*60}")

    # Determine how many control points we need
    # For cyclic+bezier mode, we need the right number for a closed sequence
    if cyclic and bezier:
        # For cyclic+bezier: we skip P0, then add P0,P1 at end
        # So with n original points: (n-1) + 2 = n+1 processed points
        # To create m complete Bezier segments (including the closing one):
        # We need: (degree+1) + (m-1)*degree processed points
        # So: n+1 = (degree+1) + (m-1)*degree = degree*m + 1
        # Therefore: n = degree*m
        # Use m=4 segments for testing (to get a closed curve)
        n_segments = 4
        n_points = n_segments * degree
    else:
        # Use more points for higher degrees and certain modes
        n_points = max(degree * 3 + 2, 10)

    control_points = master_points[:n_points].copy()

    print(f"Control points: {n_points}, Degree: {degree}")
    print(f"Flags: cyclic={cyclic}, clamped={clamped}, bezier={bezier}")

    # Create B-spline and Bezier curves
    try:
        bspline, beziers = bs.create_uniform_bspline_and_beziers(
            control_points, degree, cyclic=cyclic, clamped=clamped, bezier=bezier
        )
    except Exception as e:
        print(f"{Colors.RED}✗ Failed to create spline: {e}{Colors.RESET}")
        test_results.append((test_name, False))
        return

    print(f"Number of Bezier curves: {len(beziers)}")

    if len(beziers) == 0:
        print(f"{Colors.RED}✗ No Bezier curves generated{Colors.RESET}")
        test_results.append((test_name, False))
        return

    # Test evaluation: sample each Bezier curve and compare with B-spline
    print("\nEvaluating curves...")
    max_error = 0.0
    total_samples = 0

    for i, bezier in enumerate(beziers):
        # Get the parameter range this Bezier covers in B-spline space
        u_start = bezier.u_start
        u_end = bezier.u_end

        # Sample in B-spline parameter space
        n_samples = 20
        u_bspline = np.linspace(u_start, u_end - 1e-10, n_samples)

        # Evaluate B-spline at these parameters
        bspline_vals = bspline(u_bspline)

        # Sample Bezier in its own [0,1] parameter space
        u_bezier = np.linspace(0, 1 - 1e-10, n_samples)
        bezier_vals = bezier(u_bezier)

        # Compare (both should be in same coordinate system)
        errors = np.abs(bspline_vals - bezier_vals)
        segment_max_error = np.max(errors)
        max_error = max(max_error, segment_max_error)
        total_samples += n_samples

        if i == 0:  # Print detail for first segment
            print(
                f"  Segment 1: u ∈ [{u_start:.3f}, {u_end:.3f}], "
                f"max error = {segment_max_error:.2e}"
            )

    print(f"Total samples evaluated: {total_samples}")
    print(f"Maximum error across all segments: {max_error:.2e}")

    # Check for curve validity
    # Use 1e-7 tolerance to account for floating point precision errors
    # (accumulation of errors can be slightly larger for lower degrees)
    passed = max_error < 1e-6

    if passed:
        print(
            f"{Colors.GREEN}✓ Test passed: Bezier curves match B-spline{Colors.RESET}"
        )
        test_results.append((test_name, True))
    else:
        print(
            f"{Colors.RED}✗ Test failed: Error too large ({max_error:.2e}){Colors.RESET}"
        )
        test_results.append((test_name, False))

    # Visualize if requested
    if visualize and MATPLOTLIB_AVAILABLE:
        filename = f"{mode_str.lower().replace('+', '_')}_deg{degree}.png"
        visualize_comparison(
            bspline,
            beziers,
            control_points,  # Use ORIGINAL control points, not bspline.c
            f"{test_name} - B-spline and Bezier Decomposition",
            filename=filename,
        )


def run_unit_tests():
    """Run focused unit tests matching the C++ test suite."""
    print("\n" + "=" * 60)
    print("=== Starting BSpline Unit Tests ===")
    print("=" * 60)

    test_results = []

    # Test 1: Basic uniform B-spline creation and evaluation
    print("\nTest 1: Basic uniform B-spline creation and evaluation")
    try:
        control_points = np.array([[0.0], [1.0], [2.0], [1.0], [0.0]])
        degree = 3

        bspline = bs.BSpline.create_uniform(
            control_points, degree, cyclic=False, clamped=True, bezier=False
        )

        # Verify knot vector size
        expected_knots = len(bspline.c) + degree + 1
        assert (
            len(bspline.t) == expected_knots
        ), f"Knot vector size mismatch: {len(bspline.t)} vs {expected_knots}"

        # Test evaluation at a few points
        val_start = bspline(0.0)[0]
        val_mid = bspline(0.5)[0]
        val_end = bspline(1.0)[0]

        print(f"  u=0: {val_start:.4f}, u=0.5: {val_mid:.4f}, u=1: {val_end:.4f}")
        print(f"{Colors.GREEN}✓ Test 1 passed{Colors.RESET}")
        test_results.append(("Test 1: Basic B-spline", True))
    except Exception as e:
        print(f"{Colors.RED}✗ Test 1 failed: {e}{Colors.RESET}")
        test_results.append(("Test 1: Basic B-spline", False))

    # Test 2: Knot insertion preserves curve shape
    print("\nTest 2: Knot insertion preserves curve shape")
    try:
        control_points = np.array([[0, 0], [1, 1], [2, 0], [3, 1]])
        degree = 2

        bspline = bs.BSpline.create_uniform(
            control_points, degree, cyclic=False, clamped=True, bezier=False
        )

        print(f"  Initial knot vector: {bspline.t}")

        # Sample original curve
        num_samples = 101
        u_samples = np.linspace(0, 1, num_samples)
        original_samples = bspline(u_samples)

        # Insert a knot in the middle
        bspline.insert_knot(0.25)

        print(f"  After insertion: {bspline.t}")

        # Sample curve after insertion
        new_samples = bspline(u_samples)

        print(f"  Original samples:\n{original_samples}")
        print(f"  New samples:\n{new_samples}")

        # Verify samples are close
        max_diff = np.max(np.abs(original_samples - new_samples))
        assert (
            max_diff < 1e-4
        ), f"Knot insertion changed curve shape: max diff = {max_diff}"

        print(f"  Max difference: {max_diff:.2e}")
        print(f"{Colors.GREEN}✓ Test 2 passed: curve shape preserved{Colors.RESET}")
        test_results.append(("Test 2: Knot insertion", True))
    except Exception as e:
        print(f"{Colors.RED}✗ Test 2 failed: {e}{Colors.RESET}")
        test_results.append(("Test 2: Knot insertion", False))

    # Test 3: Conversion to Bezier form
    print("\nTest 3: Conversion to Bezier form")
    try:
        control_points = np.array([[0.0], [1.0], [2.0], [3.0], [4.0]])
        degree = 3

        bspline = bs.BSpline.create_uniform(
            control_points, degree, cyclic=False, clamped=True, bezier=False
        )
        bezier_bspline = bspline.to_bezier()

        # Sample both curves
        u_samples = np.linspace(0, 1, 21)
        vals_orig = bspline(u_samples)
        vals_bezier = bezier_bspline(u_samples)

        max_diff = np.max(np.abs(vals_orig - vals_bezier))
        assert max_diff < 1e-4, f"Bezier conversion failed: max diff = {max_diff}"

        print(f"  Max difference: {max_diff:.2e}")
        print(
            f"{Colors.GREEN}✓ Test 3 passed: Bezier conversion curves match{Colors.RESET}"
        )
        test_results.append(("Test 3: Bezier conversion", True))
    except Exception as e:
        print(f"{Colors.RED}✗ Test 3 failed: {e}{Colors.RESET}")
        test_results.append(("Test 3: Bezier conversion", False))

    # Test 4: create_uniform_bspline_and_beziers helper
    print("\nTest 4: create_uniform_bspline_and_beziers helper")
    try:
        control_points = np.array([[0, 0], [1, 1], [2, 0], [3, 1], [4, 0]])
        degree = 3

        bspline, beziers = bs.create_uniform_bspline_and_beziers(
            control_points, degree, cyclic=False, clamped=True, bezier=False
        )

        # Print B-spline information
        print("Test 4 - B-spline information:")
        print(f"  Degree: {bspline.k}")
        print(f"  Number of control points: {len(bspline.c)}")
        print(f"  Knot vector size: {len(bspline.t)}")
        print(f"  Knot vector: [{', '.join(f'{k:.6f}' for k in bspline.t)}]")
        print("  Control points:")
        for i, cp in enumerate(bspline.c):
            print(f"    cp[{i}] = {cp}")

        # Print Bezier segments information
        print(f"Test 4 - Generated {len(beziers)} Bezier segments")
        for i, bezier in enumerate(beziers):
            print(
                f"  Segment {i}: u_start={bezier.u_start}, u_end={bezier.u_end}, degree={bezier.degree}"
            )
            print("    Control points:")
            for j, cp in enumerate(bezier.control_points):
                print(f"      cp[{j}] = {cp}")

        print(f"  Generated {len(beziers)} Bezier segments")
        assert len(beziers) > 0, "Should generate at least one Bezier segment"

        # Verify each Bezier segment has correct degree
        for i, bezier in enumerate(beziers):
            assert bezier.degree == degree, f"Bezier segment {i} degree mismatch"

        # Sample and compare with individual segments
        u_samples = np.linspace(0, 1 - 1e-10, 21)
        max_diff = 0.0

        for u in u_samples:
            val_full = bspline(u)

            # Find which Bezier segment contains u
            found = False
            for bezier in beziers:
                if bezier.u_start <= u <= bezier.u_end:
                    # Remap u to [0,1] for this segment
                    t = (
                        (u - bezier.u_start) / (bezier.u_end - bezier.u_start)
                        if bezier.u_end > bezier.u_start
                        else 0
                    )
                    val_segment = bezier(t)
                    diff = np.max(np.abs(val_full - val_segment))
                    max_diff = max(max_diff, diff)
                    # print(
                    #     f"  u={u:.3f}, segment [{bezier.u_start:.3f},{bezier.u_end:.3f}], val_full={val_full.flatten()[0]:.4f}, val_segment={val_segment.flatten()[0]:.4f}, diff={diff:.2e}"
                    # )
                    found = True
                    break

            if not found:
                print(f"  Warning: u={u:.3f} not found in any segment")

        assert (
            max_diff < 1e-3
        ), f"Bezier segments don't match full curve: max diff = {max_diff}"

        print(f"  Max difference: {max_diff:.2e}")
        print(
            f"{Colors.GREEN}✓ Test 4 passed: Bezier segments match full curve{Colors.RESET}"
        )
        test_results.append(("Test 4: Bezier segments", True))
    except Exception as e:
        print(f"{Colors.RED}✗ Test 4 failed: {e}{Colors.RESET}")
        test_results.append(("Test 4: Bezier segments", False))

    # Test 5: Cyclic B-spline
    print("\nTest 5: Cyclic B-spline")
    try:
        control_points = np.array([[1, 0, 0], [0, 1, 0], [-1, 0, 0], [0, -1, 0]])
        degree = 3

        bspline = bs.BSpline.create_uniform(
            control_points, degree, cyclic=True, clamped=False, bezier=False
        )

        # Verify curve evaluation works
        start = bspline(0.0)
        end = bspline(1.0)

        print(f"  Start: {start}, End: {end}")
        print(f"{Colors.GREEN}✓ Test 5 passed: Cyclic B-spline created{Colors.RESET}")
        test_results.append(("Test 5: Cyclic B-spline", True))
    except Exception as e:
        print(f"{Colors.RED}✗ Test 5 failed: {e}{Colors.RESET}")
        test_results.append(("Test 5: Cyclic B-spline", False))

    # Test 6: Bezier mode
    print("\nTest 6: Bezier mode")
    try:
        # 2 cubic Bezier curves: first from indices 0-3, second from 3-6
        control_points = np.array([[0.0], [1.0], [2.0], [3.0], [2.0], [1.0], [0.0]])
        degree = 3

        bspline, beziers = bs.create_uniform_bspline_and_beziers(
            control_points, degree, cyclic=False, clamped=True, bezier=True
        )

        print(f"  Generated {len(beziers)} segments")
        assert (
            len(beziers) == 2
        ), f"Should generate 2 Bezier segments, got {len(beziers)}"

        # Verify continuity at junction (t=0.5)
        val1 = beziers[0](1.0)
        val2 = beziers[1](0.0)
        diff = np.max(np.abs(val1 - val2))
        assert diff < 1e-4, f"Bezier segments not continuous at junction: diff = {diff}"

        print(f"  Junction continuity: {diff:.2e}")
        print(
            f"{Colors.GREEN}✓ Test 6 passed: Bezier segments continuous{Colors.RESET}"
        )
        test_results.append(("Test 6: Bezier mode", True))
    except Exception as e:
        print(f"{Colors.RED}✗ Test 6 failed: {e}{Colors.RESET}")
        test_results.append(("Test 6: Bezier mode", False))

    # Test 7: Multiple knot insertions
    print("\nTest 7: Multiple knot insertions")
    try:
        control_points = np.array([[0.0], [1.0], [2.0], [1.0], [0.0]])
        degree = 3

        bspline = bs.BSpline.create_uniform(
            control_points, degree, cyclic=False, clamped=True, bezier=False
        )

        # Sample original
        u_samples = np.linspace(0, 1, 11)
        original_samples = bspline(u_samples)

        new_bspline = bspline
        # Insert same knot multiple times
        for i in range(2):
            new_bspline = new_bspline.insert_knot(0.5)

        # Sample after insertions
        new_samples = new_bspline(u_samples)

        max_diff = np.max(np.abs(original_samples - new_samples))
        assert (
            max_diff < 1e-4
        ), f"Multiple knot insertions changed curve: max diff = {max_diff}"

        print(f"  Max difference after 2 insertions: {max_diff:.2e}")
        print(f"{Colors.GREEN}✓ Test 7 passed: curve preserved{Colors.RESET}")
        test_results.append(("Test 7: Multiple knot insertions", True))
    except Exception as e:
        print(f"{Colors.RED}✗ Test 7 failed: {e}{Colors.RESET}")
        test_results.append(("Test 7: Multiple knot insertions", False))

    # Print summary
    print("\n" + "=" * 60)
    print(f"{Colors.BOLD}UNIT TEST SUMMARY{Colors.RESET}")
    print("=" * 60)

    passed = sum(1 for _, result in test_results if result)
    total = len(test_results)
    failed = total - passed

    for test_name, result in test_results:
        status = "✓" if result else "✗"
        color = Colors.GREEN if result else Colors.RED
        print(f"{color}{status} {test_name}{Colors.RESET}")

    print("\n" + "-" * 60)
    if failed == 0:
        print(
            f"{Colors.GREEN}{Colors.BOLD}All {passed}/{total} unit tests passed!{Colors.RESET}"
        )
    else:
        print(
            f"{Colors.BOLD}{passed}/{total} passed, {Colors.RED}{failed} failed{Colors.RESET}"
        )
    print("=" * 60)

    return failed == 0


def run_all_tests():
    """Run comprehensive tests for all configurations."""
    # Set random seed for reproducibility
    np.random.seed(42)

    print("B-spline to Bezier Conversion Tests")
    print("=" * 60)

    # Generate master control points (enough for all tests)
    n_master = 50
    master_points = generate_master_control_points(n_master)
    print(f"Generated {n_master} master control points\n")

    # Test parameters
    degrees = [2, 3, 4, 5]
    flag_combinations = [
        (False, False, False),  # Uniform
        (False, True, False),  # Clamped
        (True, False, False),  # Cyclic
        (True, True, False),  # Cyclic+Clamped
        (False, False, True),  # Bezier
        (False, True, True),  # Bezier+Clamped
        (True, False, True),  # Bezier+Cyclic
        (True, True, True),  # Bezier+Cyclic+Clamped
    ]

    test_results = []

    # Run tests for each degree and configuration
    for degree in degrees:
        print(f"\n{'#'*60}")
        print(f"# DEGREE {degree}")
        print(f"{'#'*60}")

        for cyclic, clamped, bezier in flag_combinations:
            # Visualize only degree 3 to avoid too many plots
            visualize = MATPLOTLIB_AVAILABLE

            test_configuration(
                master_points,
                degree,
                cyclic,
                clamped,
                bezier,
                test_results,
                visualize=visualize,
            )

    # Print summary
    print("\n\n" + "=" * 60)
    print(f"{Colors.BOLD}TEST SUMMARY{Colors.RESET}")
    print("=" * 60)

    passed = sum(1 for _, result in test_results if result)
    total = len(test_results)
    failed = total - passed

    for test_name, result in test_results:
        status = "✓" if result else "✗"
        color = Colors.GREEN if result else Colors.RED
        print(f"{color}{status} {test_name}{Colors.RESET}")

    print("\n" + "-" * 60)
    if failed == 0:
        print(
            f"{Colors.GREEN}{Colors.BOLD}All {passed}/{total} tests passed!{Colors.RESET}"
        )
    else:
        print(
            f"{Colors.BOLD}{passed}/{total} passed, {Colors.RED}{failed} failed{Colors.RESET}"
        )
    print("=" * 60)


if __name__ == "__main__":
    # Run unit tests first
    unit_tests_passed = run_unit_tests()

    if not unit_tests_passed:
        print(
            f"\n{Colors.RED}Unit tests failed. Skipping comprehensive tests.{Colors.RESET}"
        )
        exit(1)

    # Run comprehensive configuration tests
    run_all_tests()
