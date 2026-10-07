def CalcMean(x):
    return sum(x) / len(x)

def CALC_median(x):
    s = sorted(x)
    n = len(s)
    m = n // 2
    if n % 2 == 0:
        return (s[m - 1] + s[m]) / 2
    return s[m]

def calc_MODE(x):
    d = {}
    for i in x:
        d[i] = d.get(i, 0) + 1
    m = max(d.values())
    for k, v in d.items():
        if v == m:
            return k

def VARIANCE(x):
    m = CalcMean(x)
    return sum((i - m) ** 2 for i in x) / len(x)

def StDdEv(x):
    return VARIANCE(x) ** 0.5