import re
import pandas as pd


def read_orders():
    """Parse orders CSV despite unquoted commas in address fields."""
    rows = []
    with open("data/orders.csv") as f:
        f.readline()
        for line in f:
            m = re.match(r"^(\d+),([A-Z]{5}),(\d+),([^,]+),", line)
            if m:
                rows.append({
                    "orderID": int(m.group(1)),
                    "customerID": m.group(2),
                    "orderDate": m.group(4),
                })
    return pd.DataFrame(rows)
