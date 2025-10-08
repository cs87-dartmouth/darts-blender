import os
import bpy
import numpy as np
import math

def bspline_to_bezier_matrix(n):
    """
    Generate B-spline to Bezier conversion matrix.
    
    Args:
        n: Number of control points (degree = n-1)
        
    Returns:
        numpy.ndarray: The B-spline to Bezier conversion matrix
    """
    # Initialize matrix and denominator
    matrix = np.zeros((n, n), dtype=int)
    denominator = math.factorial(n - 1)
    
    # Initialize identity matrix
    np.fill_diagonal(matrix, 1)
    
    degree = n - 1
    
    for k in range(degree - 1, 0, -1):
        nc = (degree - k + 1) // 2  # Integer division with rounding to nearest
        fc = degree + 1 - nc
        
        # 1. Shift-and-Subtraction
        for j in range(fc, degree + 1):
            for i in range(k + 1, degree + 2):
                matrix[i - 1, j - 1] = matrix[i - 1, j - 1] - matrix[i - 1, j]
        
        # 2. Integration
        for j in range(degree, fc - 1, -1):
            matrix[k - 1, j - 1] = matrix[degree, j]
            for i in range(k + 1, degree + 2):
                matrix[i - 1, j - 1] = matrix[i - 2, j - 1] + matrix[i - 1, j - 1]
        
        if (degree + 1 - k) % 2 == 1:
            for i in range(k, degree + 2):
                matrix[i - 1, degree - nc - 1] = matrix[degree + 1 - i, fc - 1]
    
    # 3. Replication of columns
    for j in range(1, (degree + 1) // 2 + 1):
        for i in range(1, degree + 2):
            matrix[i - 1, j - 1] = matrix[degree + 1 - i, degree + 2 - j - 1]
    
    return matrix / denominator

def prepare_bspline_for_conversion(control_points, weights, order, use_endpoint, use_cyclic, use_bezier):
    """
    Prepare B-spline control points for conversion to Bezier by handling endpoint/cyclic/bezier cases.
    
    Args:
        control_points: Array of control points along one dimension
        weights: Array of weights corresponding to control points
        order: Order (degree + 1) of the B-spline
        use_endpoint: Whether the spline interpolates endpoints
        use_cyclic: Whether the spline is cyclic
        use_bezier: Whether the spline is already in Bezier mode
        
    Returns:
        tuple: (prepared_points, prepared_weights, num_segments, offset, needs_conversion, bezier_stride, parametric_spans)
    """
    degree = order - 1
    n = len(control_points)
    
    if use_bezier:
        # Bezier mode: control points are already Bezier control points
        # Each complete set of 'order' consecutive points forms a Bezier curve
        
        if use_cyclic:
            if use_endpoint:
                prepared_points = np.concatenate([control_points, control_points[:order-1]])
                prepared_weights = np.concatenate([weights, weights[:order-1]])
                num_segments = n
                offset = 0
                bezier_stride = degree
                # Parametric domain completes after n/stride spans
                parametric_spans = n // degree
            else:
                # Independent bezier curves with wraparound
                prepared_points = np.concatenate([control_points, control_points[:order-1]])
                prepared_weights = np.concatenate([weights, weights[:order-1]])
                num_segments = n // order  # Complete non-overlapping curves only
                offset = 0
                bezier_stride = order  # Skip by order between curves
                parametric_spans = num_segments
            needs_conversion = False
        elif use_endpoint:
            # Endpoint bezier mode: p0-p3, p3-p6, p6-p9, etc.
            # Bezier curves share endpoint with next curve's start point
            # Number of segments = (n - 1) // degree
            num_segments = (n - 1) // degree
            prepared_points = control_points
            prepared_weights = weights
            offset = 0
            bezier_stride = degree
            parametric_spans = num_segments
            needs_conversion = False
        else:
            # Open bezier mode (no endpoint): skip first point
            # Start from index 1: p1-p4, p4-p7, etc.
            if n > 1:
                prepared_points = control_points[1:]
                prepared_weights = weights[1:]
                num_segments = (n - 1 - 1) // degree if n > 1 else 0
                offset = 0
            else:
                prepared_points = control_points
                prepared_weights = weights
                num_segments = 0
                offset = 0
            bezier_stride = degree
            parametric_spans = num_segments
            needs_conversion = False
    elif use_cyclic:
        # For cyclic splines, wrap the control points
        prepared_points = np.concatenate([control_points, control_points[:degree]])
        prepared_weights = np.concatenate([weights, weights[:degree]])
        num_segments = n
        offset = 0
        bezier_stride = 1
        parametric_spans = n
        needs_conversion = True
    elif use_endpoint:
        # For clamped/endpoint B-splines:
        prepared_points = control_points
        prepared_weights = weights
        num_segments = max(1, n - degree)
        offset = 0
        bezier_stride = 1
        parametric_spans = num_segments
        needs_conversion = False
    else:
        # Uniform open B-spline - needs conversion
        prepared_points = control_points
        prepared_weights = weights
        num_segments = n - degree
        offset = 0
        bezier_stride = 1
        parametric_spans = num_segments
        needs_conversion = True
    
    return prepared_points, prepared_weights, num_segments, offset, needs_conversion, bezier_stride, parametric_spans


def convert_nurbs_to_bezier_patches(ctx, nurb):
    """
    Convert a NURBS surface to a collection of Bezier patches.
    
    Args:
        ctx: Export context for logging
        nurb: Blender NURBS surface object
        
    Returns:
        list: List of dictionaries, each representing a Bezier patch
    """
    bezier_patches = []
    for patch in nurb.data.splines:
    
        # Extract material name
        material_name = "default"
        if nurb.data.materials and len(nurb.data.materials) > 0:
            mat = nurb.data.materials[0]
            if mat:
                material_name = mat.name
        
        # Extract control points and weights
        num_u = patch.point_count_u
        num_v = patch.point_count_v
        
        # Build control point grid (u varies fastest in Blender's storage)
        control_grid = np.zeros((num_v, num_u, 3))
        weight_grid = np.zeros((num_v, num_u))
        
        for v in range(num_v):
            for u in range(num_u):
                point = patch.points[v * num_u + u]
                control_grid[v, u] = point.co[:3]
                weight_grid[v, u] = point.weight
        
        # Get conversion matrices
        order_u = patch.order_u
        order_v = patch.order_v
        M_u = bspline_to_bezier_matrix(order_u)
        M_v = bspline_to_bezier_matrix(order_v)
        
        # Prepare control points for u direction
        prepared_u_grids = []
        prepared_u_weights = []
        offset_u = 0
        needs_conversion_u = True
        bezier_stride_u = 1
        parametric_spans_u = 0
        for v in range(num_v):
            prep_pts, prep_wts, num_seg_u, off_u, needs_conv_u, bez_stride_u, param_spans_u = prepare_bspline_for_conversion(
                control_grid[v], weight_grid[v], order_u,
                patch.use_endpoint_u, patch.use_cyclic_u, patch.use_bezier_u
            )
            prepared_u_grids.append(prep_pts)
            prepared_u_weights.append(prep_wts)
            offset_u = off_u
            needs_conversion_u = needs_conv_u
            bezier_stride_u = bez_stride_u
            parametric_spans_u = param_spans_u
        
        # Convert along u direction first
        num_segments_u = num_seg_u
        intermediate_grids = []
        intermediate_weights = []
        
        for v in range(num_v):
            u_segments = []
            u_weights = []
            for seg in range(num_segments_u):
                # Extract order_u control points for this segment
                start_idx = offset_u + seg * bezier_stride_u
                
                segment_points = prepared_u_grids[v][start_idx:start_idx + order_u]
                segment_weights = prepared_u_weights[v][start_idx:start_idx + order_u]
                
                # Convert to Bezier only if needed
                if needs_conversion_u:
                    # For rational B-splines, work in homogeneous 4D coordinates
                    # Construct [w*x, w*y, w*z, w] for each control point
                    homogeneous = np.column_stack([
                        segment_points * segment_weights[:, np.newaxis],
                        segment_weights
                    ])  # Shape: (order_u, 4)
                    
                    # Apply conversion matrix to homogeneous coordinates
                    bezier_homogeneous = M_u @ homogeneous  # Shape: (order_u, 4)
                    
                    # Extract weights (4th component) and convert back to Cartesian
                    bezier_weights = bezier_homogeneous[:, 3]
                    bezier_points = bezier_homogeneous[:, :3] / bezier_weights[:, np.newaxis]
                else:
                    bezier_points = segment_points
                    bezier_weights = segment_weights
                
                u_segments.append(bezier_points)
                u_weights.append(bezier_weights)
            
            intermediate_grids.append(u_segments)
            intermediate_weights.append(u_weights)
        
        # Now prepare and convert along v direction
        prepared_v_data = []
        for seg_u in range(num_segments_u):
            v_control = np.array([intermediate_grids[v][seg_u] for v in range(num_v)])
            v_weights = np.array([intermediate_weights[v][seg_u] for v in range(num_v)])
            
            prep_pts, prep_wts, num_seg_v, off_v, needs_conv_v, bez_stride_v, param_spans_v = prepare_bspline_for_conversion(
                v_control, v_weights, order_v,
                patch.use_endpoint_v, patch.use_cyclic_v, patch.use_bezier_v
            )
            prepared_v_data.append((prep_pts, prep_wts, num_seg_v, off_v, needs_conv_v, bez_stride_v, param_spans_v))
        
        # Convert along v direction
        for seg_u in range(num_segments_u):
            prep_pts, prep_wts, num_segments_v, offset_v, needs_conversion_v, bezier_stride_v, parametric_spans_v = prepared_v_data[seg_u]
            
            for seg_v in range(num_segments_v):
                # Extract order_v x order_u control points for this patch
                start_idx_v = offset_v + seg_v * bezier_stride_v
                
                patch_points = prep_pts[start_idx_v:start_idx_v + order_v]  # (order_v, order_u, 3)
                patch_weights = prep_wts[start_idx_v:start_idx_v + order_v]  # (order_v, order_u)
                
                # Validate we extracted the right number of points
                if patch_points.shape[0] != order_v or patch_points.shape[1] != order_u:
                    ctx.info(f"Warning: patch {seg_v}_{seg_u} has incorrect shape: {patch_points.shape}, expected ({order_v}, {order_u}). Prepared array has {len(prep_pts)} points, extracting from index {start_idx_v}")
                    continue  # Skip this malformed patch
                
                # Apply conversion in v direction only if needed
                if needs_conversion_v:
                    # For rational B-splines, work in homogeneous 4D coordinates
                    # Construct [w*x, w*y, w*z, w] for each control point
                    homogeneous = np.concatenate([
                        patch_points * patch_weights[:, :, np.newaxis],
                        patch_weights[:, :, np.newaxis]
                    ], axis=2)  # Shape: (order_v, order_u, 4)
                    
                    # Apply conversion matrix to homogeneous coordinates
                    bezier_homogeneous = np.einsum('ij,jkl->ikl', M_v, homogeneous)  # Shape: (order_v, order_u, 4)
                    
                    # Extract weights (4th component) and convert back to Cartesian
                    bezier_patch_weights = bezier_homogeneous[:, :, 3]
                    bezier_patch_points = bezier_homogeneous[:, :, :3] / bezier_patch_weights[:, :, np.newaxis]
                else:
                    bezier_patch_points = patch_points
                    bezier_patch_weights = patch_weights
                
                # Calculate UV domain for this patch
                # UV space is [0,1] x [0,1] for the entire NURBS surface
                # Use parametric_spans (actual domain divisions) not num_segments (created patches)
                u_min = seg_u / parametric_spans_u
                u_max = (seg_u + 1) / parametric_spans_u
                v_min = seg_v / parametric_spans_v
                v_max = (seg_v + 1) / parametric_spans_v
                
                # UV corners: [[u0,v0], [u1,v0], [u0,v1], [u1,v1]]
                uvs = [
                    [u_min, v_min],
                    [u_max, v_min],
                    [u_min, v_max],
                    [u_max, v_max]
                ]
                
                # Flatten to lists for JSON
                vertices = bezier_patch_points.reshape(-1, 3).tolist()
                weights = bezier_patch_weights.flatten().tolist()
                
                bezier_patches.append({
                    "type": "bezier patch",
                    "name": f"{nurb.name}_patch_{seg_v}_{seg_u}",
                    "vertices": vertices,
                    "weights": weights,
                    "uvs": uvs,
                    "u degree": order_u - 1,
                    "v degree": order_v - 1,
                    "material": material_name,
                    "transform": ctx.transform_matrix(nurb.matrix_world)
                })
    
    return bezier_patches


def export(ctx, nurbs):
    if not os.path.exists(ctx.directory + "/meshes"):
        os.makedirs(ctx.directory + "/meshes")
    
    surfaces_json = []
    
    for nurb in nurbs:
        ctx.info(f"Converting NURBS surface '{nurb.name}' to Bezier patches.")
        bezier_patches = convert_nurbs_to_bezier_patches(ctx, nurb)
        surfaces_json.extend(bezier_patches)

    return surfaces_json
