"""asopy DataLoader objects"""
import xarray as xr

from .__config__ import TIME_STR, AVERAGE_T1_STR, AVERAGE_T2_STR, GRID_ATTRS


class DataLoader(object):
    """A fundamental DataLoader object"""
    def load_variable(self, var=None, start_date=None, end_date=None,
                      intvl_in=None):
        """Returns the DataArray with requested variable, given time range,
        and input interval.

        Automatically renames all grid attributes to match aospy conventions.

        Parameters
        ----------
        var : Var
             aospy Var object
        start_date : netCDF4.netcdftime or np.datetime64
             start date for interval
        end_date : netCDF4.netcdftime or np.datetime64
             end date for interval
        intvl_in : str
             interval coding (e.g. 'monthly')

        Returns
        -------
        da : DataArray
             DataArray for the specified variable, date range, and interval in
        """
        file_set = self._generate_file_set(var, start_date, end_date, intvl_in)
        da = self._sel_var(file_set, var)
        return self._sel_time(da, start_date, end_date).load()

    def _sel_var(self, file_set, var):
        """Returns a DataArray for the requested variable from a set of files.

        This function returns the result of a call to xr.open_mfdataset, which
        returns a lazy version of the data (i.e. not loaded into memory). It
        renames all grid attributes to be consistent with aospy conventions.

        Parameters
        ----------
        file_set : list
            list of file paths for xr.open_mfdataset
        var : aospy.Var
            variable to find data for

        Returns
        -------
        da : DataArray
            DataArray with full time series of data

        Raises
        ------
        KeyError
             if a listed variable name is not in the file_set
        """
        ds = xr.open_mfdataset(file_set, preprocess=self.establish_grid_attrs,
                               concat_dim=TIME_STR)
        for name in var.names:
            try:
                da = ds[name]
                return da.rename({name: var.name})
            except KeyError:
                pass
        raise KeyError('{0} not found in '
                       'specified files {1}'.format(var, file_set))

    def _sel_time(self, da, start_date, end_date):
        """Subset a DataArray or Dataset for a given date range.  Ensures
        that data are present for full extend of requested range.

        Parameters
        ----------
        da : DataArray or Dataset
            data to subset
        start_date : np.datetime64
            start of date interval
        end_date : np.datetime64
            end of date interval

        Returns
        ----------
        da : DataArray or Dataset
            subsetted data

        Raises
        ------
        AssertionError
            if data for requested range do not exist for part or all of
            requested range
        """
        self._assert_has_data_for_time(da, start_date, end_date)
        return da.sel(**{TIME_STR: slice(start_date, end_date)})

    @staticmethod
    def establish_grid_attrs(ds):
        """Renames existing grid attributes to be consistent with
        aospy conventions.  Does not compare to Model coordinates or
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
        for name_int, names_ext in GRID_ATTRS.items():
            ds_coord_name = set(names_ext).intersection(set(ds.coords) |
                                                        set(ds.data_vars))
            if ds_coord_name:
                ds.rename({ds_coord_name.pop(): name_int}, inplace=True)
                ds.set_coords(name_int, inplace=True)
        return ds

    @staticmethod
    def _assert_has_data_for_time(da, start_date, end_date):
        """Checks to make sure data is in Dataset for the given time range.

        Parameters
        ----------
        da : DataArray
             DataArray with a time variable
        start_date : netCDF4.netcdftime or np.datetime64
             start date
        end_date : netCDF4.netcdftime or np.datetime64
             end date

        Raises
        ------
        AssertionError
             if the time range is not within the time range of the DataArray
        """
        # Accomdate time-average intervals with time_bounds coordinates
        if AVERAGE_T1_STR in da:
            da_start = da[AVERAGE_T1_STR].isel(**{TIME_STR: 0}).values
            da_end = da[AVERAGE_T2_STR].isel(**{TIME_STR: -1}).values
        else:
            da_start, da_end = da.time.isel(**{TIME_STR: [0, -1]}).values
        message = 'Data do not exist for requested time range: {0} to {1}'
        range_exists = start_date >= da_start and end_date <= da_end
        assert (range_exists), message.format(start_date, end_date)

    def _generate_file_set(self, var, start_date, end_date, intvl_in):
        raise NotImplementedError(
            'All DataLoaders require a _generate_file_set method')


class DictDataLoader(DataLoader):
    """A data loader that corresponds with a dictionary mapping lists of files
    to interval in tags.
    """
    def __init__(self, file_map={}):
        """Instantiates a new `DictDataLoader`

        Parameters
        ----------
        file_map : dict
            A dict mapping an input interval to a list of files
        """
        self.file_map = file_map

    def _generate_file_set(self, var, start_date, end_date, intvl_in):
        """Returns the file_set for the given interval in."""
        return self.file_map[intvl_in]


class GFDLDataLoader(DataLoader):
    """A data loader that locates files based on GFDL post-processing naming
    conventions.
    """
    def __init__(self, *args):
        pass

    def _generate_file_set(self, var, start_date, end_date, intvl_in):
        pass
