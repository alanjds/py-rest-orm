from pyrestorm.client import RestClient


class RestQueryset(object):
    '''
    Wrapper for 'evaluating' API results. Provides access like a list/queryset.
    The cases where evaluation will occur is:
        1) Iteration
        2) Index Access/Slicing
        3) Length/Counting
    '''
    def __init__(self, model, *args, **kwargs):
        # How many records to we have in the _data cache
        self._count = 0
        # Has the query changed since results were last retrieved?
        self._stale = True
        # Local cache of API objects
        self._data = []
        # What RestModel does this queryset belong to?
        self.model = model
        # Paginator instance for assisted navigation logic with API
        if hasattr(model, 'paginator_class'):
            self._paginator = model.paginator_class()
        # REST Client for performing API calls
        self.client = RestClient()

    # 1) Iteration
    def __iter__(self):
        return iter(self._evaluate())

    # 2) Index Access/Slicing
    def __getitem__(self, value):
        # If we are getting a slice, only get part of the queryset
        if isinstance(value, slice):
            self._evaluate(value.start, value.stop)
        # If it is a single element, fetch just that
        elif isinstance(value, int):
            self._data = self._evaluate(value, value + 1)[0]
        # Otherwise we want the unbounded results
        else:
            self._evaluate()

        return self._data

    # 3) Length/Counting
    def __len__(self):
        return len(self._evaluate())

    def _fetch(self):
        # Only perform a query if the data is stale
        if self._stale:
            response = self.client.get(self.model.url)
            self._data = [self.model(data=item) for item in response]
            self._count = len(self._data)
            self._stale = False
        return self._data

    def _fetch_pages(self, start, end):
        # Move the paginator to the beginning of the segment of interest
        self._paginator.cursor(start)

        # Only perform a query if the data is stale
        if self._stale:
            # Naive data reset, we can only cache for the current query
            self._data = []
            self._count = 0

            # While we don't have all the data we need, fetch
            self._paginator.cursor(start)
            fetch = True
            while fetch:
                # Retrieve data from the server
                response = self.client.get('%s?%s' % (self.model.url, self._paginator.as_url()))

                # Attempt to grab the size of the dataset from the usual place
                self._paginator.max = response.get('count', None)

                # Count how many record were retrieved in this round
                count = len(response['results'])

                # Extend the dataset with the new records
                self._data.extend([self.model(data=item) for item in response['results']])

                # Increment the number of records we currently have in the queryset
                self._count += count

                # Determine if we need to grab another round of records
                fetch = self._paginator.next(retrieved=count) if end is None else self._count < (end - start)

            # Data is up-to-date
            self._stale = False
        return self._data

    # Performs 'evaluation' by querying the API and bind the results into an array
    def _evaluate(self, start=0, end=None):
        # Using paginated results
        if hasattr(self, '_paginator'):
            end = self._paginator.max if end is None else end
            # Check for valid usage
            if end is not None and start >= end:
                raise ValueError('`start` cannot be greater than or equal to `end`')
            elif self._paginator.max is not None and end >= self._paginator.max:
                raise ValueError('`end` cannot be greater than or equal to the maximum number of records')

            return self._fetch_pages(start, end)

        # Returns unpaginated results
        return self._fetch()
