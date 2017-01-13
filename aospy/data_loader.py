"""aospy DataLoader objects"""
import os

import numpy as np
import xarray as xr
from glob import glob

from . import internal_names
from .utils import times, io

_TIME_SHIFT_ATTRS = ['shift_{}'.format(intvl) for intvl in
                     ['years', 'months', 'days', 'hours']]


class DataLoader(object):
    """A fundamental DataLoader object"""
    def load_variable(self, var=None, start_date=None, end_date=None,
                      **DataAttrs):
        """Return a DataArray with requested variable, given time range,
        and input interval.

        This function automatically renames all grid attributes to match
        aospy conventions.

        Parameters
        ----------
        var : Var
            aospy Var object
        start_date : netCDF4.netcdftime or np.datetime64
            start date for interval
        end_date : netCDF4.netcdftime or np.datetime64
            end date for interval
        **DataAttrs
            Attributes needed to identify a unique set of files to load from

        Returns
        -------
        da : DataArray
             DataArray for the specified variable, date range, and interval in
        """
        file_set = self._generate_file_set(var=var, start_date=start_date,
                                           end_date=end_date, **DataAttrs)
        ds = self._load_data_from_disk(file_set)
        ds = self._prep_time_data(ds)
        ds = self.set_grid_attrs_as_coords(ds)  # Tested
        da = self._sel_var(ds, var)  # Tested

        # Apply correction before selecting time range.
        # Note that time shifts are a property of a particular list of files
        # NOT an entire DataLoader, so there needs to be a way to specify
        # those on a file list by file list basis.

        # TODO
        # da = self._maybe_apply_time_shift(self, da, **DataAttrs)
        start_date_xarray = times.numpy_datetime_range_workaround(start_date)
        end_date_xarray = start_date_xarray + (end_date - start_date)
        return times.sel_time(da, np.datetime64(start_date_xarray),
                              np.datetime64(end_date_xarray)).load()

    def _maybe_apply_time_shift(self, da, **DataAttrs):
        """Apply specified time shift"""
        # TODO
        pass

    @classmethod
    def _load_data_from_disk(cls, file_set):
        """Load a Dataset from a list of files, concatenating along time,
        and rename all grid attributes to their aospy internal names.

        Parameters
        ----------
        file_set : list
            List of paths to files

        Returns
        -------
        Dataset
        """
        return xr.open_mfdataset(file_set, preprocess=cls.rename_grid_attrs,
                                 concat_dim=internal_names.TIME_STR,
                                 decode_cf=False)

    @staticmethod
    def _prep_time_data(ds):
        """Prepare time coordinate information in Dataset for use in
        aospy.

        1. Edit units attribute of time variable if it contains
        a Timestamp invalid date
        2. If the Dataset contains a time bounds coordinate, add
        attributes representing the true beginning and end dates of
        the time interval used to construct the Dataset
        3. Decode the times into np.datetime64 objects for time
        indexing

        Parameters
        ----------
        ds : Dataset
            Pre-processed Dataset with time coordinate renamed to
            internal_names.TIME_STR

        Returns
        -------
        Dataset
        """
        # ds = times.enforce_valid_timestamp_date_range(ds)
        ds = times.numpy_datetime_workaround_encode_cf(ds)
        if internal_names.TIME_BOUNDS_STR in ds:
            ds = times.set_average_dt_metadata(ds)
        ds = xr.decode_cf(
            ds, decode_times=True, decode_coords=False, mask_and_scale=False
        )
        return ds

    @staticmethod
    def _sel_var(ds, var):
        """Search a Dataset for the specified variable, trying all possible
        alternative names.

        Parameters
        ----------
        ds : Dataset
            Dataset possibly containing var
        var : aospy.Var
            Variable to find data for

        Returns
        -------
        DataArray

        Raises
        ------
        KeyError
             If the variable is not in the Dataset
        """
        for name in var.names:
            try:
                da = ds[name]
                return da.rename({name: var.name})
            except KeyError:
                pass
        raise KeyError('{0} not found in '
                       'among names:{1} in {2}'.format(var, var.names, ds))

    @staticmethod
    def rename_grid_attrs(ds):
        """Rename existing grid attributes to be consistent with
        aospy conventions.

        This function does not compare to Model coordinates or
        add missing coordinates from Model objects.  Grid attributes
        are set as coordinates, such that they are carried by all
        selected DataArrays with overlapping index dimensions.

        Parameters
        ----------
        ds : Dataset

        Returns
        -------
        renamed : Dataset
            Dataset returned with coordinates consistent with aospy
            conventions
        """
        for name_int, names_ext in internal_names.GRID_ATTRS.items():
            ds_coord_name = set(names_ext).intersection(set(ds.coords) |
                                                        set(ds.data_vars))
            if ds_coord_name:
                ds.rename({ds_coord_name.pop(): name_int}, inplace=True)
        return ds

    @staticmethod
    def set_grid_attrs_as_coords(ds):
        """Set available grid attributes as coordinates in a given Dataset.

        Grid attributes are assumed to have their internal aospy names.

        Parameters
        ----------
        ds : Dataset
            Input data

        Returns
        -------
        Dataset
            Dataset with grid attributes set as coordinates
        """
        int_names = internal_names.GRID_ATTRS.keys()
        grid_attrs_in_ds = set(int_names).intersection(set(ds.coords) |
                                                       set(ds.data_vars))
        ds.set_coords(grid_attrs_in_ds, inplace=True)
        return ds

    def _generate_file_set(self, var=None, start_date=None, end_date=None,
                           domain=None, intvl_in=None, dtype_in_vert=None,
                           dtype_in_time=None, intvl_out=None):
        raise NotImplementedError(
            'All DataLoaders require a _generate_file_set method')


class DictDataLoader(DataLoader):
    """A data loader that corresponds with a dictionary mapping lists of files
    to interval in tags.
    """
    def __init__(self, file_map=None):
        """Create a new `DictDataLoader`

        Parameters
        ----------
        file_map : dict
            A dict mapping an input interval to a list of files
        """
        self.file_map = file_map

    def _generate_file_set(self, var=None, start_date=None, end_date=None,
                           domain=None, intvl_in=None, dtype_in_vert=None,
                           dtype_in_time=None, intvl_out=None):
        """Returns the file_set for the given interval in."""
        try:
            return self.file_map[intvl_in]
        except KeyError:
            raise KeyError('File set does not exist for the specified'
                           ' intvl_in {0}'.format(intvl_in))


class OneDirDataLoader(DataLoader):
    """A data loader that locates files based on a dictionary mapping of
    variables to filesets."""
    def __init__(self, file_map=None):
        """Create a new `OneDirDataLoader`

        Parameters
        ----------
        file_map : dict
            A dict mapping intvl_in to dictionaries mapping Var
            objects to lists of files
        """
        self.file_map = file_map

    def _generate_file_set(self, var=None, start_date=None, end_date=None,
                           domain=None, intvl_in=None, dtype_in_vert=None,
                           dtype_in_time=None, intvl_out=None):
        for name in var.names:
            try:
                return self.file_map[intvl_in][name]
            except KeyError:
                pass
        raise KeyError('Files for the var {0} cannot be found in for the '
                       'intvl_in {1} in this'
                       ' OneDirDataLoader'.format(var, intvl_in))


class GFDLDataLoader(DataLoader):
    """A data loader that locates files based on GFDL post-processing naming
    conventions.
    """
    def __init__(self, data_direc=None, data_dur=None, data_start_date=None,
                 data_end_date=None):
        """Create a new `GFDLDataLoader`

        Parameters
        ----------
        data_direc : str
            Root directory of data files
        data_dur : int
            Number of years included per post-processed file
        data_start_date : datetime.datetime
            Start date of data files
        data_end_date : datetime.datetime
            End date of data files
        """
        self.data_dur = data_dur
        self.data_direc = data_direc
        self.data_start_date = data_start_date
        self.data_end_date = data_end_date

    def _generate_file_set(self, var=None, start_date=None, end_date=None,
                           domain=None, intvl_in=None, dtype_in_vert=None,
                           dtype_in_time=None, intvl_out=None):
        for name in var.names:
            file_set = self._input_data_paths_gfdl(
                name, start_date, end_date, domain, intvl_in, dtype_in_vert,
                dtype_in_time, intvl_out)
            if glob(file_set):
                return file_set
        raise IOError('Files for the var {0} cannot be located'
                      'using GFDL post-processing conventions'.format(var))

    def _input_data_paths_gfdl(self, name, start_date, end_date, domain,
                               intvl_in, dtype_in_vert, dtype_in_time,
                               intvl_out):
        dtype_lbl = dtype_in_time
        if intvl_in == 'daily':
            domain += '_daily'
        if dtype_in_vert == internal_names.ETA_STR and name != 'ps':
            domain += '_level'
        if dtype_in_time == 'inst':
            domain += '_inst'
            dtype_lbl = 'ts'
        if 'monthly_from_' in dtype_in_time:
            dtype = dtype_in_time.replace('monthly_from_', '')
            dtype_lbl = dtype
        else:
            dtype = dtype_in_time
        dur_str = str(self.data_dur) + 'yr'
        if dtype_in_time == 'av':
            subdir = intvl_in + '_' + dur_str
        else:
            subdir = os.path.join(intvl_in, dur_str)
        direc = os.path.join(self.data_direc, domain, dtype_lbl, subdir)
        files = [os.path.join(direc, io.data_name_gfdl(
                    name, domain, dtype, intvl_in, year, intvl_out,
                    self.data_start_date.year, self.data_in_dur))
                 for year in range(start_date.year, end_date.year + 1)]
        files = list(set(files))
        files.sort()
        return files
