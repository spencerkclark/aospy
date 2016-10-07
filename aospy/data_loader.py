"""aospy DataLoader objects"""
import xarray as xr
from glob import glob

from . import internal_names
from .utils import times

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
        file_set = self._generate_file_set(var, start_date, end_date,
                                           **DataAttrs)
        ds = self._load_data_from_disk(file_set)
        ds = self._prep_time_data(ds)
        ds = self.set_grid_attrs_as_coords(ds)  # Tested
        da = self._sel_var(ds, var)  # Tested

        # Apply correction before selecting time range.
        # Note that time shifts are a property of a particular list of files
        # NOT an entire DataLoader, so there needs to be a way to specify
        # those on a file list by file list basis.
        da = self._maybe_apply_time_shift(self, da, **DataAttrs)

        return times.sel_time(da, start_date, end_date).load()

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
        ds = times.enforce_valid_timestamp_date_range(ds)
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

    def _generate_file_set(self, var, start_date, end_date, intvl_in, vert_in):
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

    def _generate_file_set(self, var, start_date, end_date, intvl_in, vert_in):
        """Returns the file_set for the given interval in."""
        return self.file_map[intvl_in]


class GFDLDataLoader(DataLoader):
    """A data loader that locates files based on GFDL post-processing naming
    conventions.
    """
    def __init__(self, data_in_dur=None):
        """Create a new `GFDLDataLoader`"""
        self.data_in_dur = data_in_dur

    def _generate_file_set(self, var, start_date, end_date, intvl_in, vert_in):
        for name in var.names:
            file_set = self._input_data_paths_gfdl()
            if glob(file_set):
                return file_set
        raise IOError('Files for the var {0} cannot be located'
                      'using GFDL postprocessing conventions'.format(var))

    def _input_data_paths_gfdl():
        pass
