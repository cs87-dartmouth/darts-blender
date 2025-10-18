import numpy as np
import math


class Bezier:
    """Pure numpy implementation of Bézier curves"""

    def __init__(self, control_points, u_start=0.0, u_end=1.0):
        """
        Parameters:
        -----------
        control_points : array_like, shape (n, d) or (n,)
            Control points. Can be 1D for scalar or 2D for vector-valued.
        u_start : float
            Parameter value of source BSpline at first control point
        u_end : float
            Parameter value of source BSpline at last control point
        """
        control_points = np.asarray(control_points, dtype=np.float64)
        if control_points.ndim == 1:
            control_points = control_points[:, np.newaxis]

        self.control_points = control_points

        self.u_start = u_start
        self.u_end = u_end
        self.degree = len(self.control_points) - 1

    @staticmethod
    def create_rational(control_points, weights, u_start=0.0, u_end=1.0):
        """
        Create a rational Bézier curve (NURBS curve).

        Parameters:
        -----------
        control_points : array_like, shape (n, d) or (n,)
            Control points in d-dimensional space
        weights : array_like, shape (n,)
            Weights for each control point
        u_start : float
            Parameter value at first control point
        u_end : float
            Parameter value at last control point

        Returns:
        --------
        Bezier
            Rational Bézier curve in homogeneous coordinates [w*x, w*y, ..., w]
        """
        control_points = np.asarray(control_points, dtype=np.float64)
        weights = np.asarray(weights, dtype=np.float64)

        if control_points.ndim == 1:
            control_points = control_points[:, np.newaxis]

        # Convert to homogeneous coordinates: [w*P, w]
        homogeneous_points = np.column_stack(
            [control_points * weights[:, np.newaxis], weights]
        )

        return Bezier(homogeneous_points, u_start, u_end)

    def to_cartesian(self):
        """
        Convert rational Bézier curve from homogeneous to Cartesian coordinates.

        Returns:
        --------
        points : ndarray
            Control points in Cartesian coordinates
        weights : ndarray
            Weights for each control point
        """
        # Last column is the weight
        weights = self.control_points[:, -1]
        # Other columns are w*P, divide by w to get P
        points = self.control_points[:, :-1] / weights[:, np.newaxis]
        return points, weights

    def bernstein(self, i, n, u):
        """
        Compute Bernstein basis polynomial B_{i,n}(u)

        Parameters:
        -----------
        i : int
            Basis function index (0 <= i <= n)
        n : int
            Degree
        u : float or array
            Parameter value(s) in [0, 1]
        """
        u = np.atleast_1d(u)
        binom_coeff = math.comb(n, i)
        return binom_coeff * (u**i) * ((1 - u) ** (n - i))

    def __call__(self, u):
        """
        Evaluate Bézier curve at parameter value(s) u

        Parameters:
        -----------
        u : float or array
            Parameter value(s) between 0 and 1 (u_start and u_end are only metadata indicating the parameter range of the source B-spline)
        """
        u = np.atleast_1d(u)

        n = self.degree
        result = np.zeros((len(u), self.control_points.shape[1]), dtype=np.float64)

        # Evaluate
        for i in range(n + 1):
            basis = self.bernstein(i, n, u)
            result += self.control_points[i] * basis[:, np.newaxis]

        # Return scalar if single evaluation
        if len(result) == 1:
            return result[0]
        return result


class BSpline:
    """Pure numpy implementation of B-spline curves"""

    def __init__(self, t, c, k):
        """
        Parameters:
        -----------
        t : array_like, shape (n+k+1,)
            Knot vector
        c : array_like, shape (n,) or (n, d)
            Control points (coefficients). Can be 1D for scalar or 2D for vector-valued.
        k : int
            B-spline degree
        """
        self.cyclic = False
        self.clamped = False
        self.bezier = False
        self.t = np.asarray(t, dtype=np.float64)
        self.c = np.asarray(c, dtype=np.float64)
        # Ensure c is at least 2D for consistent handling
        if self.c.ndim == 1:
            self.c = self.c[:, np.newaxis]
        self.k = k

    def basis_function(self, i, p, u):
        """
        Compute B-spline basis function N_{i,p}(u) using Cox-de Boor recursion

        Parameters:
        -----------
        i : int
            Basis function index
        p : int
            Degree
        u : float or array
            Parameter value(s)
        """
        u = np.atleast_1d(u)
        result = np.zeros_like(u, dtype=np.float64)

        # Check bounds for this basis function's support
        if i + p + 1 >= len(self.t):
            return result

        if p == 0:
            # Base case: piecewise constant
            # Check for degenerate interval (repeated knots)
            if abs(self.t[i + 1] - self.t[i]) < 1e-10:
                return result

            # Standard half-open interval [t[i], t[i+1])
            result = np.where((u >= self.t[i]) & (u < self.t[i + 1]), 1.0, 0.0)
        else:
            # Recursive case
            denom1 = self.t[i + p] - self.t[i]
            denom2 = self.t[i + p + 1] - self.t[i + 1]

            left = 0.0
            right = 0.0

            # Left term: avoid division by zero
            if denom1 > 1e-10:
                left = ((u - self.t[i]) / denom1) * self.basis_function(i, p - 1, u)

            # Right term: avoid division by zero
            if denom2 > 1e-10:
                right = ((self.t[i + p + 1] - u) / denom2) * self.basis_function(
                    i + 1, p - 1, u
                )

            result = left + right

        return result

    def __call__(self, u):
        """Evaluate B-spline at parameter value(s) u"""
        u = np.atleast_1d(u)

        # Result shape: (len(u), d) where d is the dimension of coefficients
        result = np.zeros((len(u), self.c.shape[1]), dtype=np.float64)

        # Find valid parameter range
        t_min = self.t[self.k]
        t_max = self.t[len(self.c)]

        # Mask for valid range
        valid = (u >= t_min) & (u <= t_max)
        u_eval = u[valid]

        if len(u_eval) > 0:
            # Evaluate as weighted sum of basis functions
            for i in range(len(self.c)):
                basis = self.basis_function(i, self.k, u_eval)
                # Broadcast basis function values across all dimensions
                result[valid] += self.c[i] * basis[:, np.newaxis]

        # Return scalar if single evaluation, otherwise return array
        if len(result) == 1:
            return result[0]
        return result

    @staticmethod
    def basis_element(knots):
        """
        Create a B-spline basis element from local knot vector

        Parameters:
        -----------
        knots : array_like
            Local knot vector of length k+2 for degree k
        """
        knots = np.asarray(knots, dtype=np.float64)
        k = len(knots) - 2  # degree
        # Single control point with value 1.0
        c = np.array([1.0])
        # Extend knot vector to match requirements
        t = knots
        return BSpline(t, c, k)

    def insert_knot(self, u_bar):
        """
        Insert a knot into the B-spline using Boehm's algorithm

        Parameters:
        -----------
        u_bar : float
            Knot value to insert

        Returns:
        --------
        new_bspline : BSpline
            New B-spline with inserted knot
        """
        k = self.k
        n = len(self.c)
        t = self.t

        # Find the knot span that contains u_bar
        # u_bar should be in [t[k], t[n]]
        knot_span = -1
        for i in range(k, n + 1):
            if t[i] <= u_bar < t[i + 1]:
                knot_span = i
                break
            elif i == n and abs(u_bar - t[i]) < 1e-10:
                knot_span = i - 1
                break

        if knot_span == -1:
            # u_bar is outside the valid range, just return a copy
            return BSpline(self.t.copy(), self.c.copy(), self.k)

        # New knot vector
        new_t = np.insert(t, knot_span + 1, u_bar)

        # Compute new control points using Boehm's algorithm
        # new_c has shape (n+1, d) where d is the dimension
        new_c = np.zeros((n + 1, self.c.shape[1]), dtype=np.float64)

        for i in range(n + 1):
            if i <= knot_span - k:
                new_c[i] = self.c[i]
            elif i >= knot_span + 1:
                new_c[i] = self.c[i - 1]
            else:
                # Blending - be careful with indices
                alpha = 0.0
                if i < len(self.c):  # Make sure we can access self.c[i]
                    denom = t[i + k] - t[i]
                    if denom > 1e-10:
                        alpha = (u_bar - t[i]) / denom
                    new_c[i] = alpha * self.c[i] + (1.0 - alpha) * self.c[i - 1]
                else:
                    # If i >= len(self.c), we only use the previous control point
                    new_c[i] = self.c[i - 1]

        return BSpline(new_t, new_c, k)

    def to_bezier(self):
        """
        Convert B-spline to a B-spline in Bézier form using knot insertion.

        Returns:
        --------
        bezier_bspline : BSpline
            B-spline with Bézier knot vector (all interior knots have multiplicity equal to degree)
        """
        k = self.k
        n = len(self.c)

        t_start = self.t[k]
        t_end = self.t[n]

        # Get unique knots and multiplicities
        unique_knots, multiplicities = np.unique(self.t, return_counts=True)

        new_bspline = self

        # Insert knots at boundaries to full multiplicity (degree + 1)
        for knot_val, current_mult in zip(unique_knots, multiplicities):
            if abs(knot_val - t_start) < 1e-10 or abs(knot_val - t_end) < 1e-10:
                target_mult = k + 1
                knots_to_insert = target_mult - current_mult

                if knots_to_insert > 0:
                    for _ in range(knots_to_insert):
                        new_bspline = new_bspline.insert_knot(knot_val)

        # Insert all interior knots to degree multiplicity
        new_knots = new_bspline.t
        unique_knots, multiplicities = np.unique(new_knots, return_counts=True)

        for knot_val, current_mult in zip(unique_knots, multiplicities):
            if t_start < knot_val < t_end:
                target_mult = k
                knots_to_insert = target_mult - current_mult

                if knots_to_insert > 0:
                    for _ in range(knots_to_insert):
                        new_bspline = new_bspline.insert_knot(knot_val)

        return new_bspline

    @staticmethod
    def create_uniform(
        control_points, degree, cyclic=False, clamped=False, bezier=False
    ):
        """
        Create a B-spline with uniform knot spacing.

        Parameters:
        -----------
        control_points : array_like
            Control points
        degree : int
            Degree of the B-spline
        cyclic : bool
            If True, wrap control points to create a periodic/cyclic curve
        clamped : bool
            If True, use clamped knots (clamp endpoints to [0, 1])
        bezier : bool
            If True, control points are already in Bezier form with appropriate knot multiplicities

        Returns:
        --------
        BSpline
            Configured B-spline curve
        """
        control_points = np.asarray(control_points, dtype=np.float64)
        if control_points.ndim == 1:
            control_points = control_points[:, np.newaxis]

        k = degree
        n_original = len(control_points)

        if bezier:
            # Bezier mode: control points define Bezier curves directly
            # Consecutive Bezier curves always share endpoints (stride = degree)

            if not clamped and not cyclic:
                # Open bezier mode: skip first point, start from p1
                if n_original < 2:
                    # Not enough points
                    control_points = control_points
                    n = len(control_points)
                else:
                    control_points = control_points[1:]
                    n = len(control_points)
            elif cyclic and not clamped:
                # Cyclic bezier mode: start from P1, add P0 and P1 at end
                # Start with P1, P2, ..., P(n-1) (skip P0)
                # Then append P0, P1 to allow last Bezier to loop back to P1
                base_points = control_points[1:]
                control_points = np.vstack([base_points, control_points[:2]])
                n = len(control_points)
            elif cyclic and clamped:
                # Cyclic + clamped: wrap to first point only
                # Curves share endpoints and loop closes at first point
                control_points = np.vstack([control_points, control_points[0:1]])
                n = len(control_points)
            else:
                # Clamped only: curves share endpoints, start from p0
                n = len(control_points)

            # Create Bezier knot vector with appropriate multiplicities
            # Consecutive Bezier curves always share endpoints, so stride = degree
            stride = k  # degree

            # Calculate number of complete Bezier segments
            if n >= k + 1:
                num_segments = max(1, (n - (k + 1)) // stride + 1)
            else:
                num_segments = 0

            # Build knot vector: each segment gets (degree+1) repeated knots at boundaries
            # Total knots = n + k + 1
            knots = []

            # Start with (degree+1) knots at 0
            knots.extend([0.0] * (k + 1))

            # Add interior knots for each segment boundary (except last)
            for i in range(1, num_segments):
                knot_value = i / num_segments
                knots.extend([knot_value] * k)

            # End with (degree+1) knots at 1
            knots.extend([1.0] * (k + 1))

            knots = np.array(knots)

        else:
            # Standard B-spline mode (not Bezier)
            # Handle cyclic wrapping first
            if cyclic and not clamped:
                # Wrap first k control points for periodic curve
                control_points = np.vstack([control_points, control_points[:k]])
            elif cyclic and clamped:
                # Wrap only first control point for closed clamped curve
                control_points = np.vstack([control_points, control_points[0:1]])

            n = len(control_points)
            m = n + k + 1

            # Compute uniform knot vector
            knots = np.array([(i - k) / (n - k) for i in range(m)])

            # If clamped, clamp knot values to [0, 1]
            if clamped:
                knots = np.clip(knots, 0.0, 1.0)

        b = BSpline(knots, control_points, k)
        b.cyclic = cyclic
        b.clamped = clamped
        b.bezier = bezier
        return b

    @staticmethod
    def create_rational(
        control_points, weights, degree, cyclic=False, clamped=False, bezier=False
    ):
        """
        Create a rational B-spline (NURBS) with uniform knot spacing.

        Parameters:
        -----------
        control_points : array_like, shape (n, d)
            Control points in d-dimensional space
        weights : array_like, shape (n,)
            Weights for each control point
        degree : int
            Degree of the B-spline
        cyclic : bool
            If True, wrap control points to create a periodic/cyclic curve
        clamped : bool
            If True, use clamped knots (clamp endpoints to [0, 1])
        bezier : bool
            If True, control points are already in Bezier form with appropriate knot multiplicities

        Returns:
        --------
        BSpline
            Rational B-spline curve in homogeneous coordinates [w*x, w*y, ..., w]
        """
        control_points = np.asarray(control_points, dtype=np.float64)
        weights = np.asarray(weights, dtype=np.float64)

        if control_points.ndim == 1:
            control_points = control_points[:, np.newaxis]

        # Convert to homogeneous coordinates: [w*P, w]
        homogeneous_points = np.column_stack(
            [control_points * weights[:, np.newaxis], weights]
        )

        # Create B-spline with homogeneous coordinates, forwarding all parameters
        return BSpline.create_uniform(
            homogeneous_points, degree, cyclic, clamped, bezier
        )

    def to_cartesian(self):
        """
        Convert rational B-spline from homogeneous to Cartesian coordinates.

        Returns:
        --------
        points : ndarray
            Control points in Cartesian coordinates
        weights : ndarray
            Weights for each control point
        """
        # Last column is the weight
        weights = self.c[:, -1]
        # Other columns are w*P, divide by w to get P
        points = self.c[:, :-1] / weights[:, np.newaxis]
        return points, weights


def create_uniform_bspline_and_beziers(
    control_points, degree, weights=None, cyclic=False, clamped=False, bezier=False
):
    homogeneous_points = np.asarray(control_points, dtype=np.float64)
    if weights is not None:
        weights = np.asarray(weights, dtype=np.float64)

        if homogeneous_points.ndim == 1:
            homogeneous_points = homogeneous_points[:, np.newaxis]

        # Convert to homogeneous coordinates: [w*P, w]
        homogeneous_points = np.column_stack(
            [homogeneous_points * weights[:, np.newaxis], weights]
        )

    b = BSpline.create_uniform(homogeneous_points, degree, cyclic, clamped, bezier)
    b.cyclic = cyclic
    b.clamped = clamped
    b.bezier = bezier

    k = degree

    # Create a list of Bezier curves that represent the same curve
    beziers = []

    if bezier:
        # In Bezier mode, use the processed control points from b
        # (which have been adjusted based on clamped/cyclic flags)
        bezier_knots = b.t
        bezier_controls = b.c
    else:
        # Not in Bezier mode: convert to Bezier form first
        bezier_bspline = b.to_bezier()
        bezier_knots = bezier_bspline.t
        bezier_controls = bezier_bspline.c

        # Skip control points based on mode
        if clamped:
            # Clamped mode (with or without cyclic): don't skip any control points
            pass
        elif cyclic:
            # Cyclic only (not clamped): skip first k and last k control points
            if k > 0 and len(bezier_controls) > 2 * k:
                bezier_knots = bezier_knots[k : len(bezier_controls) + 1]
                bezier_controls = bezier_controls[k:-k]
        else:
            # Uniform only (neither clamped nor cyclic): skip first k and last k control points
            if k > 0 and len(bezier_controls) > 2 * k:
                bezier_knots = bezier_knots[k : len(bezier_controls) + 1]
                bezier_controls = bezier_controls[k:-k]

    # Find segment boundaries (knots with multiplicity >= degree)
    unique_knots, multiplicities = np.unique(bezier_knots, return_counts=True)
    segment_knots = [
        knot for knot, mult in zip(unique_knots, multiplicities) if mult >= k
    ]

    # Extract individual Bezier curves
    num_segments = len(segment_knots) - 1
    for seg_idx in range(num_segments):
        start_idx = seg_idx * k
        end_idx = start_idx + k + 1

        if end_idx <= len(bezier_controls):
            segment_controls = bezier_controls[start_idx:end_idx]

            # Use actual knot values for parameter range
            u_start = segment_knots[seg_idx]
            u_end = segment_knots[seg_idx + 1]

            bezier_curve = Bezier(segment_controls, u_start, u_end)
            beziers.append(bezier_curve)

    return b, beziers


def bspline_to_bezier_matrix(n):
    """
    Generate B-spline to Bezier conversion matrix.

    Based on: Romani and Sabin, "The Conversion Matrix between
    Uniform B-Spline and Bézier Representations."

    Args:
        n: Number of control points (degree = n-1)

    Returns:
        numpy.ndarray: The B-spline to Bezier conversion matrix
    """
    # MATLAB code uses n as degree, creating (n+1) x (n+1) matrix
    # Our n is number of control points, so degree = n - 1
    # We create (n x n) matrix for n control points
    degree = n - 1

    # Initialize matrix and denominator
    matrix = np.zeros((n, n), dtype=int)
    denominator = math.factorial(degree)

    # Initialize identity matrix: S = eye(n + 1) in MATLAB
    np.fill_diagonal(matrix, 1)

    # Main loop: for k = n − 1 : −1 : 1 (MATLAB uses n as degree)
    for k in range(degree - 1, 0, -1):
        # nc = round((n − k)/2) in MATLAB
        # MATLAB's round() rounds 0.5 away from zero (to 1), unlike Python's banker's rounding
        # Use int() with + 0.5 to mimic MATLAB rounding
        nc = int((degree - k) / 2 + 0.5)
        fc = degree + 1 - nc

        # 1. Shift-and-Subtraction
        # for j = fc : n (MATLAB, 1-indexed)
        # for i = k + 1 : n + 1
        for j in range(fc - 1, degree):  # Convert to 0-indexed: fc-1 to degree-1
            for i in range(k, degree + 1):  # Convert to 0-indexed: k to degree
                matrix[i, j] = matrix[i, j] - matrix[i, j + 1]

        # 2. Integration
        # for j = n : −1 : fc
        for j in range(degree - 1, fc - 2, -1):  # Convert to 0-indexed
            # S(k, j) = S(n + 1, j + 1)
            matrix[k - 1, j] = matrix[degree, j + 1]
            # for i = k + 1 : n + 1
            for i in range(k, degree + 1):
                matrix[i, j] = matrix[i - 1, j] + matrix[i, j]

        # if mod(n + 1 − k, 2) == 1
        if (degree + 1 - k) % 2 == 1:
            # S(k : n + 1, n − nc) = S(n + 1 : −1 : k, fc)
            for i in range(k - 1, degree + 1):
                matrix[i, degree - nc - 1] = matrix[degree - (i - (k - 1)), fc - 1]

    # 3. Replication of columns
    # for j = 1 : round(n/2)
    #   S(1 : n + 1, j) = S(n + 1 : −1 : 1, n + 2 − j)
    # MATLAB's round rounds 0.5 up, Python's rounds to even
    for j in range(0, int(degree / 2 + 0.5)):  # Convert to 0-indexed
        for i in range(0, degree + 1):
            matrix[i, j] = matrix[degree - i, degree + 1 - j - 1]

    # The MATLAB code returns the integer matrix directly without division
    # The normalization must be applied when using the matrix
    # For partition of unity (row sums = 1), we need to normalize by the row sum
    # which happens to be n!/2 for n >= 2, and 1 for n = 1
    row_sum = np.sum(matrix[0, :])
    return matrix / row_sum
