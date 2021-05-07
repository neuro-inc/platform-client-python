.. _jobs-reference:

==================
Jobs API Reference
==================


.. currentmodule:: neuro_sdk


Jobs
====

.. class:: Jobs

   Jobs subsystem, available as :attr:`Client.jobs`.

   User can start new job, terminate it, get status, list running jobs etc.

   .. comethod:: attach(id: str, *, \
                      stdin: bool = False, \
                      stdout: bool = False, \
                      stderr: bool = False, \
                      cluster_name: Optional[str] = None, \
                 ) -> AsyncContextManager[StdStream]
      :async-with:

      Get access to standard input, output, and error streams of a running job.

      :param str id: job :attr:`~JobDescription.id` to use for command execution.

      :param bool stdin: ``True`` to attach stdin, default is ``False``.

      :param bool stdout: ``True`` to attach stdout, default is ``False``.

      :param bool stderr: ``True`` to attach stderr, default is ``False``.

      :param str cluster_name: cluster on which the job is running.

                               ``None`` means the current cluster (default).

      :return: Asynchronous context manager which can be used to access
               stdin/stdout/stderr, see :class:`StdStream` for details.

   .. comethod:: exec_create(id: str, cmd: List[str], *, \
                      tty: bool = False, \
                      cluster_name: Optional[str] = None, \
                 ) -> str

      Create an exec session to run a command in a running job.

      :param str id: job :attr:`~JobDescription.id` to use for command execution.

      :param ~typing.Iterable[str] cmd: the command to execute, a sequence of
                                        :class:`str`, e.g. :class:`list` of strings.

      :param bool tty: ``True`` if :term:`tty` mode is requested, default is
                       ``False``.

      :param str cluster_name: cluster on which the job is running.

                               ``None`` means the current cluster (default).

      :return: Exec session id (:class:`str`).

   .. comethod:: exec_inspect(id: str, exec_id: str, *. \
                              cluster_name: Optional[str] = None, \
                 ) -> ExecInspect

      Get exec session info.

      :param str id: job :attr:`~JobDescription.id`.

      :param str exec_id: exec id.

      :return: Exec session info, :class:`ExecInspect` instance.

   .. comethod:: exec_resize(id: str, exec_id: str, *, w: int, h: int) -> None

      Resize created TTY exec session.

      :param str id: job :attr:`~JobDescription.id`.

      :param str exec_id: exec id.

      :param int w: New screen width.

      :param int h: New screen height.

      :param str cluster_name: cluster on which the job is running.

                               ``None`` means the current cluster (default).

   .. comethod:: exec_start(id: str, exec_id: str, *, \
                            cluster_name: Optional[str] = None, \
                 ) -> StdStream
      :async-with:

      Start an exec session, get access to session's stdin/stdout/stderr.

      :param str id: job :attr:`~JobDescription.id`.

      :param str exec_id: exec id.

      :param str cluster_name: cluster on which the job is running.

                               ``None`` means the current cluster (default).

      :return: Asynchronous context manager which can be used to access
               stdin/stdout/stderr, see :class:`StdStream` for details.

   .. comethod:: get_capacity(*, \
                             cluster_name: Optional[str] = None, \
                 ) -> Mapping[str, int]

      Get counts of available job for specified cluster for each available preset.

      The returned numbers reflect the remaining *cluster capacity*. In other words, it
      displays how many concurrent jobs for each preset can be started at the moment of
      the method call.

      The returned capacity is an approximation, the real value can differ if already
      running jobs are finished or another user starts own jobs at the same time.

      :param str cluster_name: cluster for which the request is performed.

                               ``None`` means the current cluster (default).

      :return: A mapping of *preset_name* to *count*, where *count* is a number of
               concurrent jobs that can be executed using *preset_name*.

   .. comethod:: kill(id: str) -> None

      Kill a job.

      :param str id: job :attr:`~JobDescription.id` to kill.

   .. comethod:: list(*, statuses: Iterable[JobStatus] = (), \
                      name: Optional[str] = None, \
                      tags: Sequence[str] = (), \
                      owners: Iterable[str] = (), \
                      since: Optional[datetime] = None, \
                      until: Optional[datetime] = None, \
                      reverse: bool = False, \
                      limit: Optional[int] = None, \
                      cluster_name: Optional[str] = None, \
                 ) -> AsyncIterator[JobDescription]
      :async-for:

      List user jobs, all scheduled, running and finished jobs by default.

      :param ~typing.Iterable[JobStatus] statuses: filter jobs by their statuses.

                                                   The parameter can be a set or list of
                                                   requested statuses,
                                                   e.g. ``{JobStatus.PENDIND,
                                                   JobStatus.RUNNING}`` can be used for
                                                   requesting only scheduled and running
                                                   job but skip finished and failed
                                                   ones.

                                                   Empty sequence means that jobs with
                                                   all statuses are returned (default
                                                   behavior). The list can be pretty
                                                   huge though.

      :param str name: Filter jobs by :attr:`~JobDescription.name` (exact match).

                       Empty string or ``None`` means that no filter is applied (default).

      :param ~typing.Sequence[str] tags: filter jobs by :attr:`~JobDescription.tags`.

                                         Retrieves only jobs submitted with all tags from the specified list.

                                         Empty list means that no filter is applied (default).

      :param ~typing.Iterable[str] owners: filter jobs by their owners.

                                           The parameter can be a set or list of owner
                                           usernames (see :attr:`JobDescription.owner`
                                           for details).

                                           No owners filter is applied if the iterable
                                           is empty.

      :param ~datetime.datetime since: filter jobs by their creation date.

                                       Retrieves only jobs submitted after the specified date
                                       (including) if it is not ``None``.  If the parameter
                                       is a naive datetime object, it represents local time.

                                       ``None`` means that no filter is applied (default).

      :param ~datetime.datetime until: filter jobs by their creation date.

                                       Retrieves only jobs submitted before the specified date
                                       (including) if it is not ``None``.  If the parameter
                                       is a naive datetime object, it represents local time.

                                       ``None`` means that no filter is applied (default).

      :param bool reverse: iterate jobs in the reverse order.

                           If *reverse* is false (default) the jobs are iterated in
                           the order of their creation date, from earlier to later.
                           If *reverse* is true, they are iterated in the reverse order,
                           from later to earlier.

      :param int limit: limit the number of jobs.

                        ``None`` means no limit (default).

      :param str cluster_name: list jobs on specified cluster.

                               ``None`` means the current cluster (default).

      :return: asynchronous iterator which emits :class:`JobDescription` objects.


   .. comethod:: monitor(id: str, *, \
                         cluster_name: Optional[str] = None, \
                 ) -> AsyncIterator[bytes]
      :async-for:

      Get job logs as a sequence of data chunks, e.g.::

         async for chunk in client.jobs.monitor(job_id):
             print(chunk.encode('utf8', errors='replace')

      :param str id: job :attr:`~JobDescription.id` to retrieve logs.

      :param str cluster_name: cluster on which the job is running.

                               ``None`` means the current cluster (default).

      :return: :class:`~collections.abc.AsyncIterator` over :class:`bytes` log chunks.


   .. comethod:: port_forward(id: str, local_port: int, job_port: int, *, \
                              no_key_check: bool = False, \
                              cluster_name: Optional[str] = None \
                 ) -> None
      :async-with:

      Forward local port to job, e.g.::

         async with client.jobs.port_forward(job_id, 8080, 80):
             # port forwarding is awailable inside with-block

      :param str id: job :attr:`~JobDescription.id`.

      :param int local_port: local TCP port to forward.

      :param int jot_port: remote TCP port in a job to forward.

      :param str cluster_name: cluster on which the job is running.

                               ``None`` means the current cluster (default).

   .. comethod:: resize(id: str, *, \
                        w: int, h: int, \
                        cluster_name: Optional[str] = None, \
                 ) -> None

      Resize existing TTY job.

      :param str id: job :attr:`~JobDescription.id`.

      :param int w: New screen width.

      :param int h: New screen height.

      :param str cluster_name: cluster on which the job is running.

                               ``None`` means the current cluster (default).

   .. comethod:: run(container: Container, \
                     *, \
                     name: Optional[str] = None, \
                     tags: Sequence[str] = (), \
                     description: Optional[str] = None, \
                     scheduler_enabled: bool = False, \
                     pass_config: bool = False, \
                     wait_for_jobs_quota: bool = False, \
                     schedule_timeout: Optional[float] = None, \
                     life_span: Optional[float] = None, \
                 ) -> JobDescription

      Start a new job.

      .. deprecated:: 20.11.25

         Please use :meth:`start` instead.

      :param Container container: container description to start.

      :param str name: optional container name.

      :param str name: optional job tags.

      :param str description: optional container description.

      :param bool scheduler_enabled: a flag that specifies is the job should
                                     participate in round-robin scheduling.

      :param bool pass_config: a flag that specifies that platform should pass
                                 config data to job. This allows to API and CLI
                                 from the inside of the job. See
                                 :meth:`Factory.login_with_passed_config` for details.

      :param bool wait_for_jobs_quota: when this flat is set, job will wait for another
                                       job to stop instead of failing immediately
                                       because of total running jobs quota.

      :param float schedule_timeout: minimal timeout to wait before reporting that job
                                     cannot be scheduled because the lack of computation
                                     cluster resources (memory, CPU/GPU etc).
                                     This option is not allowed when ``is_preemptible``
                                     is set to ``True``.

      :param float life_span: job run-time limit in seconds. Pass `None` to disable.

      :return: :class:`JobDescription` instance with information about started job.

   .. comethod:: start(*, \
                       image: RemoteImage, \
                       preset_name: str, \
                       entrypoint: Optional[str] = None, \
                       command: Optional[str] = None, \
                       working_dir: Optional[str] = None, \
                       http: Optional[HTTPPort] = None, \
                       env: Optional[Mapping[str, str]] = None, \
                       volumes: Sequence[Volume] = (), \
                       secret_env: Optional[Mapping[str, URL]] = None, \
                       secret_files: Sequence[SecretFile] = (), \
                       disk_volumes: Sequence[DiskVolume] = (), \
                       tty: bool = False, \
                       shm: bool = False, \
                       name: Optional[str] = None, \
                       tags: Sequence[str] = (), \
                       description: Optional[str] = None, \
                       pass_config: bool = False, \
                       wait_for_jobs_quota: bool = False, \
                       schedule_timeout: Optional[float] = None, \
                       restart_policy: JobRestartPolicy = JobRestartPolicy.NEVER, \
                       life_span: Optional[float] = None, \
                       privileged: bool = False, \
                 ) -> JobDescription

      Start a new job.

      :param RemoteImage image: image used for starting a container.

      :param str preset_name: name of the preset of resources given to a container on a node.

      :param str entrypoint: optional Docker ENTRYPOINT_ used for overriding image entry-point
                             (:class:`str`), default ``None`` is used to pick entry-point
                             from image's *Dockerfile*.

      :param str command: optional command line to execute inside a container (:class:`str`),
                          ``None`` for picking command line from image's *Dockerfile*.

      :param str working_dir: optional working directory inside a container (:class:`str`),
                          ``None`` for picking working directory from image's *Dockerfile*.

      :param HTTPPort http: optional parameters of HTTP server exposed by container,
                            ``None`` if the container doesn't provide HTTP access.

      :param ~collections.abc.Mapping[str,str] env: optional custom *environment variables* for pushing into container's task.
                                                    A :class:`~collections.abc.Mapping` where keys are environments variables names
                                                    and values are variable values, both :class:`str`. ``None`` by default.

      :param ~collections.abc.Sequence[Volume] volumes: optional Docker volumes to mount into container, a :class:`~collections.abc.Sequence`
                                                                 of :class:`Volume` objects. Empty :class:`tuple` by default.

      :param ~collections.abc.Mapping[str,yarl.URL] secret_env: optional secrets pushed as custom *environment variables* into container's task.
                                                                A :class:`~collections.abc.Mapping` where keys are environments variables
                                                                names (:class:`str`) and values are secret URIs (:class:`yarl.URL`).
                                                                ``None`` by default.

      :param ~collections.abc.Sequence[SecretFile] secret_files: optional secrets mounted as files in a container, a :class:`~collections.abc.Sequence`
                                                                 of :class:`SecretFile` objects. Empty :class:`tuple` by default.

      :param ~collections.abc.Sequence[DiskVolume] disk_volumes: optional disk volumes used to mount into container, a :class:`~collections.abc.Sequence`
                                                                 of :class:`DiskVolume` objects. Empty :class:`tuple` by default.

      :param bool tty: Allocate a TTY or not. ``False`` by default.

      :param bool shm: Use Linux shared memory or not. ``False`` by default.

      :param str name: optional job name.

      :param ~collections.abc.Sequence[str] tags: optional job tags.

      :param str description: optional container description.

      :param bool pass_config: a flag that specifies that platform should pass
                               config data to job. This allows to API and CLI
                               from the inside of the job. See
                               :meth:`Factory.login_with_passed_config` for details.

      :param bool wait_for_jobs_quota: when this flat is set, job will wait for another
                                       job to stop instead of failing immediately
                                       because of total running jobs quota.

      :param float schedule_timeout: minimal timeout to wait before reporting that job
                                     cannot be scheduled because the lack of computation
                                     cluster resources (memory, CPU/GPU etc).

      :param float life_span: job run-time limit in seconds. Pass `None` to disable.

      :param JobRestartPolicy restart_policy: job restart behavior. :class:`JobRestartPolicy`.NEVER by default.

      :param bool privileged: Run job in privileged mode. This mode should be
                              supported by cluster.

      :return: :class:`JobDescription` instance with information about started job.

   .. comethod:: send_signal(id: str, signal: Union[str, int], *, \
                             cluster_name: Optional[str] = None, \
                 ) -> None

      Send signal to a job.

      :param str id: job :attr:`~JobDescription.id`.

      :param signal: The signal number or literal name, e.g. ``9`` or ``"SIGKILL"``. See
                     https://www.man7.org/linux/man-pages/man7/signal.7.html for more
                     details about signal types.

      :param str cluster_name: cluster on which the job is running.

                               ``None`` means the current cluster (default).

   .. comethod:: status(id: str) -> JobDescription

      Get information about a job.

      :param str id: job :attr:`~JobDescription.id` to get its status.

      :return: :class:`JobDescription` instance with job status details.

   .. comethod:: tags() -> List[str]

      Get the list of all tags submitted by the user.

      :return: :class:`List[str]` list of tags.

   .. comethod:: top(id: str, *, \
                     cluster_name: Optional[str] = None, \
                 ) -> AsyncIterator[JobTelemetry]
      :async-for:

      Get job usage statistics, e.g.::

          async for data in client.jobs.top(job_id):
              print(data.cpu, data.memory)

      :param str id: job :attr:`~JobDescription.id` to get telemetry data.

      :param str cluster_name: cluster on which the job is running.

                               ``None`` means the current cluster (default).

      :return: asynchronous iterator which emits `JobTelemetry` objects periodically.

   .. comethod:: bump_life_span(id: str, additional_life_span: float) -> None

      Increase life span of a job.

      :param str id: job :attr:`~JobDescription.id` to increase life span.

      :param float life_span: amount of seconds to add to job run-time limit.

Container
=========

.. class:: Container

   *Read-only* :class:`~dataclasses.dataclass` for describing Docker image and
   environment to run a job.

   .. attribute:: image

      :class:`RemoteImage` used for starting a container.

   .. attribute:: resources

      :class:`Resources` which are used to schedule a container.

   .. attribute:: entrypoint

      Docker ENTRYPOINT_ used for overriding image entry-point (:class:`str`), default
      ``None`` is used to pick entry-point from image's *Dockerfile*.

   .. attribute:: command

      Command line to execute inside a container (:class:`str`), ``None`` for picking
      command line from image's *Dockerfile*.

   .. attribute:: http

      :class:`HTTPPort` for describing parameters of HTTP server exposed by container,
      ``None`` if the container doesn't provide HTTP access.

   .. attribute:: env

      Custom *environment variables* for pushing into container's task.

      A :class:`~collections.abc.Mapping` where keys are environments variables names
      and values are variable values, both :class:`str`. Empty :class:`dict` by default.

   .. attribute:: volumes

      Docker volumes to mount into container, a :class:`~collections.abc.Sequence`
      of :class:`Volume` objects. Empty :class:`list` by default.

   .. attribute:: secret_env

      Secrets pushed as custom *environment variables* into container's task.

      A :class:`~collections.abc.Mapping` where keys are environments variables
      names (:class:`str`) and values are secret URIs (:class:`yarl.URL`).
      Empty :class:`dict` by default.

   .. attribute:: secret_files

      Secrets mounted as files in a container, a :class:`~collections.abc.Sequence`
      of :class:`SecretFile` objects. Empty :class:`list` by default.

   .. attribute:: disk_volumes

      Disk volumes used to mount into container, a :class:`~collections.abc.Sequence`
      of :class:`DiskVolume` objects. Empty :class:`list` by default.


ExecInspect
===========

.. class:: ExecInspect

   *Read-only* :class:`~dataclasses.dataclass` with information about an exec session,
   returned by :meth:`Jobs.exec_inspect`.

   .. attribute:: job_id

      Job id which is used for creating the exec session, :class:`str`.

   .. attribute:: id

      The exec session id, :class:`str`.

   .. attribute:: running

      ``True`` if the exec session is running, :class:`bool`.

   .. attribute:: exit_code

      Exit code of the executed command.

   .. attribute:: tty

      ``True`` if the exec session was created in TTY mode, :class:`bool`.

   .. attribute:: entrypoint

      Entrypoint for exec session, :class:`str`.

   .. attribute:: command

      Command line to execute inside the exec session, :class:`str`.



HTTPPort
========

.. class:: HTTPPort

   *Read-only* :class:`~dataclasses.dataclass` for exposing HTTP server started in a
   job.

   To access this server from remote machine please use :attr:`JobDescription.http_url`.

   .. attribute:: port

      Open port number in container's port namespace, :class:`int`.

   .. attribute:: requires_auth

      Authentication in Neuro Platform is required for access to exposed HTTP
      server if ``True``, the port is open publicly otherwise.


JobDescription
==============

.. class:: JobDescription

   *Read-only* :class:`~dataclasses.dataclass` for describing a job.

   .. attribute:: id

      Job ID, :class:`str`.

   .. attribute:: owner

      A name of user who created a job, :class:`str`.

   .. attribute:: cluster_name

      A name of cluster where job was scheduled, :class:`str`.

      .. versionadded:: 19.9.11

   .. attribute:: status

      Current status of job, :class:`JobStatus` enumeration.

   .. attribute:: history

      Additional information about job, e.g. creation time and process exit
      code. :class:`JobStatusHistory` instance.

   .. attribute:: container

      Description of container information used to start a job, :class:`Container`
      instance.

   .. attribute:: scheduler_enabled

      Is job participate in round-robin scheduling.

   .. attribute:: preemptible_node

      Is this node allows execution on preemptible node. If set to ``True``, the job
      only allows execution on preemptible nodes. If set to ``False``, the job
      only allows execution on **non**-preemptible nodes.

   .. attribute:: pass_config

      Is config data is passed by platform, see :meth:`Factory.login_with_passed_config`
      for details.

   .. attribute:: privileged

      Is the job is running in privileged mode, refer to
      `docker documentation <https://docs.docker.com/engine/reference/run/#runtime-privilege-and-linux-capabilities>`_
      for details.

   .. attribute:: name

      Job name provided by user at creation time, :class:`str` or ``None`` if name is
      omitted.

   .. attribute:: tags

      List of job tags provided by user at creation time, :class:`Sequence[str]` or
      ``()`` if tags omitted.

   .. attribute:: description

      Job description text provided by user at creation time, :class:`str` or ``None``
      if description is omitted.

   .. attribute:: http_url

      :class:`yarl.URL` for HTTP server exposed by job, empty URL if the job doesn't
      expose HTTP server.

   .. attribute:: ssh_server

      :class:`yarl.URL` to access running job by SSH. Internal field, don't access it
      from custom code. Use :meth:`Jobs.exec` and :meth:`Jobs.port_forward` as
      official API for accessing to running job.

   .. attribute:: internal_hostname

      DNS name to access the running job from other jobs.

   .. attribute:: internal_hostname_named

      DNS name to access the running job from other jobs based on jobs name instead of
      jobs id. Produces same value for jobs with ``name`` and ``owner`` in same cluster.

   .. attribute:: life_span

      Job run-time limit in seconds, :class:`float`

   .. attribute:: schedule_timeout

      Minimal timeout in seconds job will wait before reporting it
      cannot be scheduled because the lack of computation
      cluster resources (memory, CPU/GPU etc), :class:`float`

JobRestartPolicy
================

.. class:: JobRestartPolicy

   *Enumeration* that describes job restart behavior.

   Can be one of the following statues:

   .. attribute:: NEVER

      Job will never be restarted.

   .. attribute:: ON_FAILURE

      Job will be restarted only in case of job failure.

   .. attribute:: ALWAYS

      Job will always be restarted after success or failure.


JobStatus
=========

.. class:: JobStatus

   *Enumeration* that describes job state.

   Can be one of the following statues:

   .. attribute:: PENDING

      Job is scheduled for execution but not started yet.

   .. attribute:: RUNNING

      Job is running now.

   .. attribute:: SUSPENDED

      Scheduled job is paused to allow other jobs to run.

   .. attribute:: SUCCEEDED

      Job is finished successfully.

   .. attribute:: CANCELLED

      Job was canceled while it was running.

   .. attribute:: FAILED

      Job execution is failed.

   .. attribute:: UNKNOWN

      Invalid (or unknown) status code, should be never returned from server.

   Also some shortcuts are available:

   .. method:: items() -> Set[JobStatus]

      Returns all statuses except :attr:`~JobStatus.UNKNOWN`.

   .. method:: active_items() -> Set[JobStatus]

      Returns all statuses that are not final:
      :attr:`~JobStatus.PENDING`, :attr:`~JobStatus.SUSPENDED` and :attr:`~JobStatus.RUNNING`.

   .. method:: finished_items() -> Set[JobStatus]

      Returns all statuses that are final:
      :attr:`~JobStatus.SUCCEEDED`, :attr:`~JobStatus.CANCELLED` and :attr:`~JobStatus.FAILED`.

   Each enum value has next :class:`bool` fields:

   .. attribute:: is_pending

      Job is waiting to become running. ``True`` for :attr:`~JobStatus.PENDING` and
      :attr:`~JobStatus.SUSPENDED` states.

   .. attribute:: is_running

      Job is running now. ``True`` for :attr:`~JobStatus.RUNNING` state.

   .. attribute:: is_finished

      Job completed execution. ``True`` for
      :attr:`~JobStatus.SUCCEEDED`, :attr:`~JobStatus.CANCELLED` and :attr:`~JobStatus.FAILED`


JobStatusItem
================

.. class:: JobStatusItem

   *Read-only* :class:`~dataclasses.dataclass` for describing job status transition details.

   .. attribute:: transition_time

      Status transition timestamp, :class:`~datetime.datetime`.

   .. attribute:: status

      Status of job after this transition, :class:`JobStatus` enumeration.

   .. attribute:: reason

      Additional information for job status, :class:`str`.

      Examples of *reason* values:

      * ``'ContainerCreating'`` for :attr:`JobStatus.PENDING` job that initiates a pod
        for container.

      * ``'ErrImagePull'`` for :attr:`JobStatus.FAILED` job that cannot pull specified
        image.

   .. attribute:: description

      Extended description for short abbreviation described by :attr:`reason`,
      empty :class:`str` if no additional information is provided.

   .. attribute:: exit_code

      Exit code for container's process (:class:`int`) or ``None`` if the job was not
      started or was still running when this transition occurred.


JobStatusHistory
================

.. class:: JobStatusHistory

   *Read-only* :class:`~dataclasses.dataclass` for describing job status details,
   e.g. creation and finishing time, exit code etc.

   .. attribute:: status

      Current status of job, :class:`JobStatus` enumeration.

      The same as :attr:`JobDescription.status`.

   .. attribute:: reason

      Additional information for current status, :class:`str`.

      Examples of *reason* values:

      * ``'ContainerCreating'`` for :attr:`JobStatus.PENDING` job that initiates a pod
        for container.

      * ``'ErrImagePull'`` for :attr:`JobStatus.FAILED` job that cannot pull specified
        image.

   .. attribute:: description

      Extended description for short abbreviation described by :attr:`reason`,
      empty :class:`str` if no additional information is provided.

   .. attribute:: exit_code

      Exit code for container's process (:class:`int`) or ``None`` if the job was not
      started or is still running.

   .. attribute:: restarts

      Number of container's restarts, :class:`int`.

   .. attribute:: created_at

      Job creation timestamp, :class:`~datetime.datetime` or ``None``.

   .. attribute:: started_at

      Job starting timestamp, :class:`~datetime.datetime` or ``None`` if job not
      started.

   .. attribute:: finished_at

      Job finishing timestamp, :class:`~datetime.datetime` or ``None`` if job not
      finished.

   .. attribute:: transitions

      List of job status transitions, :class:`~typing.Sequence` of :class:`JobStatusItem`.


JobTelemetry
============

.. class:: JobTelemetry

   *Read-only* :class:`~dataclasses.dataclass` for job telemetry (statistics),
   e.g. consumed CPU load, memory footprint etc.

   .. seealso:: :meth:`Jobs.top`.

   .. attribute:: timestamp

      Date and time of telemetry report (:class:`float`), time in seconds since the
      :ref:`epoch`, like the value returned from :func:`time.time()`.

      See :mod:`time` and :mod:`datetime` for more information how to handle the
      timestamp.

   .. attribute:: cpu

      CPU load, :class:`float`. ``1`` means fully loaded one CPU unit, ``0.5`` is for
      half-utilized CPU.

   .. attribute:: memory

      Consumed memory in megabytes, :class:`float`.

   .. attribute:: gpu_duty_cycle

      Percentage of time over the past sample period (10 seconds) during which the
      accelerator was actively processing. :class:`int` between ``1`` and ``100``,
      ``None`` if the job has no GPU available.

   .. attribute:: gpu_memory

      Percentage of used GPU memory, :class:`float` between ``0`` and ``1``.


Message
=======

.. class:: Message

   *Read-only* :class:`~dataclasses.dataclass` for representing job's stdout/stderr
   stream chunks, returned from :meth:`StdStream.read_out`.

   .. attribute:: fileno

      Stream number, `1` for stdin and `2` for stdout.

   .. attribute:: data

      A chunk of stdout/stderr data, :class:`bytes`.


Resources
=========

.. class:: Resources

   *Read-only* :class:`~dataclasses.dataclass` for describing resources (memory, CPU/GPU
   etc.) available for container, see also :attr:`Container.resources` attribute.

   .. attribute:: memory_mb

      Requested memory amount in MegaBytes, :class:`int`.

   .. attribute:: cpu

      Requested number of CPUs, :class:`float`. Please note, Docker supports fractions
      here, e.g. ``0.5`` CPU means a half or CPU on the target node.

   .. attribute:: gpu

      The number of requested GPUs, :class:`int`. Use ``None`` for jobs that doesn't
      require GPU.

   .. attribute:: gpu_model

      The name of requested GPU model, :class:`str` (or ``None`` for job without GPUs).

   .. attribute:: shm

      Use Linux shared memory or not, :class:`bool`. Provide ``True`` if you don't know
      what ``/dev/shm`` device means.

   .. attribute:: tpu_type

      Requested TPU type, see also https://en.wikipedia.org/wiki/Tensor_processing_unit

   .. attribute:: tpu_software_version

      Requested TPU software version.


StdStream
=========

.. class:: StdStream

   A class for communicating with attached job (:meth:`Jobs.attach`) or exec session
   (:meth:`Jobs.exec_start`). Use :meth:`read_out` for reading from stdout/stderr and
   :meth:`write_in` for writing into stdin.

   .. comethod:: close() -> None

      Close `StdStream` instance.

   .. comethod:: read_out() -> Optional[Message]

      Read next chunk from stdout/stderr.

      :return: :class:`Message` instance for read data chunk or `None` if EOF is
               reached or `StdStream` was closed.

   .. comethod:: write_in(data: bytes) -> None

      Write *data* to stdin.

      :param bytes data: data to send.


Volume
======


.. class:: Volume


   *Read-only* :class:`~dataclasses.dataclass` for describing mounted volumes of a
   container.

   .. attribute:: storage_uri

      An URL on remotes storage, :class:`yarl.URL`.

   .. attribute:: container_path

      A path on container filesystem, :class:`str`.

   .. attribute:: read_only

      ``True`` is the volume is mounted in read-only mode, ``False`` for read-write
      (default).


SecretFile
==========


.. class:: SecretFile


   *Read-only* :class:`~dataclasses.dataclass` for describing secrets mounted
   as files in a container.

   .. attribute:: secret_uri

      An URI on a secret, :class:`yarl.URL`.

   .. attribute:: container_path

      A path on container filesystem, :class:`str`.


DiskVolume
==========


.. class:: DiskVolume


   *Read-only* :class:`~dataclasses.dataclass` for describing mounted disk volumes
   of a container.

   .. attribute:: disk_uri

      An URI on a disk, :class:`yarl.URL`.

   .. attribute:: container_path

      A path on container filesystem, :class:`str`.

   .. attribute:: read_only

      ``True`` is the volume is mounted in read-only mode, ``False`` for read-write
      (default).



.. _ENTRYPOINT: https://docs.docker.com/engine/reference/builder/#entrypoint

.. _CMD: https://docs.docker.com/engine/reference/builder/#cmd
