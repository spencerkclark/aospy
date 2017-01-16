"""Functionality for storing attributes of a model run or obs product."""
from .utils.times import datetime_or_default


class Run(object):
    """Model run parameters."""
    def __init__(self, name=None, description=None, proj=None,
                 default_start_date=None,
                 default_end_date=None, tags=None,
                 data_loader=None):
        """Instantiate a `Run` object."""
        self.name = '' if name is None else name
        self.description = '' if description is None else description
        self.proj = proj

        try:
            self.default_start_date = datetime_or_default(
                default_start_date, data_loader.data_start_date)
            self.default_end_date = datetime_or_default(
                default_end_date, data_loader.data_end_date)
        except AttributeError:
            self.default_start_date = datetime_or_default(default_start_date,
                                                          default_start_date)
            self.default_end_date = datetime_or_default(default_end_date,
                                                        default_end_date)

        self.tags = [] if tags is None else tags

        self.data_loader = data_loader

    def __str__(self):
        return 'Run instance "%s"' % self.name

    __repr__ = __str__
