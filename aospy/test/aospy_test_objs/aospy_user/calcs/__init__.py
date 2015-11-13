"""My library of functions for use in aospy.
"""
import numpy as np
import xray

from aospy.constants import (c_p, grav, kappa, L_f, L_v, r_e, Omega, p_trip,
                             T_trip, c_va, c_vv, c_vl, c_vs, R_a, R_v,
                             E_0v, E_0s, s_0v, s_0s)
from aospy.utils import (level_thickness, to_pascal, to_radians,
                         integrate, int_dp_g, dp_from_ps)# weight_by_delta) #vert_coord_name)


def dp(ps, bk, pk, arr):
    """Pressure thickness of hybrid coordinate levels from surface pressure."""
    return dp_from_ps(bk, pk, ps, arr[PFULL_STR])

# Take advantage of Spencer Hill's numerical functions.
from .numerics import (
    fwd_diff1,
    fwd_diff2,
    # cen_diff2,
    # cen_diff4,
    upwind_scheme,
    latlon_deriv_prefactor,
    wraparound_lon,
    d_dx_from_latlon,
    d_dy_from_lat,
    d_dx_at_const_p_from_eta,
    d_dy_at_const_p_from_eta,
    d_dx_of_vert_int,
    d_dy_of_vert_int,
    d_dp_from_p,
    d_dp_from_eta
)

def vert_coord_name(dp):
    for name in ['level', 'pfull']:
        if name in dp.coords:
            return name
    return None

def pfull(p):
    """ Returns the pressure at the level midpoints."""
    return to_pascal(p)
