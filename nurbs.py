import os
import bpy
import numpy as np
import math
from . import bspline as bs


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

        # Get B-spline parameters
        order_u = patch.order_u
        order_v = patch.order_v
        degree_u = order_u - 1
        degree_v = order_v - 1

        ctx.info(f"Converting NURBS surface to Bezier patches.")

        # Step 1: Process U direction - convert each row (constant V) to Bezier curves
        bezier_u_curves_list = []
        for v in range(num_v):
            # Extract row control points and weights
            row_points = control_grid[v]
            row_weights = weight_grid[v]

            # Use the new helper function to get Bezier curves for this row
            _, bezier_curves = bs.create_uniform_bspline_and_beziers(
                row_points,
                degree_u,
                weights=row_weights,
                cyclic=patch.use_cyclic_u,
                clamped=patch.use_endpoint_u,
                bezier=patch.use_bezier_u,
            )

            bezier_u_curves_list.append(bezier_curves)

        # All rows should produce the same number of U segments
        num_segments_u = len(bezier_u_curves_list[0])
        ctx.info(f"Found {num_segments_u} U segments")

        # Step 2: For each U segment, extract control points and process V direction
        for seg_u in range(num_segments_u):
            # Collect control points from all rows for this U segment
            # Shape will be (num_v, order_u, 3) for points and (num_v, order_u) for weights
            u_segment_points = []
            u_segment_weights = []

            for v in range(num_v):
                bezier_u = bezier_u_curves_list[v][seg_u]

                # Convert from homogeneous to Cartesian
                points_cart, weights_cart = bezier_u.to_cartesian()

                u_segment_points.append(points_cart)
                u_segment_weights.append(weights_cart)

            u_segment_points = np.array(u_segment_points)  # Shape: (num_v, order_u, 3)
            u_segment_weights = np.array(u_segment_weights)  # Shape: (num_v, order_u)

            # Step 3: Process V direction for each column in this U segment
            bezier_v_curves_list = []
            for col_u in range(order_u):
                # Extract column control points and weights
                col_points = u_segment_points[:, col_u, :]  # Shape: (num_v, 3)
                col_weights = u_segment_weights[:, col_u]  # Shape: (num_v,)

                # Use the new helper function to get Bezier curves for this column
                _, bezier_curves = bs.create_uniform_bspline_and_beziers(
                    col_points,
                    degree_v,
                    weights=col_weights,
                    cyclic=patch.use_cyclic_v,
                    clamped=patch.use_endpoint_v,
                    bezier=patch.use_bezier_v,
                )

                bezier_v_curves_list.append(bezier_curves)

            # All columns should produce the same number of V segments
            num_segments_v = len(bezier_v_curves_list[0])
            ctx.info(f"Found {num_segments_v} V segments for U segment {seg_u}")

            # Step 4: Extract final Bezier patches
            for seg_v in range(num_segments_v):
                # Collect control points for this patch
                patch_points = np.zeros((order_v, order_u, 3))
                patch_weights = np.zeros((order_v, order_u))

                for col_u in range(order_u):
                    bezier_v = bezier_v_curves_list[col_u][seg_v]

                    # Convert from homogeneous to Cartesian
                    points_cart, weights_cart = bezier_v.to_cartesian()

                    patch_points[:, col_u, :] = points_cart
                    patch_weights[:, col_u] = weights_cart

                # Calculate UV domain for this patch
                u_min = seg_u / num_segments_u
                u_max = (seg_u + 1) / num_segments_u
                v_min = seg_v / num_segments_v
                v_max = (seg_v + 1) / num_segments_v

                uvs = [[u_min, v_min], [u_max, v_min], [u_min, v_max], [u_max, v_max]]

                # Flatten to lists for JSON
                vertices = patch_points.reshape(-1, 3).tolist()
                weights = patch_weights.flatten().tolist()

                bezier_patches.append(
                    {
                        "type": "bezier patch",
                        "name": f"{nurb.name}_patch_{seg_v}_{seg_u}",
                        "vertices": vertices,
                        "weights": weights,
                        "uvs": uvs,
                        "u degree": degree_u,
                        "v degree": degree_v,
                        "material": material_name,
                        "transform": ctx.transform_matrix(nurb.matrix_world),
                    }
                )

    return bezier_patches


def convert_nurbs_to_native_format(ctx, nurb):
    """
    Export a NURBS surface in native format.

    Args:
        ctx: Export context for logging
        nurb: Blender NURBS surface object

    Returns:
        list: List of dictionaries, each representing a NURBS surface
    """
    nurbs_surfaces = []
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

        # Build control point list (v varies slowest, u varies fastest)
        vertices = []
        weights = []

        for v in range(num_v):
            for u in range(num_u):
                point = patch.points[v * num_u + u]
                vertices.append(list(point.co[:3]))
                weights.append(point.weight)

        # Get B-spline parameters
        degree_u = patch.order_u - 1
        degree_v = patch.order_v - 1

        ctx.info(f"Exporting NURBS surface '{nurb.name}' in native format.")
        ctx.info(
            f"  num_u={num_u}, num_v={num_v}, degree_u={degree_u}, degree_v={degree_v}"
        )
        ctx.info(
            f"  clamped_u={patch.use_endpoint_u}, clamped_v={patch.use_endpoint_v}"
        )

        nurbs_surface = {
            "type": "nurbs surface",
            "name": nurb.name,
            "num u": num_u,
            "num v": num_v,
            "u degree": degree_u,
            "v degree": degree_v,
            "clamped u": patch.use_endpoint_u,
            "clamped v": patch.use_endpoint_v,
            "bezier u": patch.use_bezier_u,
            "bezier v": patch.use_bezier_v,
            "cyclic u": patch.use_cyclic_u,
            "cyclic v": patch.use_cyclic_v,
            "vertices": vertices,
            "material": material_name,
            "transform": ctx.transform_matrix(nurb.matrix_world),
        }

        # Only include weights if they're not all 1.0
        if not all(abs(w - 1.0) < 1e-6 for w in weights):
            nurbs_surface["weights"] = weights

        nurbs_surfaces.append(nurbs_surface)

    return nurbs_surfaces


def export(ctx, nurbs):
    if not os.path.exists(ctx.directory + "/meshes"):
        os.makedirs(ctx.directory + "/meshes")

    surfaces_json = []

    for nurb in nurbs:
        if ctx.nurbs_mode == "PATCHES":
            ctx.info(f"Converting NURBS surface '{nurb.name}' to Bezier patches.")
            bezier_patches = convert_nurbs_to_bezier_patches(ctx, nurb)
            surfaces_json.extend(bezier_patches)
        elif ctx.nurbs_mode == "NURBS":
            ctx.info(f"Exporting NURBS surface '{nurb.name}' in native format.")
            nurbs_surfaces = convert_nurbs_to_native_format(ctx, nurb)
            surfaces_json.extend(nurbs_surfaces)

    return surfaces_json
