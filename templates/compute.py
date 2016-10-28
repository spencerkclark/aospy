from aospy import Calc, CalcInterface

from aospy_example import projects, models, runs, variables


calc_int = CalcInterface(
    proj=projects.example,
    model=models.im,
    run=runs.im_example,
    var=variables.precip,
    date_range=('0003-01-01', '0006-12-31'),
    intvl_in='monthly',
    dtype_in_time='ts',
    intvl_out='ann',
    dtype_out_time='av'
)
calc = Calc(calc_int)
calc.compute()
