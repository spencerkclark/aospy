from aospy.proj import Proj
from aospy_user import regions, variables, models

tests = Proj(
    'tests',
    vars=variables.master_vars_list,
    direc_out='/archive/skc/aospy_tests/',
    models=(
        models.am2,
        models.dargan
    ),
    regions=(regions.globe,
             regions.land,
             regions.ocean)
)
