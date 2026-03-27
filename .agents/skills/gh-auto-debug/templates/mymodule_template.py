print("Module is imported")

# Set to True when the Agent needs self-check results in last_error.json["validation"].
ENABLE_VALIDATION = True

# The GH entry script can read this field and write it back to last_error.json.
VALIDATION_REPORT = None


class YourCalculator:
    def __init__(self, values, scale=1.0):
        self._values = values
        self._scale = float(scale)

    def compute(self):
        global VALIDATION_REPORT
        VALIDATION_REPORT = None

        normalized_values = self._normalize_values(self._values)
        result_values = [value * self._scale for value in normalized_values]

        if ENABLE_VALIDATION:
            self._run_validation(normalized_values, result_values)

        return result_values

    def _normalize_values(self, values):
        if values is None:
            return []
        if isinstance(values, (list, tuple)):
            return [float(value) for value in values]
        return [float(values)]

    def _run_validation(self, normalized_values, result_values):
        global VALIDATION_REPORT

        checks = []
        passed = True

        same_length = len(result_values) == len(normalized_values)
        checks.append(
            {
                "name": "same_length",
                "passed": same_length,
                "expected": len(normalized_values),
                "actual": len(result_values),
            }
        )
        if not same_length:
            passed = False

        expected_values = [value * self._scale for value in normalized_values]
        max_abs_err = 0.0
        for expected_value, actual_value in zip(expected_values, result_values):
            abs_err = abs(float(actual_value) - float(expected_value))
            if abs_err > max_abs_err:
                max_abs_err = abs_err

        tolerance = 1e-9
        within_tolerance = max_abs_err <= tolerance
        checks.append(
            {
                "name": "reference_compare",
                "passed": within_tolerance,
                "tolerance": tolerance,
                "max_abs_err": max_abs_err,
                "sample_count": len(result_values),
            }
        )
        if not within_tolerance:
            passed = False

        VALIDATION_REPORT = {
            "passed": passed,
            "checks": checks,
            "input_count": len(normalized_values),
            "output_count": len(result_values),
        }

        if not passed:
            raise ValueError("VALIDATION_FAIL: see VALIDATION_REPORT")
