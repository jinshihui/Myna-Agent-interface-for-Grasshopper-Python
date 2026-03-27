# pyright: reportInvalidTypeArguments=false

import Rhino.Geometry as rg
from Grasshopper import DataTree
from Grasshopper.Kernel.Data import GH_Path

print("Module is imported")

# 自检开关：只在本算法脚本内做对照验证（不要在 gh_entry_*.py 里写算法自检/测试）
# 需要自检时改为 True（会打印到 GH 入口脚本捕获的 stdout_tail）
ENABLE_VALIDATION = True

# 入口脚本可读取该字段并写入 last_error.json，用于 Agent 自主回归
VALIDATION_REPORT = None
   
#______________以下为正式代码_________________________


class CurveCauculator:
    def __init__(self, curve_list, t_list):
        self._curve_list = curve_list
        self._t_list = t_list

    def unit_tangent_vectors(self):
        if self._curve_list is None or self._t_list is None:
            return None

        curve_list = self._curve_list
        t_list = self._t_list
        if not isinstance(curve_list, (list, tuple)):
            curve_list = [curve_list]
        if not isinstance(t_list, (list, tuple)):
            t_list = [t_list]

        tangent_tree = DataTree[rg.Vector3d]()
        for curve_index, curve in enumerate(curve_list):
            path = GH_Path(curve_index)
            for t in t_list:
                if curve is None or t is None:
                    tangent_tree.Add(rg.Vector3d.Unset, path)
                    continue
                tangent = curve.TangentAt(float(t))
                tangent.Unitize()
                tangent_tree.Add(tangent, path)
        return tangent_tree

    def curvatures_and_local_bending_energies(self):
        if self._curve_list is None or self._t_list is None:
            return None, None

        global VALIDATION_REPORT
        VALIDATION_REPORT = None

        curve_list = self._curve_list
        t_list = self._t_list
        if not isinstance(curve_list, (list, tuple)):
            curve_list = [curve_list]
        if not isinstance(t_list, (list, tuple)):
            t_list = [t_list]

        curvature_tree = DataTree[object]()
        energy_tree = DataTree[object]()
        for curve_index, curve in enumerate(curve_list):
            path = GH_Path(curve_index)
            if curve is None:
                for _ in t_list:
                    curvature_tree.Add(None, path)
                    energy_tree.Add(None, path)
                continue

            # validation accumulators (per curve)
            k_points_compared = 0
            k_abs_err_sum = 0.0
            k_abs_err_max = 0.0
            energy_sample_checks = []
            printed_derivative_debug = False

            domain = curve.Domain
            total_length = curve.GetLength()
            if len(t_list) > 1:
                # b 的每段改为固定弧长：按采样数量等分总弧长
                segment_length = total_length / float(len(t_list) - 1)
            else:
                segment_length = total_length

            energy_check_indices = set()
            if ENABLE_VALIDATION and len(t_list) > 0:
                energy_check_indices = {0, len(t_list) // 2, len(t_list) - 1}
                validation_samples = []
                validation_energy_rel_err_max = 0.0
                validation_energy_abs_err_max = 0.0

            for t_index, t in enumerate(t_list):
                if t is None:
                    curvature_tree.Add(None, path)
                    energy_tree.Add(None, path)
                    continue
                t = float(t)
                # clamp to domain for RhinoCommon evaluation stability
                t_clamped = min(max(t, domain.T0), domain.T1)
                ders = curve.DerivativeAt(t, 2)
                if isinstance(ders, rg.Vector3d):
                    ders = [ders]
                else:
                    ders = list(ders)
                # RhinoCommon Curve.DerivativeAt(t, 2) 常见返回 [0阶(点坐标), 1阶, 2阶]
                # 曲率公式使用 r'(t), r''(t)
                if len(ders) >= 3:
                    d1 = ders[1]
                    d2 = ders[2]
                else:
                    d1 = ders[0]
                    d2 = ders[1] if len(ders) > 1 else rg.Vector3d(0.0, 0.0, 0.0)
                cross = rg.Vector3d.CrossProduct(d1, d2)
                num = cross.Length
                denom = d1.Length ** 3
                curvature = 0.0 if denom == 0.0 else num / denom
                curvature_tree.Add(curvature, path)

                if ENABLE_VALIDATION:
                    if not printed_derivative_debug and curve_index == 0:
                        k_ref_dbg = curve.CurvatureAt(t_clamped).Length
                        k_01 = None
                        k_12 = None
                        if len(ders) >= 2:
                            d1_01 = ders[0]
                            d2_01 = ders[1]
                            cross_01 = rg.Vector3d.CrossProduct(d1_01, d2_01)
                            denom_01 = d1_01.Length ** 3
                            k_01 = 0.0 if denom_01 == 0.0 else cross_01.Length / denom_01
                        if len(ders) >= 3:
                            d1_12 = ders[1]
                            d2_12 = ders[2]
                            cross_12 = rg.Vector3d.CrossProduct(d1_12, d2_12)
                            denom_12 = d1_12.Length ** 3
                            k_12 = 0.0 if denom_12 == 0.0 else cross_12.Length / denom_12
                        print(
                            "[DEBUG_DERIV] t={0} ders_len={1} k_ref={2:.6g} k_01={3} k_12={4}".format(
                                float(t),
                                int(len(ders)),
                                float(k_ref_dbg),
                                ("{0:.6g}".format(float(k_01)) if k_01 is not None else None),
                                ("{0:.6g}".format(float(k_12)) if k_12 is not None else None),
                            )
                        )
                        printed_derivative_debug = True
                    k_ref = curve.CurvatureAt(t_clamped).Length
                    abs_err = abs(float(curvature) - float(k_ref))
                    k_abs_err_sum += abs_err
                    if abs_err > k_abs_err_max:
                        k_abs_err_max = abs_err
                    k_points_compared += 1

                if segment_length <= 0.0 or total_length <= 0.0:
                    energy_tree.Add(0.0, path)
                    continue

                center_length = curve.GetLength(rg.Interval(domain.T0, t_clamped))
                half_length = segment_length * 0.5
                length0 = max(0.0, center_length - half_length)
                length1 = min(total_length, center_length + half_length)
                has_t0, t0 = curve.LengthParameter(length0)
                has_t1, t1 = curve.LengthParameter(length1)
                if not has_t0:
                    t0 = domain.T0
                if not has_t1:
                    t1 = domain.T1
                if t1 <= t0:
                    energy_tree.Add(0.0, path)
                    continue

                n = 10
                h = (t1 - t0) / n
                total = 0.0
                for i in range(n + 1):
                    ti = t0 + h * i
                    ders_i = curve.DerivativeAt(ti, 2)
                    if isinstance(ders_i, rg.Vector3d):
                        ders_i = [ders_i]
                    else:
                        ders_i = list(ders_i)
                    if len(ders_i) >= 3:
                        d1_i = ders_i[1]
                        d2_i = ders_i[2]
                    else:
                        d1_i = ders_i[0]
                        d2_i = ders_i[1] if len(ders_i) > 1 else rg.Vector3d(0.0, 0.0, 0.0)
                    speed = d1_i.Length
                    if speed == 0.0:
                        f = 0.0
                    else:
                        cross_i = rg.Vector3d.CrossProduct(d1_i, d2_i)
                        num_i = cross_i.Length
                        denom_i = speed ** 3
                        kappa_i = 0.0 if denom_i == 0.0 else num_i / denom_i
                        # Simpson 积分：kappa^2 * |r'(t)|
                        f = kappa_i * kappa_i * speed
                    if i == 0 or i == n:
                        coeff = 1.0
                    elif i % 2 == 1:
                        coeff = 4.0
                    else:
                        coeff = 2.0
                    total += coeff * f
                energy = total * h / 3.0
                energy_tree.Add(energy, path)

                if ENABLE_VALIDATION and t_index in energy_check_indices:
                    # 对照：直接在弧长域积分 ∫kappa(s)^2 ds（用 CurvatureAt + LengthParameter），验证“固定弧长窗口”本身正确
                    length_span = float(length1 - length0)
                    if length_span <= 0.0:
                        energy_ref = 0.0
                    else:
                        n_s = 200  # 必须为偶数
                        ds = length_span / float(n_s)
                        total_s = 0.0
                        for j in range(n_s + 1):
                            sj = float(length0) + ds * j
                            has_tj, tj = curve.LengthParameter(sj)
                            if not has_tj:
                                tj = domain.T0 if j == 0 else domain.T1
                            kappa_ref = curve.CurvatureAt(tj).Length
                            f_ref = float(kappa_ref) * float(kappa_ref)
                            if j == 0 or j == n_s:
                                coeff = 1.0
                            elif j % 2 == 1:
                                coeff = 4.0
                            else:
                                coeff = 2.0
                            total_s += coeff * f_ref
                        energy_ref = total_s * ds / 3.0

                    abs_err = abs(float(energy) - float(energy_ref))
                    rel_err = (abs_err / abs(float(energy_ref))) if float(energy_ref) != 0.0 else (0.0 if abs_err == 0.0 else None)
                    validation_samples.append(
                        {"t": float(t), "energy": float(energy), "energy_ref": float(energy_ref), "abs_err": abs_err, "rel_err": rel_err}
                    )
                    if abs_err > validation_energy_abs_err_max:
                        validation_energy_abs_err_max = abs_err
                    if rel_err is not None and float(rel_err) > validation_energy_rel_err_max:
                        validation_energy_rel_err_max = float(rel_err)

            if ENABLE_VALIDATION:
                mean_abs_err = (k_abs_err_sum / k_points_compared) if k_points_compared else None
                print(
                    "[VALIDATION] curve_index={0} domain=({1:.6g},{2:.6g}) "
                    "k_points={3} k_max_abs_err={4:.3e} k_mean_abs_err={5} "
                    "energy_samples={6}".format(
                        curve_index,
                        float(domain.T0),
                        float(domain.T1),
                        k_points_compared,
                        float(k_abs_err_max),
                        ("{0:.3e}".format(float(mean_abs_err)) if mean_abs_err is not None else None),
                        validation_samples,
                    )
                )
                VALIDATION_REPORT = {
                    "curve_index": int(curve_index),
                    "k_max_abs_err": float(k_abs_err_max),
                    "k_mean_abs_err": float(mean_abs_err) if mean_abs_err is not None else None,
                    "energy_abs_err_max": float(validation_energy_abs_err_max),
                    "energy_rel_err_max": float(validation_energy_rel_err_max),
                    "energy_samples": validation_samples,
                }

                # 让 MCP 回归具备“红灯”语义：超过阈值则抛错，使 last_error.json 的 ok=false
                tol_rel = 1e-2
                tol_abs = 1e-10
                if validation_energy_abs_err_max > tol_abs and validation_energy_rel_err_max > tol_rel:
                    raise ValueError(
                        "BENDING_ENERGY_VALIDATION_FAIL abs_err_max={0:.3e} rel_err_max={1:.3e}".format(
                            float(validation_energy_abs_err_max), float(validation_energy_rel_err_max)
                        )
                    )
        return curvature_tree, energy_tree

"""
class NurbsCurve:
    def __init__(self,points:list[rg.Point3d]):
        self._points = points
        self._Nurbs_curve = None


    def create_bezier_curve(self):
        self._Nurbs_curve = rg.NurbsCurve.CreateInterpolatedCurve(self._points,3) 
        return self._Nurbs_curve
"""


     
  

    

    
    
       

 
    
    

    

    
 
     
 









