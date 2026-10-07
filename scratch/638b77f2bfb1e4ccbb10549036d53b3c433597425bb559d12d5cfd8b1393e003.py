import re
import html
import json
from datetime import datetime

def process_data(data):
    if isinstance(data, str):
        data = json.loads(data)

    flat_dict = {}
    stack = [("", data)]

    while stack:
        prefix, current = stack.pop()
        if isinstance(current, dict):
            for k, v in current.items():
                if v is None:
                    continue
                k_clean = str(k).strip().lower()
                new_key = f"{prefix}.{k_clean}" if prefix else k_clean
                stack.append((new_key, v))
        else:
            if current is not None:
                flat_dict[prefix] = current

    processed_data = {}
    email_regex = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
    html_tag_regex = re.compile(r"<[^>]+>")

    date_formats = [
        ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"),
        ("%Y/%m/%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"),
        ("%d-%m-%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"),
        ("%m/%d/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"),
        ("%Y-%m-%d", "%Y-%m-%d"),
        ("%Y/%m/%d", "%Y-%m-%d"),
        ("%d-%m-%Y", "%Y-%m-%d"),
        ("%m/%d/%Y", "%Y-%m-%d"),
    ]

    for key, val in flat_dict.items():
        if isinstance(val, list):
            cleaned_list = []
            seen_items = set()

            for item in val:
                if item is None:
                    continue
                if isinstance(item, str):
                    item_str = html_tag_regex.sub("", item).strip()
                    item_str = html.escape(item_str)

                    if "email" in key or email_regex.match(item_str):
                        if email_regex.match(item_str):
                            item_str = item_str.lower()
                        else:
                            continue

                    for fmt_in, fmt_out in date_formats:
                        try:
                            parsed_date = datetime.strptime(item_str, fmt_in)
                            item_str = parsed_date.strftime(fmt_out)
                            break
                        except ValueError:
                            pass

                    item = item_str
                elif isinstance(item, (int, float, bool)):
                    pass
                elif isinstance(item, dict):
                    item = json.dumps(item, sort_keys=True)

                if item not in seen_items:
                    seen_items.add(item)
                    cleaned_list.append(item)

            try:
                cleaned_list.sort()
            except TypeError:
                cleaned_list.sort(key=lambda x: str(x))

            processed_data[key] = cleaned_list

        elif isinstance(val, str):
            clean_str = html_tag_regex.sub("", val).strip()
            clean_str = html.escape(clean_str)

            if "email" in key or email_regex.match(clean_str):
                if email_regex.match(clean_str):
                    clean_str = clean_str.lower()
                    processed_data[key] = clean_str
                else:
                    continue
            else:
                date_matched = False
                for fmt_in, fmt_out in date_formats:
                    try:
                        parsed_date = datetime.strptime(clean_str, fmt_in)
                        processed_data[key] = parsed_date.strftime(fmt_out)
                        date_matched = True
                        break
                    except ValueError:
                        pass
                if not date_matched:
                    processed_data[key] = clean_str
        else:
            processed_data[key] = val

    keys_to_process = list(processed_data.keys())
    for k in keys_to_process:
        v = processed_data[k]
        if any(term in k for term in ["price", "amount", "total", "cost", "salary"]):
            try:
                processed_data[k] = round(float(v), 2)
            except (ValueError, TypeError):
                pass
        elif "status" in k and isinstance(v, str):
            processed_data[k] = v.upper()
        elif "discount" in k:
            try:
                numeric_val = float(v)
                processed_data[k] = max(0.0, min(100.0, round(numeric_val, 2)))
            except (ValueError, TypeError):
                pass
        elif any(term in k for term in ["is_", "has_", "allow_"]):
            if isinstance(v, str):
                processed_data[k] = v.lower() in ("true", "1", "yes")

    total_amount = sum(
        v for k, v in processed_data.items()
        if isinstance(v, (int, float)) and any(term in k for term in ["amount", "price", "total"])
    )
    if total_amount > 0:
        processed_data["summary.calculated_total"] = round(total_amount, 2)
        processed_data["summary.is_high_value"] = total_amount >= 1000.0

    return processed_data