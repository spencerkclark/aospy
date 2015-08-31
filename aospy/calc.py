"""calc.py: classes for performing specified calculations on aospy data"""
import cPickle
import os
import shutil
import subprocess
import tarfile
import time

import netCDF4
import numpy as np

from . import Constant, Var, Region
from .io import (_data_in_label, _data_out_label, _ens_label, _get_time,
                 _month_indices, _yr_label, dmget, nc_name_gfdl)
from .utils import (get_parent_attr, level_thickness, pfull_from_sigma,
                    dp_from_sigma, int_dp_g)

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
    """Class for executing, saving, and loading a single computation."""
    def _get_yr_range(self):
        """Set the object's span of years."""
        if self.yr_range == 'default':
            start_yr, end_yr = get_parent_attr(self.run[0], 'default_yr_range')
        elif self.yr_range == 'all':
            start_yr = get_parent_attr(self.run[0], 'nc_start_yr')
            end_yr = get_parent_attr(self.run[0], 'nc_end_yr')
        else:
            start_yr, end_yr = self.yr_range
        return start_yr, end_yr

    def _get_num_yr(self):
        """Compute effective number of years in the input data."""
        if self.dtype_in_time in ('ts', 'inst'):
            num_yr = self.end_yr - self.start_yr + 1
        else:
            num_yr = 1
        return num_yr

    def _make_time_chunks(self):
        """Create tuple of (start, end) pairs based on given year chunks."""
        if self.yr_chunk_len:
            dur = self.yr_chunk_len - 1
            st_yrs = range(self.start_yr, self.end_yr + 1, self.yr_chunk_len)
            end_yrs = range(self.start_yr + dur, self.end_yr + dur + 1,
                            self.yr_chunk_len)
            if len(end_yrs) == len(st_yrs) - 1:
                end_yrs.append(self.end_yr)
        else:
            st_yrs, end_yrs = [self.start_yr], [self.end_yr]
        return zip(st_yrs, end_yrs)

    def __init__(self, proj=None, model=None, run=None, ens_mem=None, var=None,
                 yr_range=None, region=None, intvl_in=None, intvl_out=None,
                 dtype_in_time=None, dtype_in_vert=None, dtype_out_time=None,
                 dtype_out_vert=None, level=None, skip_time_inds=False,
                 yr_chunk_len=False, verbose=True):
        """Create the CalcInterface object with the given parameters."""
        if run not in model.runs.values():
            raise AttributeError("Model '%s' has no run '%s'.  Calc object "
                                 "will not be generated." % (model, run))
        # Everything gets turned into tuples.
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

        self.yr_range = yr_range
        self.start_yr, self.end_yr = self._get_yr_range()
        self.num_yr = self._get_num_yr()
        self.months = _month_indices(intvl_out, iterable=True)
        self.skip_time_inds = skip_time_inds
        self.yr_chunk_len = yr_chunk_len
        self.chunk_ranges = self._make_time_chunks()


class Calc(object):
    """Class for executing, saving, and loading a single computation."""
    def __init__(self, calc_interface):
        self.__dict__ = vars(calc_interface)
        self._print_verbose("\nInitializing Calc instance: %s", self.__str__())

        [mod.set_grid_data() for mod in self.model]
        self._set_nc_attrs()

        if isinstance(calc_interface.ens_mem, int):
            self.direc_nc = self.direc_nc[calc_interface.ens_mem]

        if not calc_interface.skip_time_inds:
            self._set_time_dt()

        self.dir_scratch = self._dir_scratch()
        self.dir_archive = self._dir_archive()
        self.file_name = {d: self._file_name(d) for d in self.dtype_out_time}
        self.path_scratch = {
            d: '/'.join([self.dir_scratch,
                         self.file_name[d]]).replace('//', '/')
            for d in self.dtype_out_time
        }
        self.path_archive = (
            '/'.join([self.dir_archive, 'data.tar']).replace('//', '/')
        )

        self.data_out = {}

    def __str__(self):
        """String representation of the object."""
        return "Calc object: " + ', '.join(
            (self.name, self.proj_str, self.model_str, self.run_str_full)
        )

    __repr__ = __str__

    # 2015-08-28: These __call__ and __add__ methods were never fully
    # implemented, let alone tested.  Nor is their resulting functionality used
    # at all currently.
    # def __call__(self, dtype_out):
    #     try:
    #         data = self.data_out[dtype_out]
    #     except AttributeError:
    #         raise AttributeError("'data_out' attribute has not been set for "
    #                              "aospy.Calc object '%s'." % self)
    #     except KeyError:
    #         raise KeyError("No data exists for dtype '%s' for aospy.Calc "
    #                        "object '%s'." % (dtype_out, self))
    #     else:
    #         return data

    # def __add__(self, other):
    #     """Add aospy.Calc.data_out, numpy.array, int, or float to the array."""
    #     try:
    #         data_self = getattr(self, 'data_out')
    #     except AttributeError:
    #         raise AttributeError("Object '%s' lacks a 'data_out' attr" % self)
    #     # aospy.Calc, numpy array, and int/flot objects each use a different
    #     # named attribute to store their values
    #     for attr in ('data_out', '__array__', 'real'):
    #         try:
    #             data_other = getattr(other, 'data_out')
    #         except AttributeError:
    #             pass
    #         else:
    #             break
    #     return np.add(data_self, data_other)

    def _print_verbose(self, *args):
        """Print diagnostic message."""
        if not self.verbose:
            pass
        else:
            try:
                print args[0] % args[1], '(%s)' % time.ctime()
            except IndexError:
                print args[0], '(%s)' % time.ctime()

    def _set_nc_attrs(self):
        for attr in ('nc_start_yr', 'nc_end_yr', 'nc_dur', 'direc_nc',
                     'nc_start_month', 'nc_end_month', 'ens_mem_prefix',
                     'ens_mem_ext' 'nc_files', 'nc_dir_struc',
                     'default_yr_range'):
            attr_val = tuple([get_parent_attr(rn, attr, strict=False) for rn
                              in self.run])
            setattr(self, attr, attr_val)

    def _set_time_dt(self):
        """Get time and dt arrays at needed time indices."""
        # Use the first var in the list that is an aospy.Var object.
        nc_var = self.variables[0]
        for var in self.variables:
            if isinstance(var, Var) and not var.in_nc_grid:
                nc_var = var
                break

        with self._get_nc(nc_var, self.start_yr, self.end_yr) as nc:
            time_obj = nc.variables['time']
            inds, time = _get_time(
                time_obj[:], time_obj.units, time_obj.calendar,
                self.start_yr, self.end_yr, self.months, indices=True
            )
            self.time = time
            self.time_units = time_obj.units
            self.calendar = time_obj.calendar
            self.time_inds = inds
            self.dt = self._get_dt(nc, inds)

    def _get_dt(self, nc, indices):
        """Get durations of the desired timesteps."""
        if self.dtype_in_time == 'inst':
            return np.ones(np.shape(indices))
        else:
            for dt_name in ('average_DT',):
                try:
                    dt = nc.variables[dt_name]
                except KeyError:
                    pass
                else:
                    break
            else:
                dt = self.model[0]._get_dt()
            return dt[indices]

    def _reshape_time_indices(self, array, start_yr, end_yr):
        """Reshape time array to have year- and within-year axes.

        2015-04-23: This might not work for sub-monthly data spanning leap
        years or other calendar idiosyncracies.  For example, suppose using
        3 hourly data for DJF spanning a leap year and non leap-year.  The
        leap year February will have 4 more timesteps than the non-leap year.
        """

        reshaped = np.reshape(array, (end_yr - start_yr + 1, -1))
        return reshaped[:,:,np.newaxis,np.newaxis,np.newaxis]

    def _dir_scratch(self):
        """Create string of the data directory on the scratch filesystem."""
        ens_label = _ens_label(self.ens_mem)
        dir_scratch = '/'.join(
            ['/work', os.getenv('USER'), self.proj_str, self.model_str,
             self.run_str, ens_label, self.var.name]
        ).replace('//', '/')
        return dir_scratch

    def _dir_archive(self):
        """Create string of the data directory on the archive filesystem."""
        ens_label = _ens_label(self.ens_mem)
        dir_archive = '/'.join(
            ['/archive', os.getenv('USER'), self.proj_str, 'data',
             self.model_str, self.run_str, ens_label]
        ).replace('//', '/')
        return dir_archive

    def _file_name(self, dtype_out_time):
        """Create the name of the aospy file."""
        out_lbl = _data_out_label(self.intvl_out, dtype_out_time,
                                  dtype_vert=self.dtype_out_vert)
        in_lbl = _data_in_label(self.intvl_in, self.dtype_in_time,
                                self.dtype_in_vert)
        ens_lbl = _ens_label(self.ens_mem)
        yr_lbl = _yr_label((self.start_yr, self.end_yr))
        file_name = '.'.join(
            [self.name, out_lbl, in_lbl, self.model_str, self.run_str_full,
             ens_lbl, yr_lbl, 'p']
        ).replace('..', '.')
        return file_name

    def _get_nc_one_dir(self, name, n=0):
        """Get the names of netCDF files when all in same directory."""
        try:
            files = [self.direc_nc[n] + '/' + self.nc_files[n][name]]
        except TypeError:
            files = [self.direc_nc[n] + '/' + nc_file for
                     nc_file in self.nc_files[n][name]]
        # Remove duplicate entries.
        files = list(set(files))
        files.sort()
        return files

    def _get_nc_gfdl_dir_struct(self, name, start_yr, end_yr, n=0):
        """
        Get the names of netCDF files stored in GFDL standard directory
        structure and names.
        """
        domain = self.domain
        dtype_lbl = self.dtype_in_time
        if self.dtype_in_vert == 'sigma' and name != 'ps':
            domain += '_level'
        if self.dtype_in_time == 'inst':
            domain += '_inst'
            dtype_lbl = 'ts'
        # 2015-05-12 using 'ts' or 'inst' data only for now
        # separator = '_' if self.dtype_in_time == 'av' else '/'
        separator = '/'
        if 'av_from_' in self.dtype_in_time:
            dtype = self.dtype_in_time.replace('av_from_', '')
            dtype_lbl = dtype
        else:
            dtype = self.dtype_in_time
        direc = (self.direc_nc[n] + '/' + domain + '/' + dtype_lbl + '/' +
                 self.intvl_in + separator + str(self.nc_dur[n]) + 'yr/')
        # files_in_dir = os.listdir(direc)
        # files_var = [nc for nc in files_in_dir if name in nc]
        # yrs_regexp = '.' + start_yr + '[0-9]*-' + end_yr
        # yrs_re = [re.search(yrs_regexp, nc] for nc in files_var]
        # Assume time range is printed to
        # yr_ranges = [nc.split('.')[1] for nc in files_var]
        # files_time = [nc for nc in
        files = [direc + nc_name_gfdl(name, domain, dtype,
                                      self.intvl_in, yr, self.intvl_out,
                                      self.nc_start_yr[n], self.nc_dur[n])
                 for yr in range(start_yr, end_yr + 1)]
        # Remove duplicate entries.
        files = list(set(files))
        files.sort()
        return files

    def _get_nc(self, var, start_yr=False, end_yr=False, n=0):
        """
        Create an MFDataset for the variable spanning all desired timesteps.

        Files chosen depend on the specified variables and time intvl and the
        attributes of the netCDF files.
        """
        # Cycle through possible names.
        names = [var.name]
        if hasattr(var, 'alt_names'):
            names += list(var.alt_names)
        # Get directory and file info from the corresponding Run.
        # if n:
        # Get the data.
        for name in names:
            if self.nc_dir_struc[n] == 'one_dir':
                files = self._get_nc_one_dir(name, n=n)
            elif self.nc_dir_struc[0].lower() == 'gfdl':
                files = self._get_nc_gfdl_dir_struct(name, start_yr,
                                                     end_yr, n=n)
            try:
                # Retrieve files from archive using desired system calls.
                dmget(files)
                # hsmget_retcode = hsmget_nc(files)
                # Return netCDF4.MFDataset object containing the data.
                return netCDF4.MFDataset(files)
            except (RuntimeError, KeyError):
                pass
        else:
            raise IOError("Could not find files for variable '%s'." % var)

    def _get_pressure_vals(self, var, start_yr, end_yr, n=0):
        """Get pressure array, whether sigma or standard levels."""
        self._print_verbose("Getting pressure data: %s", var)
        if self.dtype_in_vert == 'pressure':
            if var == 'p':
                data = self.model[n].level
            elif var == 'dp':
                data = level_thickness(self.model[n].level)
            data = data[np.newaxis,:,np.newaxis,np.newaxis]
        if self.dtype_in_vert == 'sigma':
            bk = self.model[n].bk
            pk = self.model[n].pk
            ps = self._get_var_data(self.ps, start_yr, end_yr, eddy=False)
            if var == 'p':
                data = pfull_from_sigma(bk, pk, ps)
            elif var == 'dp':
                data = dp_from_sigma(bk, pk, ps)
        return data

    def _get_data_subset(self, data, region=False, eddy=False, time=False,
                         vert=False, lat=False, lon=False, n=0):
        """Subset the data array to the specified time/level/lat/lon, etc."""
        if region:
            if type(region) is str:
                data = data[region]
            elif type(region) is Region:
                data = data[region.name]
        if np.any(time):
            data = data[time]
            if 'av_from_' in self.dtype_in_time:
                data = np.mean(data, axis=0)[np.newaxis,:]
        if np.any(eddy):
            data -= np.ma.average(data, axis=0, weights=eddy)
        if np.any(vert):
            if self.dtype_in_vert != 'sigma':
                if np.max(self.model[n].level) > 1e4:
                    # Convert from Pa to hPa.
                    lev_hpa = self.model[n].level*1e-2
                else:
                    lev_hpa = self.model[n].level
                level_index = np.where(lev_hpa == self.level)
                if 'ts' in self.dtype_out_time:
                    data = np.squeeze(data[:,level_index])
                else:
                    data = np.squeeze(data[level_index])
        if np.any(lat):
            pass
        if np.any(lon):
            pass
        return data

    def _get_var_data(self, var, start_yr, end_yr, n=0, region=False,
                      eddy=False, vert=False, lat=False, lon=False):
        """Get the needed data from one aospy.Var."""
        self._print_verbose("\tGetting data from netCDF files: %s", var)
        with self._get_nc(var, start_yr, end_yr, n=n) as nc:
            # Variable names can differ.
            try:
                data = nc.variables[var.name][:]
            except KeyError:
                for alt_name in var.alt_names:
                    try:
                        data = nc.variables[alt_name][:]
                    except KeyError:
                        pass
                    else:
                        break
            time = nc.variables['time']
            t_array, t_units, t_cal = time[:], time.units, time.calendar
            t_inds = _get_time(t_array, t_units, t_cal, start_yr, end_yr,
                               self.months, indices='only')
            if eddy:
                eddy = self._get_dt(nc, t_inds)
        data = self._get_data_subset(
            data, region=region, eddy=eddy, time=t_inds,
            vert=self.level, lat=lat, lon=lon
        )
        # Interpolate data at sigma half levels to full levels.
        if self.dtype_in_vert == 'sigma' and var.def_vert == 'phalf':
            data = 0.5*(data[:,:-1] + data[:,1:])
        # if self.dtype_in_time == 'av':
            # data = self.mask_unphysical()
        # To simplify broadcasting, add dim to non-vertical data.
        if not var.def_vert:
            data = data[:,np.newaxis]
        return data

    def _get_all_vars_data(self, start_yr, end_yr, eddy=False):
        """Get the needed data from all of the vars in the calculation."""
        all_vals = []
        for n, var in enumerate(self.variables):
            # If only 1 run, use it to load all data.
            # Otherwise assume that # runs == # vars to load.
            if len(self.run) == 1:
                n = 0
            # Pressure handled specially due to complications from sigma vs. p.
            if var in ('p', 'dp'):
                data = self._get_pressure_vals(var, start_yr, end_yr)
            # Pass numerical constants as is.
            elif isinstance(var, (float, int, Constant)):
                data = var
            # aospy.Var objects remain.
            elif var.name in ('lat', 'lon', 'level', 'pk', 'bk', 'sfc_area',
                              'time'):
                # Get grid, time, etc. arrays directly from model object
                data = getattr(self.model[0], var.name)
            else:
                data = self._get_var_data(var, start_yr, end_yr,
                                          n=n, eddy=eddy)
            all_vals.append(data)
        return all_vals

    def _local_ts(self, dp, dt, num_yr, *data_in):
        """Compute the function on the given gridded input data."""
        result = self.function(*data_in)
        # Apply spatial reductions methods.
        if self.def_vert and self.dtype_out_vert == 'vert_int':
            result = int_dp_g(result, dp)[:,np.newaxis,:,:]
        # If already averaged, pass data on.  Otherwise do time averaging.
        if 'av' in self.dtype_in_time or not self.def_time:
            return result
        try:
            result = result.reshape((num_yr, -1, result.shape[-3],
                                     result.shape[-2], result.shape[-1]))
        except ValueError:
            result = result.reshape((num_yr, -1, result.shape[-2],
                                     result.shape[-1]))
        # Average within each year, yielding a yearly time-series.
        try:
            return np.ma.multiply(result, dt).sum(axis=1) / dt.sum(axis=1)
        except ValueError:
            dt = dt[:,:,:,:,0]
            return np.ma.multiply(result, dt).sum(axis=1) / dt.sum(axis=1)

    def _time_reduce(self, loc_ts):
        """Compute all desired calculations on a local time-series."""
        files = {}
        if 'ts' in self.dtype_out_time:
            files.update({'ts': loc_ts})
        if 'None' in self.dtype_out_time:
            # Some calcs (e.g. correlations) already do time reduction.
            files.update({'av': loc_ts})
        if 'av' in self.dtype_out_time:
            files.update({'av': loc_ts.mean(axis=0)})
        if 'eddy.av' in self.dtype_out_time:
            files.update({'eddy.av': loc_ts.mean(axis=0)})
        if 'std' in self.dtype_out_time:
            files.update({'std': loc_ts.std(axis=0)})
        if 'eddy.std' in self.dtype_out_time:
            files.update({'eddy.std': loc_ts.std(axis=0)})
        # Zonal asymmetry.
        if any('zasym' in out_type for out_type in self.dtype_out_time):
            # '.T'=transpose; makes numpy broadcasting syntax work.
            znl_ts = loc_ts.mean(axis=-1)
            zasym_ts = (loc_ts.T - znl_ts.T).T
            if 'zasym.ts' in self.dtype_out_time:
                files.update({'zasym.ts': zasym_ts})
            if 'zasym.av' in self.dtype_out_time:
                files.update({'zasym.av': zasym_ts.mean(axis=0)})
            if 'zasym.std' in self.dtype_out_time:
                files.update({'zasym.std': zasym_ts.std(axis=0)})
        # Zonal mean.
        if any('znl' in out_type for out_type in self.dtype_out_time):
            if 'znl.ts' in self.dtype_out_time:
                files.update({'znl.ts': znl_ts})
            if 'znl.av' in self.dtype_out_time:
                files.update({'znl.av': znl_ts.mean(axis=0)})
            if 'znl.std' in self.dtype_out_time:
                files.update({'znl.std': znl_ts.std(axis=0)})
        return files

    def region_calcs(self, loc_ts, eddy=False, n=0):
        """Region-averaged computations.  Execute and save to external file."""
        calcs_reg = ('ts', 'av', 'std')
        # Perform each calculation for each region.
        for calc in calcs_reg:
            calc_name = ('reg.' + calc)
            if eddy:
                calc_name = '.'.join(['eddy', calc_name])
            if calc_name in self.dtype_out_time:
                reg_dat = {}
                for reg in self.region.itervalues():
                    # Just pass along the data if averaged already.
                    if 'av' in self.dtype_in_time:
                        data_out = reg.ts(loc_ts, self.model[n])
                    # Otherwise perform the calculation.
                    else:
                        method = getattr(reg, calc)
                        data_out = method(loc_ts, self.model[n])
                    reg_dat.update({reg.name: data_out})
                self.save(reg_dat, calc_name)

    def _compute_chunk(self, start_yr, end_yr, eddy=False):
        """Perform the calculation on the given chunk of times."""
        self._print_verbose("\nComputing desired timeseries from netCDF data "
                            "for years %d-%d.", (start_yr, end_yr))
        inds = _get_time(
            self.time, self.time_units, self.calendar,
            start_yr, end_yr, self.months, indices='only'
        )
        dt = self.dt[inds]
        dt = self._reshape_time_indices(dt, start_yr, end_yr)
        data_in = self._get_all_vars_data(start_yr, end_yr, eddy=eddy)
        if self.dtype_out_vert == 'vert_int':
            dp = self._get_pressure_vals('dp', start_yr, end_yr)
        else:
            dp = False
        return self._local_ts(dp, dt, end_yr - start_yr + 1, *data_in)

    def compute(self, eddy=False):
        """Perform all desired calculations on the data and save externally."""
        # Compute the local time series for each chunk and then combine chunks.
        if all(['eddy' in do for do in self.dtype_out_time]) and eddy is False:
            self._print_verbose("Computing and saving eddy outputs.")
            eddy = True
        full_ts = [self._compute_chunk(start_yr, end_yr, eddy=eddy)
                   for start_yr, end_yr in self.chunk_ranges]
        if len(full_ts) == 1:
            full_ts = full_ts[0]
        else:
            self._print_verbose("Combining output data from all time chunks.")
            full_ts = np.ma.concatenate(full_ts, axis=0)
        # Apply time reduction methods on gridded data and save.
        self._print_verbose("Applying desired time-reduction methods.")
        if self.def_time:
            reduced = self._time_reduce(full_ts)
        else:
            reduced = {'': full_ts}
        self._print_verbose("Writing desired gridded outputs to disk.")
        for dtype_out_time, data in reduced.iteritems():
            self.save(np.squeeze(data), dtype_out_time,
                      dtype_out_vert=self.dtype_out_vert)
        # Apply time reduction methods to regional averages and save.
        if any(['reg' in do for do in self.dtype_out_time]) and self.region:
            self._print_verbose("Computing and saving regional outputs.")
            self.region_calcs(full_ts, eddy=eddy)
        # Perfom eddy computations.
        if any(['eddy' in do for do in self.dtype_out_time]) and eddy is False:
            self._print_verbose("Computing and saving eddy outputs.")
            self.compute(eddy=True)

    def _save_to_scratch(self, data, dtype_out_time, dtype_out_vert=False):
        """Save the data to the scratch filesystem."""
        path = self.path_scratch[dtype_out_time]
        if not os.path.isdir(self.dir_scratch):
            os.makedirs(self.dir_scratch)
        with open(path, 'a+') as file_scratch:
            # Update, rather than overwrite, existing regional data.
            if 'reg' in dtype_out_time:
                # Open the existing dictionary if it exists.
                try:
                    reg_data = cPickle.load(file_scratch)
                except EOFError:
                    reg_data = {}
                # Add the new data to the dictionary.
                reg_data.update(data)
                data_out = reg_data
            else:
                data_out = data
        with open(path, 'w') as file_scratch:
            cPickle.dump(data_out, file_scratch, protocol=-1)

    def _save_to_archive(self, dtype_out_time, dtype_out_vert=False):
        """Add the data to the tar file in /archive."""
        if not os.path.isdir(self.dir_archive):
            os.makedirs(self.dir_archive)
        # tarfile 'append' mode won't overwrite the old file, which we want.
        # So open in 'read' mode, extract the file, and then delete it.
        # But 'read' mode throws OSError if file doesn't exist: make it first.
        dmget([self.path_archive])
        # SAH 201-08-27: Within the last few weeks, both of the 'with' blocks
        # below are causing frequent hangups when trying to save to archive
        # for the first time during a shell session.  But then if I Ctrl-C to
        # kill the job and then restart, the hangup goes away.  Don't know
        # why it started happening all of a sudden.
        with tarfile.open(self.path_archive, 'a') as tar:
            pass
        with tarfile.open(self.path_archive, 'r') as tar:
            try:
                old_data_path = '/'.join(
                    [self.dir_archive, self.file_name[dtype_out_time]]
                ).replace('//', '/')

                tar.extract(self.file_name[dtype_out_time],
                            path=old_data_path)
            except KeyError:
                pass
            else:
                # The os module treats files on archive as non-empty
                # directories, so can't use os.remove or os.rmdir.
                shutil.rmtree(old_data_path)
                subprocess.call([
                    "tar", "--delete", "--file=%s" % self.path_archive,
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
            self._save_to_scratch(data, dtype_out_time,
                                  dtype_out_vert=dtype_out_vert)
        if archive:
            self._save_to_archive(dtype_out_time,
                                  dtype_out_vert=dtype_out_vert)
        print '\t%s' % self.path_scratch[dtype_out_time]

    def _load_from_scratch(self, dtype_out_time, dtype_out_vert=False):
        """Load aospy data saved on scratch file system."""
        with open(self.path_scratch[dtype_out_time], 'r') as data:
            data_vals = cPickle.load(data)
        return data_vals

    def _load_from_archive(self, dtype_out_time, dtype_out_vert=False):
        """Load data save in tarball on archive file system."""
        path = '/'.join([self.dir_archive, 'data.tar']).replace('//', '/')
        dmget([path])
        with tarfile.open(path, 'r') as data_tar:
            data_vals = cPickle.load(
                data_tar.extractfile(self.file_name[dtype_out_time])
            )
        return data_vals

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
            except OSError:
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
