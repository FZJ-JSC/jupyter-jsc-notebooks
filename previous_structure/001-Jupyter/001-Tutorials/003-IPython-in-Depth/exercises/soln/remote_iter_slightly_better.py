import ipyparallel

class remote_iterator:
    """Return an iterator on an object living on a remote engine."""
    def __init__(self, view, name):
        self.view = view
        self.name = name

    def __iter__(self):
        return self

    def __next__(self):
        it_name = '_%s_iter' % self.name
        self.view.execute('%s = iter(%s)' % (it_name, self.name), block=True)
        next_ref = ipyparallel.Reference(it_name + '.next')
        while True:
            try:
                yield self.view.apply_sync(next_ref)
            # This causes the StopIteration exception to be raised.
            except ipyparallel.RemoteError as e:
                if e.ename == 'StopIteration':
                    raise StopIteration
                else:
                    raise e
