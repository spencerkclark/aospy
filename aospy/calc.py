"""calc.py: classes for performing specified calculations on aospy data"""
from __future__ import print_function
import os
import shutil
import subprocess
import tarfile
import time
import warnings

import numpy as np
import xray

from . import Constant, Var
from .__config__ import (LAT_STR, LON_STR, LAT_BOUNDS_STR, LON_BOUNDS_STR,
                         PHALF_STR, PFULL_STR, PLEVEL_STR, TIME_STR, YEAR_STR)
from .io import (_data_in_label, _data_out_label, _ens_label, _yr_label, dmget,
                 data_in_name_gfdl)
from .timedate import TimeManager, _get_time
from .utils import (get_parent_attr, apply_time_offset, monthly_mean_ts,
                    monthly_mean_at_each_ind, pfull_from_ps,
                    to_pfull_from_phalf, dp_from_ps, dp_from_p, int_dp_g,
                    to_pascal)


dp = Var(
    name='dp',
    units='Pa',
    domain='atmos',
    description='Pressure thickness of model levels.',
    def_time=True,
    def_vert=True,
    def_lat=True,
    def_lon=True,
    in_nc_grid=False,
 )
ps = Var(
    name='ps',
    units='Pa',
    domain='atmos',
    description='Surface pressure.',
    def_time=True,
    def_vert=False,
    def_lat=True,
    def_lon=True,
    in_nc_grid=False
)


class CalcInterface(object):
    """Interface to Calc class."""
    def _set_data_in_attrs(self):
        for attr in ('data_in_start_date',
                     'data_in_end_date',
                     'default_date_range',
                     'data_in_dur',
                     'data_in_direc',
                     'data_in_files',
                     'data_in_dir_struc',
                     'ens_mem_prefix',
                     'ens_mem_ext',
                     'idealized'):
            attr_val = tuple([get_parent_attr(rn, attr, strict=False)
                              for rn in self.run])
            setattr(self, attr, attr_val)

    def __init__(self, proj=None, model=None, run=None, ens_mem=None, var=None,
                 date_range=None, region=None, intvl_in=None, intvl_out=None,
                 dtype_in_time=None, dtype_in_vert=None, dtype_out_time=None,
                 dtype_out_vert=None, level=None, chunk_len=False,
                 verbose=True):
        """Create the CalcInterface object with the given parameters."""
        if run not in model.runs.values():
            raise AttributeError("Model '{}' has no run '{}'.  Calc object "
                                 "will not be generated.".format(model, run))
        # 2015-10-13 S. Hill: This tuple-izing is for support of calculations
        # where variables come from different runs.  However, this is a very
        # fragile way of implementing that functionality.  Eventually it will
        # be replaced with something better.
        proj = tuple([proj])
        model = tuple([model])
        if not isinstance(run, (list, tuple)):
            run = tuple([run])
        # Make tuples the same length.
        if len(proj) == 1 and (len(model) > 1 or len(run) > 1):
            proj = tuple(list(proj)*len(run))
        if len(model) == 1 and len(run) > 1:
            model = tuple(list(model)*len(run))

        self.proj = proj
        self.model = model
        self.run = run

        self._set_data_in_attrs()

        self.proj_str = '_'.join(set([p.name for p in self.proj]))
        self.model_str = '_'.join(set([m.name for m in self.model]))
        run_names = [r.name for r in self.run]
        self.run_str = '_'.join(set(run_names))
        self.run_str_full = '_'.join(run_names)

        self.var = var
        self.name = self.var.name
        self.domain = self.var.domain
        self.def_time = self.var.def_time
        self.def_vert = self.var.def_vert
        self.verbose = verbose

        try:
            self.function = self.var.func
        except AttributeError:
            self.function = lambda x: x
        if getattr(self.var, 'variables', False):
            self.variables = self.var.variables
        else:
            self.variables = (self.var,)

        self.ens_mem = ens_mem
        self.level = level
        self.intvl_in = intvl_in
        self.intvl_out = intvl_out
        self.dtype_in_time = dtype_in_time
        self.dtype_in_vert = dtype_in_vert
        self.ps = ps
        if isinstance(dtype_out_time, (list, tuple)):
            self.dtype_out_time = tuple(dtype_out_time)
        else:
            self.dtype_out_time = tuple([dtype_out_time])
        self.dtype_out_vert = dtype_out_vert
        self.region = region

        self.months = TimeManager.month_indices(intvl_out)
        self.start_date = TimeManager.str_to_datetime(date_range[0])
        self.end_date = TimeManager.str_to_datetime(date_range[-1])
        tm = TimeManager(self.start_date, self.end_date, intvl_out)
        self.date_range = tm.create_time_array()

        self.start_date_xray = tm.apply_year_offset(self.start_date)
        self.end_date_xray = tm.apply_year_offset(self.end_date)


class Calc(object):
    """Class for executing, saving, and loading a single computation."""

    ARR_XRAY_NAME = 'aospy_result'

    def __str__(self):
        """String representation of the object."""
        return "Calc object: " + ', '.join(
            (self.name, self.proj_str, self.model_str, self.run_str_full)
        )

    __repr__ = __str__

    def _dir_scratch(self):
        """Create string of the data directory on the scratch filesystem."""
        ens_label = _ens_label(self.ens_mem)
        return os.path.join('/work', os.getenv('USER'), self.proj_str,
                            self.model_str, self.run_str, ens_label,
                            self.name)

    def _dir_archive(self):
        """Create string of the data directory on the archive filesystem."""
        ens_label = _ens_label(self.ens_mem)
        return os.path.join('/archive', os.getenv('USER'),
                            self.proj_str, 'data', self.model_str,
                            self.run_str, ens_label)

    def _file_name(self, dtype_out_time, extension='nc'):
        """Create the name of the aospy file."""
        out_lbl = _data_out_label(self.intvl_out, dtype_out_time,
                                  dtype_vert=self.dtype_out_vert)
        in_lbl = _data_in_label(self.intvl_in, self.dtype_in_time,
                                self.dtype_in_vert)
        ens_lbl = _ens_label(self.ens_mem)
        yr_lbl = _yr_label((self.start_date.year,
                            self.end_date.year))
        return '.'.join(
            [self.name, out_lbl, in_lbl, self.model_str, self.run_str_full,
             ens_lbl, yr_lbl, extension]
        ).replace('..', '.')

    def _path_scratch(self, dtype_out_time):
        return os.path.join(self.dir_scratch, self.file_name[dtype_out_time])

    def _path_archive(self):
        return os.path.join(self.dir_archive, 'data.tar')

    def _print_verbose(self, *args):
        """Print diagnostic message."""
        if not self.verbose:
            pass
        else:
            try:
                print('{} {}'.format(args[0], args[1]),
                      '({})'.format(time.ctime()))
            except IndexError:
                print('{}'.format(args[0]), '({})'.format(time.ctime()))

    def __init__(self, calc_interface):
        self.__dict__ = vars(calc_interface)
        self._print_verbose('Initializing Calc instance:', self.__str__())

        [mod.set_grid_data() for mod in self.model]

        if isinstance(calc_interface.ens_mem, int):
            self.data_in_direc = self.data_in_direc[calc_interface.ens_mem]

        self.dt_set = False

        self.dir_scratch = self._dir_scratch()
        self.dir_archive = self._dir_archive()
        self.file_name = {d: self._file_name(d) for d in self.dtype_out_time}
        self.path_scratch = {d: self._path_scratch(d)
                             for d in self.dtype_out_time}
        self.path_archive = self._path_archive()

        self.data_out = {}

    def _data_in_files_one_dir(self, name, n=0):
        """Get the file names of the files in a single directory"""
        if self.intvl_in in self.data_in_files[n]:
            if isinstance(self.data_in_files[n][self.intvl_in][name], str):
                data_in_files = [self.data_in_files[n][self.intvl_in][name]]
            else:
                data_in_files = self.data_in_files[n][self.intvl_in][name]
        else:
            if isinstance(self.data_in_files[n][name], str):
                data_in_files = [self.data_in_files[n][name]]
            else:
                data_in_files = self.data_in_files[n][name]
        return data_in_files

    def _get_input_data_paths_one_dir(self, name, data_in_direc, n=0):
        """Get the names of netCDF files when all in same directory."""
        data_in_files = self._data_in_files_one_dir(name, n)
        # data_in_files may hold absolute or relative paths
        paths = []
        for nc in data_in_files:
            full = os.path.join(data_in_direc, nc)
            if os.path.isfile(nc):
                paths.append(nc)
            elif os.path.isfile(full):
                paths.append(full)
            else:
                print("Warning: specified netCDF file `{}` "
                      "not found".format(nc))
        # Remove duplicate entries.
        files = list(set(paths))
        files.sort()
        return files

    def _get_input_data_paths_gfdl_repo(self, name, n=0):
        """Get the names of netCDF files from a GFDL repo on /archive."""
        return self.model[n].find_data_in_direc_repo(
            run_name=self.run[n].name, var_name=name
        )

    def _get_input_data_paths_gfdl_dir_struct(self, name, data_in_direc,
                                              start_year, end_year, n=0):
        """Get paths to netCDF files save in GFDL standard output format."""
        domain = self.domain
        dtype_lbl = self.dtype_in_time
        if self.intvl_in == 'daily':
            domain += '_daily'
        if self.dtype_in_vert == 'sigma' and name != 'ps':
            domain += '_level'
        if self.dtype_in_time == 'inst':
            domain += '_inst'
            dtype_lbl = 'ts'
        if 'monthly_from_' in self.dtype_in_time:
            dtype = self.dtype_in_time.replace('monthly_from_', '')
            dtype_lbl = dtype
        else:
            dtype = self.dtype_in_time
        direc = os.path.join(data_in_direc, domain, dtype_lbl, self.intvl_in,
                             str(self.data_in_dur[n]) + 'yr')

        files = [os.path.join(direc, data_in_name_gfdl(
                 name, domain, dtype, self.intvl_in, year, self.intvl_out,
                 self.data_in_start_date[n].year, self.data_in_dur[n]
                 )) for year in range(start_year, end_year + 1)]

        # Remove duplicate entries.
        files = list(set(files))
        files.sort()
        return files

    def _get_data_in_direc(self, n):
        if isinstance(self.data_in_direc, str):
            return self.data_in_direc
        if isinstance(self.data_in_direc, (list, tuple)):
            return self.data_in_direc[n]
        raise IOError("data_in_direc must be string, list, or tuple: "
                      "{}".format(self.data_in_direc))

    def _get_input_data_paths(self, var, start_date=False,
                              end_date=False, n=0):
        """Create xray.DataArray of the variable from its netCDF files on disk.

        Files chosen depend on the specified variables and time interval and
        the attributes of the netCDF files.
        """
        data_in_direc = self._get_data_in_direc(n)
        # Cycle through possible names until the data is found.
        for name in var.names:
            if self.data_in_dir_struc[n] == 'one_dir':
                try:
                    files = self._get_input_data_paths_one_dir(
                        name, data_in_direc, n=n
                    )
                except KeyError:
                    pass
                else:
                    break
            elif self.data_in_dir_struc[n].lower() == 'gfdl':
                try:
                    files = self._get_input_data_paths_gfdl_dir_struct(
                        name, data_in_direc, start_date.year,
                        end_date.year, n=n
                    )
                except:
                    raise
                else:
                    break
            elif self.data_in_dir_struc[n].lower() == 'gfdl_repo':
                try:
                    files = self._get_input_data_paths_gfdl_repo(name, n=n)
                except IOError:
                    pass
                else:
                    break
            else:
                raise ValueError("Specified directory type not supported"
                                 ": {}".format(self.data_in_dir_struc[n]))
        else:
            raise IOError("netCDF files for variable `{}`, year range {}-{}, "
                          "in directory {}, not found".format(var, start_date,
                                                              end_date,
                                                              data_in_direc))
        paths = list(set(files))
        paths.sort()
        return paths

    def _to_desired_dates(self, arr):
        """Restrict the xray DataArray or Dataset to the desired months."""
        times = _get_time(arr[TIME_STR], self.start_date_xray,
                          self.end_date_xray, self.months, indices=False)
        return arr.sel(time=times)

    def _add_grid_attributes(self, ds, n=0):
        """Add model grid attributes to a dataset"""

        grid_attrs = {
            LAT_STR:        ('lat', 'latitude', 'LATITUDE', 'y', 'yto'),
            LAT_BOUNDS_STR: ('latb', 'lat_bnds', 'lat_bounds'),
            LON_STR:        ('lon', 'longitude', 'LONGITUDE', 'x', 'xto'),
            LON_BOUNDS_STR: ('lonb', 'lon_bnds', 'lon_bounds'),
            PLEVEL_STR:     ('level', 'lev', 'plev'),
            'sfc_area':     ('area', 'sfc_area'),
            'zsurf':        ('zsurf',),
            'land_mask':    ('land_mask',),
            'pk':           ('pk',),
            'bk':           ('bk',),
            PHALF_STR:      ('phalf',),
            PFULL_STR:      ('pfull',),
            }

        for name_int, names_ext in grid_attrs.items():
            ds_coord_name = set(names_ext).intersection(set(ds.coords))
            # print(name_int, names_ext, ds_coord_name)
            if ds_coord_name:
                # Check if coord is in dataset already.  If it is, then rename
                # it so that it has the correct internal name.
                ds = ds.rename({list(ds_coord_name)[0]: name_int})
                ds = ds.set_coords(name_int)
                if not ds[name_int].equals(getattr(self.model[n], name_int)):
                    warnings.warn("Model coordinates for '{}'"
                                  "do not match those in Run".format(name_int))
            else:
                # Bring in coord from model object if it exists.
                if getattr(self.model[n], name_int, None) is not None:
                    ds[name_int] = getattr(self.model[n], name_int)
                    ds = ds.set_coords(name_int)
            if self.dtype_in_vert == 'pressure' and 'level' in ds.coords:
                self.pressure = ds.level
                ds.level = to_pascal(ds.level)
        # print(ds)
        return ds

    def _create_input_data_obj(self, var, start_date=False,
                               end_date=False, n=0, set_dt=False,
                               set_pfull=False):
        """Create xray.DataArray for the Var from files on disk."""
        paths = self._get_input_data_paths(var, start_date, end_date, n)
        # 2015-10-15 S. Hill: This `dmget` call, which is unique to the
        # filesystem at the NOAA GFDL computing cluster, should be factored out
        # of this function.  A config setting or some other user input should
        # specify what method to call to access the files on the filesystem.
        dmget(paths)
        ds_chunks = []
        # 2015-10-16 S. Hill: Can we use the xray.open_mfdataset function here
        # instead of this logic of making individual datasets and then
        # calling xray.concat?  Or does the year<1678 logic make this not
        # possible?

        # 2015-10-16 19:06:00 S. Clark: The year<1678 logic is independent of
        # using xray.open_mfdataset. The main reason I held off on using it
        # here was that it opens a can of worms with regard to performance;
        # we'd need to add some logic to make sure the data were chunked in a
        # reasonable way (and logic to change the chunking if need be).
        for file_ in paths:
            test = xray.open_dataset(file_, decode_cf=False,
                                     drop_variables=['time_bounds', 'nv',
                                                     'average_T1',
                                                     'average_T2'])
            if start_date.year < 1678:
                for v in [TIME_STR]:
                    test[v].attrs['units'] = ('days since 1900-01-01 '
                                              '00:00:00')
                test[TIME_STR].attrs['calendar'] = 'noleap'
            test = xray.decode_cf(test)
            ds_chunks.append(test)
        ds = xray.concat(ds_chunks, dim=TIME_STR)
        ds = self._add_grid_attributes(ds, n)
        for name in var.names:
            try:
                arr = ds[name]
            except KeyError:
                pass
            else:
                break
        else:
            raise KeyError('Variable not found: {}'.format(var))
        # At least one variable has to get us the dt array also.
        if set_dt:
            for name in ['average_DT']:
                try:
                    dt = ds[name]
                except KeyError:
                    pass
                else:
                    # Convert from nanoseconds to seconds (prevent overflow)
                    self.dt = (self._to_desired_dates(dt) /
                               np.timedelta64(1, 's'))
                    break
        # At least one variable has to get us the pfull array, if its needed.
        if set_pfull:
            try:
                self.pfull = ds[PFULL_STR]
            except KeyError:
                pass
        return arr

    def _get_pressure_vals(self, var, start_date, end_date, n=0):
        """Get pressure array, whether sigma or standard levels."""
        ps = self._create_input_data_obj(self.ps, start_date, end_date)

        if self.dtype_in_vert == 'pressure':
            if np.any(self.pressure):
                pressure = self.pressure
            else:
                pressure = self.model[n].level
            if var.name == 'p':
                data = pressure
            elif var.name == 'dp':
                data = dp_from_p(pressure, ps)

        elif self.dtype_in_vert == 'sigma':
            bk = self.model[n].bk
            pk = self.model[n].pk
            pfull_coord = self.model[n].pfull
            if var.name == 'p':
                data = pfull_from_ps(bk, pk, ps, pfull_coord)
            elif var.name == 'dp':
                data = dp_from_ps(bk, pk, ps, pfull_coord)
            else:
                raise ValueError("var.name must be 'p' or 'dp':"
                                 "'{}'".format(var.name))
        else:
            raise ValueError("`dtype_in_vert` must be either 'pressure' or "
                             "'sigma' for pressure data")
        return data

    def _correct_gfdl_inst_time(self, arr):
        """Correct off-by-one error in GFDL instantaneous model data."""
        time = arr[TIME_STR]
        if self.intvl_in == '3hr':
            offset = -3
        elif self.intvl_in == '6hr':
            offset = -6
        time = apply_time_offset(time, hours=offset)
        arr[TIME_STR] = time
        return arr

    def _get_input_data(self, var, start_date, end_date, n):
        """Get the data for a single variable over the desired date range."""
        self._print_verbose("Getting input data:", var)
        # If only 1 run, use it to load all data.  Otherwise assume that num
        # runs equals num vars to load.
        if len(self.run) == 1:
            n = 0
        # Pass numerical constants as is.
        if isinstance(var, (float, int)):
            return var
        elif isinstance(var, Constant):
            return var.value
        # aospy.Var objects remain.
        # Pressure handled specially due to complications from sigma vs. p.
        elif var.name in ('p', 'dp'):
            data = self._get_pressure_vals(var, start_date, end_date)
            if self.dtype_in_vert == 'sigma':
                if self.dtype_in_time == 'inst':
                    data = self._correct_gfdl_inst_time(data)
                return self._to_desired_dates(data)
            return data
        # Get grid, time, etc. arrays directly from model object
        elif var.name in (LAT_STR, LON_STR, TIME_STR, PLEVEL_STR,
                          'pk', 'bk', 'sfc_area'):
            data = getattr(self.model[n], var.name)
        else:
            set_dt = True if not hasattr(self, 'dt') else False
            cond_pfull = (not hasattr(self, 'pfull') and var.def_vert and
                          self.dtype_in_vert == 'sigma')
            set_pfull = True if cond_pfull else False
            data = self._create_input_data_obj(var, start_date, end_date, n=n,
                                               set_dt=set_dt,
                                               set_pfull=set_pfull)
            # Force all data to be at full pressure levels, not half levels.
            if self.dtype_in_vert == 'sigma' and var.def_vert == 'phalf':
                data = to_pfull_from_phalf(data, self.pfull)
        # Correct GFDL instantaneous data time indexing problem.
        if var.def_time:
            if self.dtype_in_time == 'inst':
                data = self._correct_gfdl_inst_time(data)
            # Restrict to the desired dates within each year.
            return self._to_desired_dates(data)
        return data

    def _prep_data(self, data, func_input_dtype):
        """Convert data to type needed by the given function.

        :param data: List of xray.DataArray objects.
        :param func_input_dtype: One of (None, 'DataArray', 'Dataset',
                                 'numpy'). Specifies which datatype to convert
                                 to.
        """
        if func_input_dtype is None:
            return data
        if func_input_dtype == 'DataArray':
            return data
        if func_input_dtype == 'Dataset':
            # S. Hill 2015-10-19: This should be filled in with logic that
            # creates a single Dataset comprising all of the DataArray objects
            # in `data`.
            return NotImplementedError
        if func_input_dtype == 'numpy':
            self.coords = data[0].coords
            return [d.values for d in data]
        raise ValueError("Unknown func_input_dtype "
                         "'{}'.".format(func_input_dtype))

    def _get_all_data(self, start_date, end_date):
        """Get the needed data from all of the vars in the calculation."""
        return [self._prep_data(self._get_input_data(var, start_date,
                                                     end_date, n),
                                self.var.func_input_dtype)
                for n, var in enumerate(self.variables)]

    def _local_ts(self, *data_in):
        """Perform the computation at each gridpoint and time index."""
        arr = self.function(*data_in)
        if self.var.func_input_dtype == 'numpy':
            arr = xray.DataArray(arr, coords=self.coords)
        arr.name = self.name
        return arr

    def _compute(self, data_in, monthly_mean=False):
        """Perform the calculation."""
        if monthly_mean:
            data_monthly = []
            for d in data_in:
                try:
                    data_monthly.append(monthly_mean_ts(d))
                except KeyError:
                    data_monthly.append(d)
            data_in = data_monthly
        local_ts = self._local_ts(*data_in)
        if self.dtype_in_time == 'inst':
            dt = xray.DataArray(np.ones(np.shape(local_ts[TIME_STR])),
                                dims=[TIME_STR], coords=[local_ts[TIME_STR]])
        else:
            dt = self.dt
        if monthly_mean:
            dt = monthly_mean_ts(dt)
        return local_ts, dt

    def _vert_int(self, arr, dp):
        """Vertical integral"""
        return int_dp_g(arr, dp)

    def _compute_full_ts(self, data_in, monthly_mean=False, zonal_asym=False):
        """Perform calculation and create yearly timeseries at each point."""
        # Get results at each desired timestep and spatial point.
        # Here we need to provide file read-in dates (NOT xray dates)
        full_ts, dt = self._compute(data_in, monthly_mean=monthly_mean)
        if zonal_asym:
            full_ts = full_ts - full_ts.mean(LON_STR)
        # Vertically integrate.
        if self.dtype_out_vert == 'vert_int' and self.var.def_vert:
            # Here we need file read-in dates (NOT xray dates)
            full_ts = self._vert_int(full_ts, self._get_pressure_vals(
                dp, self.start_date, self.end_date
            ))
        return full_ts, dt

    def _avg_by_year(self, arr, dt):
        """Average a sub-yearly time-series over each year."""
        return ((arr*dt).groupby('time.year').sum(TIME_STR) /
                dt.groupby('time.year').sum(TIME_STR))

    def _full_to_yearly_ts(self, arr, dt):
        """Average the full timeseries within each year."""
        time_defined = self.def_time and not ('av' in self.dtype_in_time or
                                              self.idealized[0])
        if time_defined:
            arr = self._avg_by_year(arr, dt)
        return arr

    def _time_reduce(self, arr, reduction):
        """Perform the specified time reduction on a local time-series."""
        reductions = {
            'None': lambda xarr: xarr,
            'ts': lambda xarr: xarr,
            'av': lambda xarr: xarr.mean(YEAR_STR),
            'std': lambda xarr: xarr.std(YEAR_STR),
            }
        try:
            return reductions[reduction](arr)
        except KeyError:
            raise ValueError("Specified time-reduction method '{}' is not "
                             "supported".format(reduction))

    def region_calcs(self, arr, func, n=0):
        """Perform a calculation for all regions."""
        reg_dat = {}
        for reg in self.region.values():
            # Just pass along the data if averaged already.
            if 'av' in self.dtype_in_time:
                data_out = reg.ts(arr)
            # Otherwise perform the calculation.
            else:
                method = getattr(reg, func)
                data_out = method(arr)
            reg_dat.update({reg.name: data_out})
        return reg_dat

    def compute(self):
        """Perform all desired calculations on the data and save externally."""
        # Load the input data from disk.
        data_in = self._prep_data(self._get_all_data(self.start_date,
                                                     self.end_date),
                                  self.var.func_input_dtype)
        # Compute only the needed timeseries.
        self._print_verbose('\n', 'Computing desired timeseries for '
                            '{} -- {}.'.format(self.start_date, self.end_date))
        bool_monthly = (['monthly_from' in self.dtype_in_time] +
                        ['time-mean' in dout for dout in self.dtype_out_time])
        bool_eddy = ['eddy' in dout for dout in self.dtype_out_time]
        if not all(bool_monthly):
            full_ts, full_dt = self._compute_full_ts(data_in,
                                                     monthly_mean=False)
        else:
            full_ts = False
        if any(bool_eddy) or any(bool_monthly):
            monthly_ts, monthly_dt = self._compute_full_ts(data_in,
                                                           monthly_mean=True)
        else:
            monthly_ts = False
        if any(bool_eddy):
            eddy_ts = full_ts - monthly_mean_at_each_ind(monthly_ts, full_ts)
        else:
            eddy_ts = False

        # Average within each year.
        if not all(bool_monthly):
            full_ts = self._full_to_yearly_ts(full_ts, full_dt)
        if any(bool_monthly):
            monthly_ts = self._full_to_yearly_ts(monthly_ts, monthly_dt)
        if any(bool_eddy):
            eddy_ts = self._full_to_yearly_ts(eddy_ts, full_dt)
        # Apply time reduction methods.
        if self.def_time:
            self._print_verbose("Applying desired time-reduction methods.")
            # Determine which are regional, eddy, time-mean.
            reduc_specs = [r.split('.') for r in self.dtype_out_time]
            reduced = {}
            for reduc, specs in zip(self.dtype_out_time, reduc_specs):
                func = specs[-1]
                if 'eddy' in specs:
                    data = eddy_ts
                elif 'time-mean' in specs:
                    data = monthly_ts
                else:
                    data = full_ts
                if 'reg' in specs:
                    reduced.update({reduc: self.region_calcs(data, func)})
                else:
                    reduced.update({reduc: self._time_reduce(data, func)})
        else:
            reduced = {'': full_ts}

        # Save to disk.
        self._print_verbose("Writing desired gridded outputs to disk.")
        for dtype_time, data in reduced.items():
            self.save(data, dtype_time, dtype_out_vert=self.dtype_out_vert)

    def _save_to_scratch(self, data, dtype_out_time):
        """Save the data to the scratch filesystem."""
        path = self.path_scratch[dtype_out_time]
        # Drop undefined coords.
        if not os.path.isdir(self.dir_scratch):
            os.makedirs(self.dir_scratch)
        if 'reg' in dtype_out_time:
            try:
                reg_data = xray.open_dataset(path)
            except (EOFError, RuntimeError):
                reg_data = xray.Dataset()
            # Add the new data to the dictionary or Dataset.
            # Same method works for both.
            reg_data.update(data)
            data_out = reg_data
        else:
            data_out = data
        if isinstance(data_out, xray.DataArray):
            data_out = xray.Dataset({self.name: data_out})
        data_out.to_netcdf(path, engine='scipy')

    def _save_to_archive(self, dtype_out_time):
        """Add the data to the tar file in /archive."""
        if not os.path.isdir(self.dir_archive):
            os.makedirs(self.dir_archive)
        # tarfile 'append' mode won't overwrite the old file, which we want.
        # So open in 'read' mode, extract the file, and then delete it.
        # But 'read' mode throws OSError if file doesn't exist: make it first.
        dmget([self.path_archive])
        with tarfile.open(self.path_archive, 'a') as tar:
            pass
        with tarfile.open(self.path_archive, 'r') as tar:
            old_data_path = os.path.join(self.dir_archive,
                                         self.file_name[dtype_out_time])
            try:
                tar.extract(self.file_name[dtype_out_time],
                            path=old_data_path)
            except KeyError:
                pass
            else:
                # The os module treats files on archive as non-empty
                # directories, so can't use os.remove or os.rmdir.
                shutil.rmtree(old_data_path)
                subprocess.call([
                    "tar", "--delete", "--file={}".format(self.path_archive),
                    self.file_name[dtype_out_time]
                ])
        with tarfile.open(self.path_archive, 'a') as tar:
            tar.add(self.path_scratch[dtype_out_time],
                    arcname=self.file_name[dtype_out_time])

    def _update_data_out(self, data, dtype):
        """Append the data of the given dtype_out to the data_out attr."""
        try:
            self.data_out.update({dtype: data})
        except AttributeError:
            self.data_out = {dtype: data}

    def save(self, data, dtype_out_time, dtype_out_vert=False,
             scratch=True, archive=False):
        """Save aospy data to data_out attr and to an external file."""
        self._update_data_out(data, dtype_out_time)
        if scratch:
            self._save_to_scratch(data, dtype_out_time)
        if archive:
            self._save_to_archive(dtype_out_time)
        print('\t', '{}'.format(self.path_scratch[dtype_out_time]))

    def _load_from_scratch(self, dtype_out_time, dtype_out_vert=False):
        """Load aospy data saved on scratch file system."""
        ds = xray.open_dataset(self.path_scratch[dtype_out_time],
                               engine='scipy')
        return ds[self.name]

    def _load_from_archive(self, dtype_out_time, dtype_out_vert=False):
        """Load data save in tarball on archive file system."""
        path = os.path.join(self.dir_archive, 'data.tar')
        dmget([path])
        with tarfile.open(path, 'r') as data_tar:
            ds = xray.open_dataset(
                data_tar.extractfile(self.file_name[dtype_out_time]),
                engine='scipy'
            )
            return ds[self.name]

    def _get_data_subset(self, data, region=False, time=False,
                         vert=False, lat=False, lon=False, n=0):
        """Subset the data array to the specified time/level/lat/lon, etc."""
        if region:
            # if type(region) is str:
                # data = data[region]
            # elif type(region) is Region:
            data = data[region.name]
        if np.any(time):
            data = data[time]
            if 'monthly_from_' in self.dtype_in_time:
                data = np.mean(data, axis=0)[np.newaxis, :]
        if np.any(vert):
            if self.dtype_in_vert != 'sigma':
                if np.max(self.model[n].level) > 1e4:
                    # Convert from Pa to hPa.
                    lev_hpa = self.model[n].level*1e-2
                else:
                    lev_hpa = self.model[n].level
                level_index = np.where(lev_hpa == self.level)
                if 'ts' in self.dtype_out_time:
                    data = np.squeeze(data[:, level_index])
                else:
                    data = np.squeeze(data[level_index])
        if np.any(lat):
            raise NotImplementedError
        if np.any(lon):
            raise NotImplementedError
        return data

    def load(self, dtype_out_time, dtype_out_vert=False, region=False,
             time=False, vert=False, lat=False, lon=False, plot_units=False,
             mask_unphysical=False):
        """Load the data from the object if possible or from disk."""
        # Grab from the object if its there.
        try:
            data = self.data_out[dtype_out_time]
        except (AttributeError, KeyError):
            # Otherwise get from disk.  Try scratch first, then archive.
            try:
                data = self._load_from_scratch(dtype_out_time, dtype_out_vert)
            except IOError:
                data = self._load_from_archive(dtype_out_time, dtype_out_vert)
        # Copy the array to self.data_out for ease of future access.
        self._update_data_out(data, dtype_out_time)
        # Subset the array and convert units as desired.
        if any((region, time, vert, lat, lon)):
            data = self._get_data_subset(data, region=region, time=time,
                                         vert=vert, lat=lat, lon=lon)
        # Apply desired plotting/cleanup methods.
        if mask_unphysical:
            data = self.var.mask_unphysical(data)
        if plot_units:
            data = self.var.to_plot_units(data, vert_int=dtype_out_vert)
        return data
