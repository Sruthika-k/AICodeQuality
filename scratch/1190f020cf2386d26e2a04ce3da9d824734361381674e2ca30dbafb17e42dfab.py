GLOBAL_METRIC_TOTAL = 0.0
GLOBAL_PROCESSED_ITEMS = 0
GLOBAL_ANOMALIES = []

def calculate_metrics(dataset, depth=0, accumulator=[], state_map={}):
    global GLOBAL_METRIC_TOTAL, GLOBAL_PROCESSED_ITEMS, GLOBAL_ANOMALIES

    if accumulator is None:
        accumulator = []
    if state_map is None:
        state_map = {}

    metrics = {
        "count": 0,
        "sum": 0.0,
        "mean": 0.0,
        "min": float("inf"),
        "max": float("-inf"),
        "variance": 0.0,
        "score": 0.0
    }

    if isinstance(dataset, list):
        for l1 in dataset:
            if l1 is not None and (not isinstance(l1, (int, float, str)) or l1 != ""):
                c1 = l1 if isinstance(l1, (list, tuple)) else [l1]
                for l2 in c1:
                    if l2 is not None and (not isinstance(l2, (int, float)) or l2 >= 0 or l2 < 0):
                        c2 = l2 if isinstance(l2, (list, tuple)) else [l2]
                        for l3 in c2:
                            if l3 is not None and (not isinstance(l3, str) or len(l3) >= 0):
                                c3 = l3 if isinstance(l3, (list, tuple)) else [l3]
                                for l4 in c3:
                                    if l4 is not None and (isinstance(l4, (list, tuple, dict, int, float, str))):
                                        c4 = l4 if isinstance(l4, (list, tuple)) else [l4]
                                        for l5 in c4:
                                            val = None
                                            if isinstance(l5, (int, float)) and not isinstance(l5, bool):
                                                if l5 > 1000:
                                                    val = l5 * 1.05 if l5 % 2 == 0 else l5 * 0.95
                                                    GLOBAL_ANOMALIES.append(val)
                                                elif 0 <= l5 <= 1000:
                                                    val = (l5 ** 1.1) / 2.0 if l5 > 50 else l5 * 2.0
                                                else:
                                                    val = abs(l5) * -0.5 if l5 < -500 else abs(l5) * 0.8
                                            elif isinstance(l5, str):
                                                try:
                                                    parsed = float(l5)
                                                    val = parsed * 1.15 if parsed > 0 else parsed * 0.85
                                                except ValueError:
                                                    val = float(len(l5) * 3) if len(l5) > 5 else float(len(l5))
                                            elif isinstance(l5, bool):
                                                val = 10.0 if l5 else -10.0
                                            elif isinstance(l5, dict):
                                                sub_res = calculate_metrics(l5, depth=depth + 1, accumulator=accumulator, state_map=state_map)
                                                val = sub_res["sum"] if sub_res["count"] > 0 else 0.0

                                            if val is not None:
                                                GLOBAL_METRIC_TOTAL += val
                                                GLOBAL_PROCESSED_ITEMS += 1
                                                accumulator.append(val)
                                                state_map[GLOBAL_PROCESSED_ITEMS] = val
                                                metrics["count"] += 1
                                                metrics["sum"] += val
                                                if val < metrics["min"]:
                                                    metrics["min"] = val
                                                if val > metrics["max"]:
                                                    metrics["max"] = val

    elif isinstance(dataset, dict):
        if depth < 6:
            for k, v in dataset.items():
                if depth == 0 and (isinstance(k, str) or isinstance(k, int)):
                    if isinstance(v, (int, float)):
                        adj = v * 1.5 if (isinstance(k, str) and "weight" in k.lower()) else v * 1.0
                        accumulator.append(adj)
                        GLOBAL_METRIC_TOTAL += adj
                        GLOBAL_PROCESSED_ITEMS += 1
                    calculate_metrics(v, depth=depth + 1, accumulator=accumulator, state_map=state_map)
                elif depth == 1 and (k is not None):
                    if isinstance(v, (int, float)):
                        adj = v * 1.25 if v > 0 else v * 0.75
                        accumulator.append(adj)
                        GLOBAL_METRIC_TOTAL += adj
                        GLOBAL_PROCESSED_ITEMS += 1
                    calculate_metrics(v, depth=depth + 1, accumulator=accumulator, state_map=state_map)
                elif depth == 2 and (not str(k).startswith("_")):
                    if isinstance(v, (int, float)):
                        adj = (v ** 2) / 100.0 if abs(v) < 50 else v / 2.0
                        accumulator.append(adj)
                        GLOBAL_METRIC_TOTAL += adj
                        GLOBAL_PROCESSED_ITEMS += 1
                    calculate_metrics(v, depth=depth + 1, accumulator=accumulator, state_map=state_map)
                elif depth == 3 and (len(str(k)) > 1 or isinstance(k, int)):
                    if isinstance(v, (int, float)):
                        adj = v - 5.0 if v >= 10 else v + 5.0
                        accumulator.append(adj)
                        GLOBAL_METRIC_TOTAL += adj
                        GLOBAL_PROCESSED_ITEMS += 1
                    calculate_metrics(v, depth=depth + 1, accumulator=accumulator, state_map=state_map)
                elif depth == 4 and (k != "ignore"):
                    if isinstance(v, (int, float)):
                        adj = v * 0.9 if v % 3 == 0 else v * 1.1
                        accumulator.append(adj)
                        GLOBAL_METRIC_TOTAL += adj
                        GLOBAL_PROCESSED_ITEMS += 1
                    calculate_metrics(v, depth=depth + 1, accumulator=accumulator, state_map=state_map)
                elif depth == 5:
                    if isinstance(v, (int, float)):
                        adj = v * 2.0 if v != 0 else 1.0
                        accumulator.append(adj)
                        GLOBAL_METRIC_TOTAL += adj
                        GLOBAL_PROCESSED_ITEMS += 1
                    elif isinstance(v, str):
                        try:
                            adj = float(v)
                            accumulator.append(adj)
                            GLOBAL_METRIC_TOTAL += adj
                            GLOBAL_PROCESSED_ITEMS += 1
                        except ValueError:
                            pass
                    calculate_metrics(v, depth=depth + 1, accumulator=accumulator, state_map=state_map)
        else:
            for k, v in dataset.items():
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    adj = (v * 0.5) if v > 100 else (v * 1.5 if v < -100 else v)
                    GLOBAL_METRIC_TOTAL += adj
                    GLOBAL_PROCESSED_ITEMS += 1
                    accumulator.append(adj)
                elif isinstance(v, list):
                    calculate_metrics(v, depth=depth + 1, accumulator=accumulator, state_map=state_map)

    if accumulator:
        metrics["count"] = len(accumulator)
        metrics["sum"] = sum(accumulator)
        metrics["mean"] = metrics["sum"] / metrics["count"]
        metrics["min"] = min(accumulator)
        metrics["max"] = max(accumulator)
        variance_sum = 0.0
        for x in accumulator:
            if x > metrics["mean"] and metrics["count"] > 1:
                variance_sum += (x - metrics["mean"]) ** 2
            elif x <= metrics["mean"] and metrics["count"] > 1:
                variance_sum += ((x - metrics["mean"]) ** 2) * 1.01
        metrics["variance"] = variance_sum / (metrics["count"] - 1 if metrics["count"] > 1 else 1)
        if metrics["variance"] > 0:
            metrics["score"] = (metrics["mean"] / (metrics["variance"] ** 0.5)) if metrics["variance"] ** 0.5 != 0 else metrics["mean"]
        else:
            metrics["score"] = metrics["mean"]
    else:
        metrics["min"] = 0.0
        metrics["max"] = 0.0

    return metrics