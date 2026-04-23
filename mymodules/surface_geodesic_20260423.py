import math

import Rhino.Geometry as rg

try:
    import numpy as np
    from scipy.optimize import minimize
except ImportError as exc:
    raise ImportError("scipy and numpy are required in the project .venv") from exc


ENABLE_VALIDATION = True
VALIDATION_REPORT = None
DEBUG_PAYLOAD = None


class SurfaceGeodesicCalculator:
    def __init__(self, surface_input, endpoint_input, tolerance=1e-5, sample_count=31, max_iterations=300):
        self._surface = self._coerce_surface(surface_input)
        self._endpoints = self._coerce_endpoints(endpoint_input)
        self._tolerance = float(tolerance)
        self._sample_count = max(int(sample_count), 5)
        self._max_iterations = max(int(max_iterations), 1)

    def compute(self):
        global VALIDATION_REPORT
        global DEBUG_PAYLOAD

        VALIDATION_REPORT = None
        DEBUG_PAYLOAD = None

        start_point, end_point = self._endpoints
        start_uv = self._closest_uv(start_point, "POINT_INPUT_START_NOT_ON_SURFACE")
        end_uv = self._closest_uv(end_point, "POINT_INPUT_END_NOT_ON_SURFACE")
        initial_uv_points = self._linear_uv_points(start_uv, end_uv)
        initial_length = self._length_from_uv_points(initial_uv_points)
        optimized_uv_points, optimizer_result = self._optimize_uv_points(initial_uv_points)

        uv_curve = rg.PolylineCurve([rg.Point3d(u, v, 0.0) for u, v in optimized_uv_points])
        geodesic_curve = self._surface.Pushup(uv_curve, self._tolerance)
        if geodesic_curve is None or not geodesic_curve.IsValid:
            geodesic_curve = rg.PolylineCurve([self._surface.PointAt(u, v) for u, v in optimized_uv_points])
        if geodesic_curve is None or not geodesic_curve.IsValid:
            raise ValueError("GEODESIC_CURVE_BUILD_FAILED")

        if geodesic_curve.PointAtStart.DistanceTo(start_point) > geodesic_curve.PointAtEnd.DistanceTo(start_point):
            geodesic_curve.Reverse()

        if ENABLE_VALIDATION:
            self._run_validation(
                geodesic_curve,
                start_point,
                end_point,
                initial_length,
                optimized_uv_points,
                optimizer_result,
            )

        return geodesic_curve

    def _coerce_surface(self, surface_input):
        if surface_input is None:
            raise ValueError("SURFACE_INPUT_IS_NONE")
        if hasattr(surface_input, "Branches"):
            items = []
            for branch in list(surface_input.Branches):
                items.extend(item for item in list(branch) if item is not None)
            if len(items) == 1:
                surface_input = items[0]
        elif isinstance(surface_input, (list, tuple)):
            items = [item for item in surface_input if item is not None]
            if len(items) == 1:
                surface_input = items[0]
        surface_input = getattr(surface_input, "Value", surface_input)

        if hasattr(surface_input, "ClosestPoint") and hasattr(surface_input, "PointAt") and hasattr(surface_input, "Pushup"):
            return surface_input
        if hasattr(surface_input, "Faces") and getattr(surface_input.Faces, "Count", 0) == 1:
            face = surface_input.Faces[0]
            if hasattr(face, "ClosestPoint") and hasattr(face, "PointAt") and hasattr(face, "Pushup"):
                return face
        raise TypeError("SURFACE_INPUT_MUST_BE_SURFACE_OR_SINGLE_FACE_BREP")

    def _coerce_endpoints(self, endpoint_input):
        if endpoint_input is None:
            raise ValueError("POINT_INPUT_IS_NONE")
        if hasattr(endpoint_input, "X") and hasattr(endpoint_input, "Y") and hasattr(endpoint_input, "Z"):
            raise ValueError("POINT_INPUT_MUST_CONTAIN_TWO_POINTS")

        raw_points = []
        if hasattr(endpoint_input, "Branches"):
            for branch in list(endpoint_input.Branches):
                raw_points.extend(list(branch))
        else:
            raw_points = list(endpoint_input)

        endpoints = [point for point in raw_points if point is not None]
        if len(endpoints) != 2:
            raise ValueError("POINT_INPUT_MUST_CONTAIN_TWO_POINTS")
        endpoints = [getattr(point, "Value", point) for point in endpoints]
        for point in endpoints:
            if not all(hasattr(point, attr_name) for attr_name in ("X", "Y", "Z")):
                raise TypeError("POINT_INPUT_ITEMS_MUST_BE_POINT3D")
        return endpoints

    def _closest_uv(self, point, error_code):
        ok, u, v = self._surface.ClosestPoint(point)
        if not ok:
            raise ValueError(error_code)
        surface_point = self._surface.PointAt(u, v)
        if surface_point.DistanceTo(point) > max(self._tolerance * 100.0, 1e-4):
            raise ValueError(error_code)
        return (float(u), float(v))

    def _linear_uv_points(self, start_uv, end_uv):
        uv_points = []
        for index in range(self._sample_count):
            ratio = float(index) / float(self._sample_count - 1)
            uv_points.append(
                (
                    (1.0 - ratio) * start_uv[0] + ratio * end_uv[0],
                    (1.0 - ratio) * start_uv[1] + ratio * end_uv[1],
                )
            )
        return uv_points

    def _optimize_uv_points(self, initial_uv_points):
        u_domain = self._surface.Domain(0)
        v_domain = self._surface.Domain(1)
        start_uv = initial_uv_points[0]
        end_uv = initial_uv_points[-1]
        initial_variables = np.array(initial_uv_points[1:-1], dtype=float).reshape(-1)
        bounds = [(u_domain.Min, u_domain.Max), (v_domain.Min, v_domain.Max)] * (self._sample_count - 2)

        def objective(variable_values):
            internal = np.asarray(variable_values, dtype=float).reshape((-1, 2))
            uv_points = [start_uv]
            uv_points.extend((float(u), float(v)) for u, v in internal)
            uv_points.append(end_uv)
            return self._length_from_uv_points(uv_points)

        result = minimize(
            objective,
            initial_variables,
            method="L-BFGS-B",
            bounds=bounds,
            options={"maxiter": self._max_iterations, "ftol": self._tolerance * 0.01},
        )
        optimized_internal = np.asarray(result.x, dtype=float).reshape((-1, 2))
        optimized_uv_points = [start_uv]
        optimized_uv_points.extend((float(u), float(v)) for u, v in optimized_internal)
        optimized_uv_points.append(end_uv)
        return optimized_uv_points, result

    def _length_from_uv_points(self, uv_points):
        total_length = 0.0
        last_point = None
        for u, v in uv_points:
            point = self._surface.PointAt(float(u), float(v))
            if last_point is not None:
                total_length += last_point.DistanceTo(point)
            last_point = point
        return float(total_length)

    def _run_validation(self, geodesic_curve, start_point, end_point, initial_length, optimized_uv_points, optimizer_result):
        global VALIDATION_REPORT
        global DEBUG_PAYLOAD

        tolerance = max(self._tolerance * 50.0, 1e-4)
        endpoint_error_start = geodesic_curve.PointAtStart.DistanceTo(start_point)
        endpoint_error_end = geodesic_curve.PointAtEnd.DistanceTo(end_point)
        optimized_length = geodesic_curve.GetLength()
        discrete_length = self._length_from_uv_points(optimized_uv_points)
        max_surface_error = self._max_curve_surface_error(geodesic_curve)
        optimizer_message = str(getattr(optimizer_result, "message", ""))
        optimizer_success = bool(getattr(optimizer_result, "success", False)) or "REL_REDUCTION_OF_F" in optimizer_message
        residual = float(np.linalg.norm(getattr(optimizer_result, "jac", np.array([0.0])), ord=np.inf))
        residual_ok = math.isfinite(residual) and residual <= 1e-2

        checks = [
            {"name": "curve_is_valid", "passed": bool(geodesic_curve.IsValid)},
            {"name": "start_matches_input", "passed": endpoint_error_start <= tolerance, "distance": endpoint_error_start},
            {"name": "end_matches_input", "passed": endpoint_error_end <= tolerance, "distance": endpoint_error_end},
            {"name": "samples_on_surface", "passed": max_surface_error <= tolerance, "max_distance": max_surface_error},
            {
                "name": "optimized_not_longer_than_initial",
                "passed": optimized_length <= initial_length + tolerance,
                "initial_length": initial_length,
                "optimized_length": optimized_length,
            },
            {"name": "optimizer_converged", "passed": optimizer_success, "message": optimizer_message},
            {"name": "optimizer_residual_small", "passed": residual_ok, "residual_inf_norm": residual},
        ]
        passed = all(check["passed"] for check in checks)

        VALIDATION_REPORT = {
            "passed": passed,
            "checks": checks,
            "tolerance": tolerance,
            "max_error": max(endpoint_error_start, endpoint_error_end, max_surface_error),
            "method_summary": "L-BFGS-B minimizes a fixed-endpoint UV polyline length, then pushes the UV path onto the surface.",
        }
        DEBUG_PAYLOAD = {
            "initial_length": initial_length,
            "optimized_length": optimized_length,
            "discrete_length": discrete_length,
            "optimizer_iterations": int(getattr(optimizer_result, "nit", -1)),
            "optimizer_function_calls": int(getattr(optimizer_result, "nfev", -1)),
            "optimizer_message": optimizer_message,
            "optimizer_residual_inf_norm": residual,
            "uv_sample_count": len(optimized_uv_points),
            "max_surface_error": max_surface_error,
        }

        if not passed:
            raise ValueError("VALIDATION_FAIL: see VALIDATION_REPORT")

    def _max_curve_surface_error(self, curve):
        curve_domain = curve.Domain
        max_error = 0.0
        for sample_index in range(11):
            ratio = float(sample_index) / 10.0
            curve_parameter = curve_domain.ParameterAt(ratio)
            curve_point = curve.PointAt(curve_parameter)
            ok, u, v = self._surface.ClosestPoint(curve_point)
            if not ok:
                return float("inf")
            surface_point = self._surface.PointAt(u, v)
            max_error = max(max_error, curve_point.DistanceTo(surface_point))
        return max_error
