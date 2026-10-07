"""Small event summaries; absent objects are NaN, absent collections stay absent."""
import math
from .physics import from_pt_eta_phi_m


def summarize_objects(name, objects):
    """Objects are (pt, eta, phi, mass), ranked by descending transverse momentum."""
    objects = sorted(objects, key=lambda obj: obj[0], reverse=True)
    result = {f"n_{name}": len(objects)}
    for rank, index in (("leading", 0), ("subleading", 1)):
        for field, offset in (("pt", 0), ("eta", 1)):
            result[f"{rank}_{name}_{field}"] = objects[index][offset] if len(objects) > index else math.nan
    result[f"m_{name}_pair"] = math.nan
    if len(objects) >= 2:
        result[f"m_{name}_pair"] = (from_pt_eta_phi_m(*objects[0]) + from_pt_eta_phi_m(*objects[1])).mass
    return result


def empty_pair():
    return {f"l{i}_{field}": math.nan for i in (1, 2)
            for field in ("pt", "eta", "phi", "mass", "charge", "flavor")}
