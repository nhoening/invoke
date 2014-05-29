import itertools

from .context import Context
from .util import debug
from .tasks import Call

from .vendor import six


class Executor(object):
    """
    An execution strategy for Task objects.

    Subclasses may override various extension points to change, add or remove
    behavior.
    """
    def __init__(self, collection, context=None):
        """
        Initialize executor with handles to a task collection & config context.

        The collection is used for looking up tasks by name and
        storing/retrieving state, e.g. how many times a given task has been
        run this session and so on. It is optional; if not given a blank
        `~invoke.context.Context` is used.

        A copy of the context is passed into any tasks that mark themselves as
        requiring one for operation.
        """
        self.collection = collection
        self.context = context or Context()

    def execute(self, *tasks, **kwargs):
        """
        Execute one or more ``tasks`` in sequence.

        :param iterable tasks:
            An iterable of two-tuples whose first element is a task name and
            whose second element is a dict suitable for use as ``**kwargs``.
            E.g.::

                [
                    ('task1', {}),
                    ('task2', {'arg1': 'val1'}),
                    ...
                ]

            As a shorthand, a string instead of a two-tuple may be given,
            implying an empty kwargs dict.

            The string specifies which task from the Executor's `.Collection`
            is to be executed. It may contain dotted syntax appropriate for
            calling namespaced tasks, e.g. ``subcollection.taskname``.

            Thus the above list-of-tuples is roughly equivalent to::

                task1()
                task2(arg1='val1')

        :param bool dedupe:
            Whether to perform deduplication on the tasks and their
            pre/post-tasks. See :ref:`deduping`.

        :returns:
            A dict mapping task objects to their return values. This may
            include pre- and post-tasks if any were executed.
        """
        # Handle top level kwargs (the name gets overwritten below)
        dedupe = kwargs.get('dedupe', True)
        # Normalize to two-tuples
        debug("Examining top level tasks {0!r}".format(
            [x[0] for x in tasks]
        ))
        tasks = [(x, {}) if isinstance(x, basestring) else x for x in tasks]
        debug("Tasks with kwargs: {0!r}".format(tasks))
        # Then to call objects (binding the task obj + kwargs together)
        tasks = [
            Call(self.collection[name], **kwargs)
            for name, kwargs in tasks
        ]
        # Expand pre/post tasks
        # TODO: post-tasks
        tasks = self.expand_tasks(tasks)
        # Dedupe if desired
        if dedupe: # Python 2 can't do *args + kwarg
            deduped = []
            for task in tasks:
                if task not in deduped:
                    deduped.append(task)
        else:
            deduped = tasks
        # Execute
        results = {}
        for task in deduped:
            args, kwargs = tuple(), {}
            if isinstance(task, Call):
                c = task
                task = c.task
                args, kwargs = c.args, c.kwargs
            # TODO: figure out how to preserve top-level tasks' given names
            result = self._execute(
                task=task, name=name, args=args, kwargs=kwargs
            )
            # TODO: handle the non-dedupe case / the same-task-different-args
            # case, wherein one task obj maps to >1 result.
            results[task] = result
        return results

    def _execute(self, task, name, args, kwargs):
        # Need task + possible name when invoking CLI-given tasks, so we can
        # pass a dotted path to Collection.configuration()
        debug("Executing %r%s" % (task, (" as %s" % name) if name else ""))
        if task.contextualized:
            context = self.context.clone()
            context.update(self.collection.configuration(name))
            args = (context,) + args
        return task(*args, **kwargs)

    def expand_tasks(self, tasks):
        """
        Recursively expand `.Task`/`.Call` objects with their pre/post tasks.

        :param iterable tasks:
            An iterable containing `.Task` or `.Call` objects.

        :returns:
            A `list` of `.Task` (or `.Call`, if any were passed in) objects.
        """
        ret = []
        for task in tasks:
            ret.extend(self.expand_tasks(task.pre))
            ret.append(task)
            # TODO: ret.extend(expand_tasks(tasks.post))
        return ret
