from aospy import Run
from datetime import datetime, timedelta

# AM2
am2_control = Run(
    name='am2_control',
    description=(
        'Preindustrial control simulation.'
    ),
    data_in_direc=('/archive/Yi.Ming/sm2.1_fixed/'
                   'SM2.1U_Control-1860_lm2_aie_rerun6.YIM/pp'),
    data_in_dur=5,
    data_in_start_date='0001-01-01',
    data_in_end_date='0080-12-31',
    default_date_range=('0021-01-01', '0080-12-31'),
)


# IDEALIZED
# S. Clark 10-30-2015: Contrary to what idealized model runs suggest,
# we start at year 1 NOT 0.
# Also note that it throws things into a 365 day no-leap calendar.
# So if you want the last 360 days you need to be smarter about things.

# Specify variables containted by output files.
var = ['olr', 'vcomp']

# If we run more than four years we'll have to think about leap years,
# but for now this is OK.
model_start = datetime(1, 1, 1)
length = timedelta(days=720)
end = model_start + length
analysis_length = timedelta(days=360)
a_start = str(end - analysis_length)
a_end = str(end)

control_T85 = Run(
    name='control_T85',
    description=(
        'A test case for using aospy + an idealized simulation.'
    ),
    data_in_direc='/archive/skc/idealized_moist_T85/control_T85/'
                  'gfdl.ncrc2-default-prod/1x0m720d_32pe/history',
    default_date_range=(a_start, a_end),
    data_in_dir_struc='one_dir',
    data_in_files={'20-day': {v: '00000.1x20days.nc' for v in var},
                   'daily': {v: '00000.1xday.nc' for v in var},
                   '6-hourly': {v: '00000.4xday.nc' for v in var}}
)
