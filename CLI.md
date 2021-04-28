

# Table of Contents
* [neuro](#neuro)
	* [neuro admin](#neuro-admin)
		* [neuro admin get-clusters](#neuro-admin-get-clusters)
		* [neuro admin generate-cluster-config](#neuro-admin-generate-cluster-config)
		* [neuro admin add-cluster](#neuro-admin-add-cluster)
		* [neuro admin show-cluster-options](#neuro-admin-show-cluster-options)
		* [neuro admin get-cluster-users](#neuro-admin-get-cluster-users)
		* [neuro admin add-cluster-user](#neuro-admin-add-cluster-user)
		* [neuro admin remove-cluster-user](#neuro-admin-remove-cluster-user)
		* [neuro admin set-user-quota](#neuro-admin-set-user-quota)
		* [neuro admin add-user-quota](#neuro-admin-add-user-quota)
		* [neuro admin add-resource-preset](#neuro-admin-add-resource-preset)
		* [neuro admin update-resource-preset](#neuro-admin-update-resource-preset)
		* [neuro admin remove-resource-preset](#neuro-admin-remove-resource-preset)
	* [neuro job](#neuro-job)
		* [neuro job run](#neuro-job-run)
		* [neuro job generate-run-command](#neuro-job-generate-run-command)
		* [neuro job ls](#neuro-job-ls)
		* [neuro job status](#neuro-job-status)
		* [neuro job exec](#neuro-job-exec)
		* [neuro job port-forward](#neuro-job-port-forward)
		* [neuro job logs](#neuro-job-logs)
		* [neuro job kill](#neuro-job-kill)
		* [neuro job top](#neuro-job-top)
		* [neuro job save](#neuro-job-save)
		* [neuro job browse](#neuro-job-browse)
		* [neuro job attach](#neuro-job-attach)
		* [neuro job bump-life-span](#neuro-job-bump-life-span)
	* [neuro project](#neuro-project)
		* [neuro project init](#neuro-project-init)
	* [neuro storage](#neuro-storage)
		* [neuro storage cp](#neuro-storage-cp)
		* [neuro storage ls](#neuro-storage-ls)
		* [neuro storage glob](#neuro-storage-glob)
		* [neuro storage rm](#neuro-storage-rm)
		* [neuro storage mkdir](#neuro-storage-mkdir)
		* [neuro storage mv](#neuro-storage-mv)
		* [neuro storage tree](#neuro-storage-tree)
	* [neuro image](#neuro-image)
		* [neuro image ls](#neuro-image-ls)
		* [neuro image push](#neuro-image-push)
		* [neuro image pull](#neuro-image-pull)
		* [neuro image rm](#neuro-image-rm)
		* [neuro image size](#neuro-image-size)
		* [neuro image digest](#neuro-image-digest)
		* [neuro image tags](#neuro-image-tags)
	* [neuro config](#neuro-config)
		* [neuro config login](#neuro-config-login)
		* [neuro config login-with-token](#neuro-config-login-with-token)
		* [neuro config login-headless](#neuro-config-login-headless)
		* [neuro config show](#neuro-config-show)
		* [neuro config show-token](#neuro-config-show-token)
		* [neuro config show-quota](#neuro-config-show-quota)
		* [neuro config aliases](#neuro-config-aliases)
		* [neuro config get-clusters](#neuro-config-get-clusters)
		* [neuro config switch-cluster](#neuro-config-switch-cluster)
		* [neuro config docker](#neuro-config-docker)
		* [neuro config logout](#neuro-config-logout)
	* [neuro completion](#neuro-completion)
		* [neuro completion generate](#neuro-completion-generate)
		* [neuro completion patch](#neuro-completion-patch)
	* [neuro acl](#neuro-acl)
		* [neuro acl grant](#neuro-acl-grant)
		* [neuro acl revoke](#neuro-acl-revoke)
		* [neuro acl list](#neuro-acl-list)
		* [neuro acl add-role](#neuro-acl-add-role)
		* [neuro acl remove-role](#neuro-acl-remove-role)
	* [neuro blob](#neuro-blob)
		* [neuro blob cp](#neuro-blob-cp)
		* [neuro blob ls](#neuro-blob-ls)
		* [neuro blob glob](#neuro-blob-glob)
	* [neuro secret](#neuro-secret)
		* [neuro secret ls](#neuro-secret-ls)
		* [neuro secret add](#neuro-secret-add)
		* [neuro secret rm](#neuro-secret-rm)
	* [neuro disk](#neuro-disk)
		* [neuro disk ls](#neuro-disk-ls)
		* [neuro disk create](#neuro-disk-create)
		* [neuro disk get](#neuro-disk-get)
		* [neuro disk rm](#neuro-disk-rm)
	* [neuro help](#neuro-help)
	* [neuro run](#neuro-run)
	* [neuro ps](#neuro-ps)
	* [neuro status](#neuro-status)
	* [neuro exec](#neuro-exec)
	* [neuro port-forward](#neuro-port-forward)
	* [neuro attach](#neuro-attach)
	* [neuro logs](#neuro-logs)
	* [neuro kill](#neuro-kill)
	* [neuro top](#neuro-top)
	* [neuro save](#neuro-save)
	* [neuro login](#neuro-login)
	* [neuro logout](#neuro-logout)
	* [neuro cp](#neuro-cp)
	* [neuro ls](#neuro-ls)
	* [neuro rm](#neuro-rm)
	* [neuro mkdir](#neuro-mkdir)
	* [neuro mv](#neuro-mv)
	* [neuro images](#neuro-images)
	* [neuro push](#neuro-push)
	* [neuro pull](#neuro-pull)
	* [neuro share](#neuro-share)

# neuro

**Usage:**

```bash
neuro [OPTIONS] COMMAND [ARGS]...
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_--color \[yes &#124; no &#124; auto]_|Color mode.|
|_\--disable-pypi-version-check_|Don't periodically check PyPI to determine whether a new version of Neuro Platform CLI is available for download.|
|_\--hide-token / --no-hide-token_|Prevent user's token sent in HTTP headers from being printed out to stderr during HTTP tracing. Can be used only together with option '--trace'. On by default.|
|_\--iso-datetime-format / --no-iso-datetime-format_|Use ISO 8601 format for printing date and time|
|_\--network-timeout FLOAT_|Network read timeout, seconds.|
|_\--neuromation-config PATH_|Path to config directory.|
|_\-q, --quiet_|Give less output. Option is additive, and can be used up to 2 times.|
|_\--show-traceback_|Show python traceback on error, useful for debugging the tool.|
|_\--skip-stats / --no-skip-stats_|Skip sending usage statistics to Neuro servers. Note: the statistics has no sensitive data, e.g. file, job, image, or user names, executed command lines, environment variables, etc.|
|_--trace_|Trace sent HTTP requests and received replies to stderr.|
|_\-v, --verbose_|Give more output. Option is additive, and can be used up to 2 times.|
|_--version_|Show the version and exit.|


**Command Groups:**

|Usage|Description|
|---|---|
| _[neuro admin](#neuro-admin)_| Cluster administration commands |
| _[neuro job](#neuro-job)_| Job operations |
| _[neuro project](#neuro-project)_| Project operations |
| _[neuro storage](#neuro-storage)_| Storage operations |
| _[neuro image](#neuro-image)_| Container image operations |
| _[neuro config](#neuro-config)_| Client configuration |
| _[neuro completion](#neuro-completion)_| Output shell completion code |
| _[neuro acl](#neuro-acl)_| Access Control List management |
| _[neuro blob](#neuro-blob)_| Blob storage operations |
| _[neuro secret](#neuro-secret)_| Operations with secrets |
| _[neuro disk](#neuro-disk)_| Operations with disks |


**Commands:**

|Usage|Description|
|---|---|
| _[neuro help](#neuro-help)_| Get help on a command |
| _[neuro run](#neuro-run)_| Run a job with predefined resources configuration |
| _[neuro ps](#neuro-ps)_| List all jobs |
| _[neuro status](#neuro-status)_| Display status of a job |
| _[neuro exec](#neuro-exec)_| Execute command in a running job |
| _[neuro port-forward](#neuro-port-forward)_| Forward port\(s) of a running job to local port\(s) |
| _[neuro attach](#neuro-attach)_| Attach local standard input, output, and error streams to a running job |
| _[neuro logs](#neuro-logs)_| Print the logs for a job |
| _[neuro kill](#neuro-kill)_| Kill job\(s) |
| _[neuro top](#neuro-top)_| Display GPU/CPU/Memory usage |
| _[neuro save](#neuro-save)_| Save job's state to an image |
| _[neuro login](#neuro-login)_| Log into Neuro Platform |
| _[neuro logout](#neuro-logout)_| Log out |
| _[neuro cp](#neuro-cp)_| Copy files and directories |
| _[neuro ls](#neuro-ls)_| List directory contents |
| _[neuro rm](#neuro-rm)_| Remove files or directories |
| _[neuro mkdir](#neuro-mkdir)_| Make directories |
| _[neuro mv](#neuro-mv)_| Move or rename files and directories |
| _[neuro images](#neuro-images)_| List images |
| _[neuro push](#neuro-push)_| Push an image to platform registry |
| _[neuro pull](#neuro-pull)_| Pull an image from platform registry |
| _[neuro share](#neuro-share)_| Shares resource with another user |




## neuro admin

Cluster administration commands.

**Usage:**

```bash
neuro admin [OPTIONS] COMMAND [ARGS]...
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|


**Commands:**

|Usage|Description|
|---|---|
| _[neuro admin get-clusters](#neuro-admin-get-clusters)_| Print the list of available clusters |
| _[neuro admin generate\-cluster-config](#neuro-admin-generate-cluster-config)_| Create a cluster configuration file |
| _[neuro admin add-cluster](#neuro-admin-add-cluster)_| Create a new cluster and start its provisioning |
| _[neuro admin show\-cluster-options](#neuro-admin-show-cluster-options)_| Create a cluster configuration file |
| _[neuro admin get\-cluster-users](#neuro-admin-get-cluster-users)_| Print the list of all users in the cluster with their assigned role |
| _[neuro admin add\-cluster-user](#neuro-admin-add-cluster-user)_| Add user access to specified cluster |
| _[neuro admin remove\-cluster-user](#neuro-admin-remove-cluster-user)_| Remove user access from the cluster |
| _[neuro admin set\-user-quota](#neuro-admin-set-user-quota)_| Set user quota to given values |
| _[neuro admin add\-user-quota](#neuro-admin-add-user-quota)_| Add given values to user quota |
| _[neuro admin add\-resource-preset](#neuro-admin-add-resource-preset)_| Add new resource preset |
| _[neuro admin update\-resource-preset](#neuro-admin-update-resource-preset)_| Update existing resource preset |
| _[neuro admin remove\-resource-preset](#neuro-admin-remove-resource-preset)_| Remove resource preset |




### neuro admin get-clusters

Print the list of available clusters.

**Usage:**

```bash
neuro admin get-clusters [OPTIONS]
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




### neuro admin generate-cluster-config

Create a cluster configuration file.

**Usage:**

```bash
neuro admin generate-cluster-config [OPTIONS] [CONFIG]
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_--type \[aws &#124; gcp &#124; azure]_||




### neuro admin add-cluster

Create a new cluster and start its provisioning.

**Usage:**

```bash
neuro admin add-cluster [OPTIONS] CLUSTER_NAME CONFIG
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




### neuro admin show-cluster-options

Create a cluster configuration file.

**Usage:**

```bash
neuro admin show-cluster-options [OPTIONS]
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_--type \[aws &#124; gcp &#124; azure]_||




### neuro admin get-cluster-users

Print the list of all users in the cluster with their assigned role.

**Usage:**

```bash
neuro admin get-cluster-users [OPTIONS] [CLUSTER_NAME]
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




### neuro admin add-cluster-user

Add user access to specified cluster.<br/><br/>The command supports one of 3 user roles: admin, manager or user.

**Usage:**

```bash
neuro admin add-cluster-user [OPTIONS] CLUSTER_NAME USER_NAME [ROLE]
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




### neuro admin remove-cluster-user

Remove user access from the cluster.

**Usage:**

```bash
neuro admin remove-cluster-user [OPTIONS] CLUSTER_NAME USER_NAME
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




### neuro admin set-user-quota

Set user quota to given values

**Usage:**

```bash
neuro admin set-user-quota [OPTIONS] CLUSTER_NAME USER_NAME
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_\-c, --credits AMOUNT_|Maximum running jobs quota|
|_\-g, --gpu AMOUNT_|GPU quota value in hours \(h) or minutes \(m).|
|_\-j, --jobs AMOUNT_|Maximum running jobs quota|
|_\-n, --non-gpu AMOUNT_|Non-GPU quota value in hours \(h) or minutes \(m).|




### neuro admin add-user-quota

Add given values to user quota

**Usage:**

```bash
neuro admin add-user-quota [OPTIONS] CLUSTER_NAME USER_NAME
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_\-c, --credits AMOUNT_|Maximum running jobs quota|
|_\-g, --gpu AMOUNT_|Additional GPU quota value in hours \(h) or minutes \(m).|
|_\-n, --non-gpu AMOUNT_|Additional non-GPU quota value in hours \(h) or minutes \(m).|




### neuro admin add-resource-preset

Add new resource preset

**Usage:**

```bash
neuro admin add-resource-preset [OPTIONS] PRESET_NAME
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_\-c, --cpu NUMBER_|Number of CPUs  \[default: 0.1]|
|_\--credits-per-hour AMOUNT_|Price of running job of this preset for an hour in credits  \[default: 0]|
|_\-g, --gpu NUMBER_|Number of GPUs|
|_\--gpu-model MODEL_|GPU model|
|_\-m, --memory AMOUNT_|Memory amount  \[default: 1G]|
|_\--preemptible-node / --non-preemptible-node_|Use a lower-cost preemptible instance  \[default: False]|
|_\-p, --scheduler / -P, --no-scheduler_|Use round robin scheduler for jobs  \[default: False]|
|_\--tpu-sw-version VERSION_|TPU software version|
|_\--tpu-type TYPE_|TPU type|




### neuro admin update-resource-preset

Update existing resource preset

**Usage:**

```bash
neuro admin update-resource-preset [OPTIONS] PRESET_NAME
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_\-c, --cpu NUMBER_|Number of CPUs|
|_\--credits-per-hour AMOUNT_|Price of running job of this preset for an hour in credits|
|_\-g, --gpu NUMBER_|Number of GPUs|
|_\--gpu-model MODEL_|GPU model|
|_\-m, --memory AMOUNT_|Memory amount|
|_\--preemptible-node / --non-preemptible-node_|Use a lower-cost preemptible instance|
|_\-p, --scheduler / -P, --no-scheduler_|Use round robin scheduler for jobs|
|_\--tpu-sw-version VERSION_|TPU software version|
|_\--tpu-type TYPE_|TPU type|




### neuro admin remove-resource-preset

Remove resource preset

**Usage:**

```bash
neuro admin remove-resource-preset [OPTIONS] PRESET_NAME
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




## neuro job

Job operations.

**Usage:**

```bash
neuro job [OPTIONS] COMMAND [ARGS]...
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|


**Commands:**

|Usage|Description|
|---|---|
| _[neuro job run](#neuro-job-run)_| Run a job with predefined resources configuration |
| _[neuro job generate\-run-command](#neuro-job-generate-run-command)_| Generate command that will rerun given job |
| _[neuro job ls](#neuro-job-ls)_| List all jobs |
| _[neuro job status](#neuro-job-status)_| Display status of a job |
| _[neuro job exec](#neuro-job-exec)_| Execute command in a running job |
| _[neuro job port-forward](#neuro-job-port-forward)_| Forward port\(s) of a running job to local port\(s) |
| _[neuro job logs](#neuro-job-logs)_| Print the logs for a job |
| _[neuro job kill](#neuro-job-kill)_| Kill job\(s) |
| _[neuro job top](#neuro-job-top)_| Display GPU/CPU/Memory usage |
| _[neuro job save](#neuro-job-save)_| Save job's state to an image |
| _[neuro job browse](#neuro-job-browse)_| Opens a job's URL in a web browser |
| _[neuro job attach](#neuro-job-attach)_| Attach local standard input, output, and error streams to a running job |
| _[neuro job bump\-life-span](#neuro-job-bump-life-span)_| Increase job life span |




### neuro job run

Run a job with predefined resources configuration.<br/><br/>IMAGE docker image name to run in a job.<br/><br/>CMD list will be passed as arguments to the executed job's image.<br/>

**Usage:**

```bash
neuro job run [OPTIONS] IMAGE [CMD]...
```

**Examples:**

```bash

# Starts a container pytorch:latest on a machine with smaller GPU resources
# (see exact values in `neuro config show`) and with two volumes mounted:
#   storage:/<home-directory>   --> /var/storage/home (in read-write mode),
#   storage:/neuromation/public --> /var/storage/neuromation (in read-only mode).
neuro run --preset=gpu-small --volume=storage::/var/storage/home:rw \
--volume=storage:/neuromation/public:/var/storage/home:ro pytorch:latest

# Starts a container using the custom image my-ubuntu:latest stored in neuro
# registry, run /script.sh and pass arg1 and arg2 as its arguments:
neuro run -s cpu-small image:my-ubuntu:latest --entrypoint=/script.sh arg1 arg2

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_--browse_|Open a job's URL in a web browser|
|_\-d, --description DESC_|Optional job description in free format|
|_--detach_|Don't attach to job logs and don't wait for exit code|
|_--entrypoint TEXT_|Executable entrypoint in the container \(note that it overwrites `ENTRYPOINT` and `CMD` instructions of the docker image)|
|_\-e, --env VAR=VAL_|Set environment variable in container. Use multiple options to define more than one variable. See `neuro help secrets` for information about passing secrets as environment variables.|
|_\--env-file PATH_|File with environment variables to pass|
|_\-x, --extshm / -X, --no-extshm_|Request extended '/dev/shm' space  \[default: True]|
|_--http PORT_|Enable HTTP port forwarding to container  \[default: 80]|
|_\--http-auth / --no-http-auth_|Enable HTTP authentication for forwarded HTTP port  \[default: True]|
|_\--life-span TIMEDELTA_|Optional job run-time limit in the format '1d2h3m4s' \(some parts may be missing). Set '0' to disable. Default value '1d' can be changed in the user config.|
|_\-n, --name NAME_|Optional job name|
|_\--pass-config / --no-pass-config_|Upload neuro config to the job  \[default: False]|
|_\--port-forward LOCAL\_PORT:REMOTE_RORT_|Forward port\(s) of a running job to local port\(s) \(use multiple times for forwarding several ports)|
|_\-s, --preset PRESET_|Predefined resource configuration \(to see available values, run `neuro config show`)|
|_--privileged_|Run job in privileged mode, if it is supported by cluster.  \[default: False]|
|_\-q, --quiet_|Run command in quiet mode \(DEPRECATED)|
|_\--restart \[never &#124; on-failure &#124; always]_|Restart policy to apply when a job exits  \[default: never]|
|_\--schedule-timeout TIMEDELTA_|Optional job schedule timeout in the format '3m4s' \(some parts may be missing).|
|_--share USER_|Share job write permissions to user or role.|
|_--tag TAG_|Optional job tag, multiple values allowed|
|_\-t, --tty / -T, --no-tty_|Allocate a TTY, can be useful for interactive jobs. By default is on if the command is executed from a terminal, non-tty mode is used if executed from a script.|
|_\-v, --volume MOUNT_|Mounts directory from vault into container. Use multiple options to mount more than one volume. See `neuro help secrets` for information about passing secrets as mounted files.|
|_\--wait-for-seat / --no-wait-for-seat_|Wait for total running jobs quota  \[default: False]|
|_\--wait-start / --no-wait-start_|Wait for a job start or failure  \[default: True]|
|_\-w, --workdir TEXT_|Working directory inside the container|




### neuro job generate-run-command

Generate command that will rerun given job.<br/>

**Usage:**

```bash
neuro job generate-run-command [OPTIONS] JOB
```

**Examples:**

```bash

# You can use the following to directly re-execute it:
eval $(neuro job generate-run-command <job-id>)

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




### neuro job ls

List all jobs.<br/>

**Usage:**

```bash
neuro job ls [OPTIONS]
```

**Examples:**

```bash

neuro ps -a
neuro ps -a --owner=user-1 --owner=user-2
neuro ps --name my-experiments-v1 -s failed -s succeeded
neuro ps --description=my favourite job
neuro ps -s failed -s succeeded -q
neuro ps -t tag1 -t tag2

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_\-a, --all_|Show all jobs regardless the status.|
|_\-d, --description DESCRIPTION_|Filter out jobs by description \(exact match).|
|_--distinct_|Show only first job if names are same.|
|_--format COLUMNS_|Output table format, see "neuro help ps\-format" for more info about the format specification. The default can be changed using the job.ps-format configuration variable documented in "neuro help user-config"|
|_\--full-uri_|Output full image URI.|
|_\-n, --name NAME_|Filter out jobs by name.|
|_\-o, --owner TEXT_|Filter out jobs by owner \(multiple option). Supports `ME` option to filter by the current user.|
|_\-q, --quiet_|Run command in quiet mode \(DEPRECATED)|
|_\--recent-first / --recent-last_|Show newer jobs first or last|
|_--since DATE\_OR_TIMEDELTA_|Show jobs created after a specific date \(including). Use value of format '1d2h3m4s' to specify moment in past relatively to current time.|
|_\-s, --status \[pending &#124; suspended &#124; running &#124; succeeded &#124; failed &#124; cancelled]_|Filter out jobs by status \(multiple option).|
|_\-t, --tag TAG_|Filter out jobs by tag \(multiple option)|
|_--until DATE\_OR_TIMEDELTA_|Show jobs created before a specific date \(including). Use value of format '1d2h3m4s' to specify moment in past relatively to current time.|
|_\-w, --wide_|Do not cut long lines for terminal width.|




### neuro job status

Display status of a job.

**Usage:**

```bash
neuro job status [OPTIONS] JOB
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_\--full-uri_|Output full URI.|




### neuro job exec

Execute command in a running job.<br/>

**Usage:**

```bash
neuro job exec [OPTIONS] JOB CMD...
```

**Examples:**

```bash

# Provides a shell to the container:
neuro exec my-job /bin/bash

# Executes a single command in the container and returns the control:
neuro exec --no-tty my-job ls -l

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_\-t, --tty / -T, --no-tty_|Allocate a TTY, can be useful for interactive jobs. By default is on if the command is executed from a terminal, non-tty mode is used if executed from a script.|




### neuro job port-forward

Forward port\(s) of a running job to local port\(s).<br/>

**Usage:**

```bash
neuro job port-forward [OPTIONS] JOB LOCAL_PORT:REMOTE_RORT...
```

**Examples:**

```bash

# Forward local port 2080 to port 80 of job's container.
# You can use http://localhost:2080 in browser to access job's served http
neuro job port-forward my-fastai-job 2080:80

# Forward local port 2222 to job's port 22
# Then copy all data from container's folder '/data' to current folder
# (please run second command in other terminal)
neuro job port-forward my-job-with-ssh-server 2222:22
rsync -avxzhe ssh -p 2222 root@localhost:/data .

# Forward few ports at once
neuro job port-forward my-job 2080:80 2222:22 2000:100

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




### neuro job logs

Print the logs for a job.

**Usage:**

```bash
neuro job logs [OPTIONS] JOB
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




### neuro job kill

Kill job\(s).

**Usage:**

```bash
neuro job kill [OPTIONS] JOBS...
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




### neuro job top

Display GPU/CPU/Memory usage.<br/>

**Usage:**

```bash
neuro job top [OPTIONS] [JOBS]...
```

**Examples:**

```bash

neuro top
neuro top job-1 job-2
neuro top --owner=user-1 --owner=user-2
neuro top --name my-experiments-v1
neuro top -t tag1 -t tag2

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_\-d, --description DESCRIPTION_|Filter out jobs by description \(exact match).|
|_--format COLUMNS_|Output table format, see "neuro help top\-format" for more info about the format specification. The default can be changed using the job.top-format configuration variable documented in "neuro help user-config"|
|_\--full-uri_|Output full image URI.|
|_\-n, --name NAME_|Filter out jobs by name.|
|_\-o, --owner TEXT_|Filter out jobs by owner \(multiple option). Supports `ME` option to filter by the current user. Specify `ALL` to show jobs of all users.|
|_--since DATE\_OR_TIMEDELTA_|Show jobs created after a specific date \(including). Use value of format '1d2h3m4s' to specify moment in past relatively to current time.|
|_--sort COLUMNS_|Sort rows by specified column. Add "-" prefix to revert the sorting order. Multiple columns can be specified \(comma separated).  \[default: cpu]|
|_\-t, --tag TAG_|Filter out jobs by tag \(multiple option)|
|_--timeout FLOAT_|Maximum allowed time for executing the command, 0 for no timeout  \[default: 0]|
|_--until DATE\_OR_TIMEDELTA_|Show jobs created before a specific date \(including). Use value of format '1d2h3m4s' to specify moment in past relatively to current time.|




### neuro job save

Save job's state to an image.<br/>

**Usage:**

```bash
neuro job save [OPTIONS] JOB IMAGE
```

**Examples:**

```bash

neuro job save job-id image:ubuntu-patched
neuro job save my-favourite-job image:ubuntu-patched:v1
neuro job save my-favourite-job image://bob/ubuntu-patched

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




### neuro job browse

Opens a job's URL in a web browser.

**Usage:**

```bash
neuro job browse [OPTIONS] JOB
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




### neuro job attach

Attach local standard input, output, and error streams to a running job.

**Usage:**

```bash
neuro job attach [OPTIONS] JOB
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_\--port-forward LOCAL\_PORT:REMOTE_RORT_|Forward port\(s) of a running job to local port\(s) \(use multiple times for forwarding several ports)|




### neuro job bump-life-span

Increase job life span

**Usage:**

```bash
neuro job bump-life-span [OPTIONS] JOB TIMEDELTA
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




## neuro project

Project operations.

**Usage:**

```bash
neuro project [OPTIONS] COMMAND [ARGS]...
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|


**Commands:**

|Usage|Description|
|---|---|
| _[neuro project init](#neuro-project-init)_| Initialize an empty project |




### neuro project init

Initialize an empty project.<br/>

**Usage:**

```bash
neuro project init [OPTIONS] [SLUG]
```

**Examples:**

```bash

# Initializes a scaffolding for the new project with the recommended project
# structure (see http://github.com/neuro-inc/cookiecutter-neuro-project)
neuro project init

# Initializes a scaffolding for the new project with the recommended project
# structure and sets default project folder name to "example"
neuro project init my-project-id

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




## neuro storage

Storage operations.

**Usage:**

```bash
neuro storage [OPTIONS] COMMAND [ARGS]...
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|


**Commands:**

|Usage|Description|
|---|---|
| _[neuro storage cp](#neuro-storage-cp)_| Copy files and directories |
| _[neuro storage ls](#neuro-storage-ls)_| List directory contents |
| _[neuro storage glob](#neuro-storage-glob)_| List resources that match PATTERNS |
| _[neuro storage rm](#neuro-storage-rm)_| Remove files or directories |
| _[neuro storage mkdir](#neuro-storage-mkdir)_| Make directories |
| _[neuro storage mv](#neuro-storage-mv)_| Move or rename files and directories |
| _[neuro storage tree](#neuro-storage-tree)_| List contents of directories in a tree-like format |




### neuro storage cp

Copy files and directories.<br/><br/>Either SOURCES or DESTINATION should have storage:// scheme. If scheme is<br/>omitted, file:// scheme is assumed.<br/><br/>Use /dev/stdin and /dev/stdout file names to copy a file from terminal and<br/>print the content of file on the storage to console.<br/><br/>Any number of \--exclude and --include options can be passed.  The filters<br/>that appear later in the command take precedence over filters that appear<br/>earlier in the command.  If neither \--exclude nor --include options are<br/>specified the default can be changed using the storage.cp-exclude<br/>configuration variable documented in "neuro help user-config".<br/>

**Usage:**

```bash
neuro storage cp [OPTIONS] [SOURCES]... [DESTINATION]
```

**Examples:**

```bash

# copy local files into remote storage root
neuro cp foo.txt bar/baz.dat storage:
neuro cp foo.txt bar/baz.dat -t storage:

# copy local directory `foo` into existing remote directory `bar`
neuro cp -r foo -t storage:bar

# copy the content of local directory `foo` into existing remote
# directory `bar`
neuro cp -r -T storage:foo storage:bar

# download remote file `foo.txt` into local file `/tmp/foo.txt` with
# explicit file:// scheme set
neuro cp storage:foo.txt file:///tmp/foo.txt
neuro cp -T storage:foo.txt file:///tmp/foo.txt
neuro cp storage:foo.txt file:///tmp
neuro cp storage:foo.txt -t file:///tmp

# download other user's remote file into the current directory
neuro cp storage://{username}/foo.txt .

# download only files with extension `.out` into the current directory
neuro cp storage:results/*.out .

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_--continue_|Continue copying partially-copied files.|
|_\--exclude-from-files FILES_|A list of file names that contain patterns for exclusion files and directories. Used only for uploading. The default can be changed using the storage.cp\-exclude-from-files configuration variable documented in "neuro help user-config"|
|_--exclude_|Exclude files and directories that match the specified pattern.|
|_--include_|Don't exclude files and directories that match the specified pattern.|
|_\--glob / --no-glob_|Expand glob patterns in SOURCES with explicit scheme.  \[default: True]|
|_\-T, --no-target-directory_|Treat DESTINATION as a normal file.|
|_\-p, --progress / -P, --no-progress_|Show progress, on by default in TTY mode, off otherwise.|
|_\-r, --recursive_|Recursive copy, off by default|
|_\-t, --target-directory DIRECTORY_|Copy all SOURCES into DIRECTORY.|
|_\-u, --update_|Copy only when the SOURCE file is newer than the destination file or when the destination file is missing.|




### neuro storage ls

List directory contents.<br/><br/>By default PATH is equal user's home dir \(storage:)

**Usage:**

```bash
neuro storage ls [OPTIONS] [PATHS]...
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_\-d, --directory_|list directories themselves, not their contents.|
|_-l_|use a long listing format.|
|_\-h, --human-readable_|with -l print human readable sizes \(e.g., 2K, 540M).|
|_\-a, --all_|do not ignore entries starting with .|
|_--sort \[name &#124; size &#124; time]_|sort by given field, default is name.|




### neuro storage glob

List resources that match PATTERNS.

**Usage:**

```bash
neuro storage glob [OPTIONS] [PATTERNS]...
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




### neuro storage rm

Remove files or directories.<br/>

**Usage:**

```bash
neuro storage rm [OPTIONS] PATHS...
```

**Examples:**

```bash

neuro rm storage:foo/bar
neuro rm storage://{username}/foo/bar
neuro rm --recursive storage://{username}/foo/
neuro rm storage:foo/**/*.tmp

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_\--glob / --no-glob_|Expand glob patterns in PATHS  \[default: True]|
|_\-p, --progress / -P, --no-progress_|Show progress, on by default in TTY mode, off otherwise.|
|_\-r, --recursive_|remove directories and their contents recursively|




### neuro storage mkdir

Make directories.

**Usage:**

```bash
neuro storage mkdir [OPTIONS] PATHS...
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_\-p, --parents_|No error if existing, make parent directories as needed|




### neuro storage mv

Move or rename files and directories.<br/><br/>SOURCE must contain path to the file or directory existing on the storage,<br/>and DESTINATION must contain the full path to the target file or directory.<br/>

**Usage:**

```bash
neuro storage mv [OPTIONS] [SOURCES]... [DESTINATION]
```

**Examples:**

```bash

# move and rename remote file
neuro mv storage:foo.txt storage:bar/baz.dat
neuro mv -T storage:foo.txt storage:bar/baz.dat

# move remote files into existing remote directory
neuro mv storage:foo.txt storage:bar/baz.dat storage:dst
neuro mv storage:foo.txt storage:bar/baz.dat -t storage:dst

# move the content of remote directory into other existing
# remote directory
neuro mv -T storage:foo storage:bar

# move remote file into other user's directory
neuro mv storage:foo.txt storage://{username}/bar.dat

# move remote file from other user's directory
neuro mv storage://{username}/foo.txt storage:bar.dat

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_\--glob / --no-glob_|Expand glob patterns in SOURCES  \[default: True]|
|_\-T, --no-target-directory_|Treat DESTINATION as a normal file|
|_\-t, --target-directory DIRECTORY_|Copy all SOURCES into DIRECTORY|




### neuro storage tree

List contents of directories in a tree-like format.<br/><br/>Tree is a recursive directory listing program that produces a depth indented<br/>listing of files, which is colorized ala dircolors if the LS_COLORS<br/>environment variable is set and output is to tty.  With no arguments, tree<br/>lists the files in the storage: directory.  When directory arguments are<br/>given, tree lists all the files and/or directories found in the given<br/>directories each in turn.  Upon completion of listing all files/directories<br/>found, tree returns the total number of files and/or directories listed.<br/><br/>By default PATH is equal user's home dir \(storage:)

**Usage:**

```bash
neuro storage tree [OPTIONS] [PATH]
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_\-h, --human-readable_|Print the size in a more human readable way.|
|_\-a, --all_|do not ignore entries starting with .|
|_\-s, --size_|Print the size in bytes of each file.|
|_--sort \[name &#124; size &#124; time]_|sort by given field, default is name|




## neuro image

Container image operations.

**Usage:**

```bash
neuro image [OPTIONS] COMMAND [ARGS]...
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|


**Commands:**

|Usage|Description|
|---|---|
| _[neuro image ls](#neuro-image-ls)_| List images |
| _[neuro image push](#neuro-image-push)_| Push an image to platform registry |
| _[neuro image pull](#neuro-image-pull)_| Pull an image from platform registry |
| _[neuro image rm](#neuro-image-rm)_| Remove image from platform registry |
| _[neuro image size](#neuro-image-size)_| Get image size Image name must be URL with image:// scheme |
| _[neuro image digest](#neuro-image-digest)_| Get digest of an image from remote registry Image name must be URL with image://... |
| _[neuro image tags](#neuro-image-tags)_| List tags for image in platform registry |




### neuro image ls

List images.

**Usage:**

```bash
neuro image ls [OPTIONS]
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_-l_|List in long format.|
|_\--full-uri_|Output full image URI.|
|_\-n, --name NAME_|Filter out images by name.|
|_\-o, --owner TEXT_|Filter out images by owner \(multiple option). Supports `ME` option to filter by the current user.|




### neuro image push

Push an image to platform registry.<br/><br/>Remote image must be URL with image:// scheme. Image names can contain tag.<br/>If tags not specified 'latest' will be used as value.<br/>

**Usage:**

```bash
neuro image push [OPTIONS] LOCAL_IMAGE [REMOTE_IMAGE]
```

**Examples:**

```bash

neuro push myimage
neuro push alpine:latest image:my-alpine:production
neuro push alpine image://myfriend/alpine:shared

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_\-q, --quiet_|Run command in quiet mode \(DEPRECATED)|




### neuro image pull

Pull an image from platform registry.<br/><br/>Remote image name must be URL with image:// scheme. Image names can contain<br/>tag.<br/>

**Usage:**

```bash
neuro image pull [OPTIONS] REMOTE_IMAGE [LOCAL_IMAGE]
```

**Examples:**

```bash

neuro pull image:myimage
neuro pull image://myfriend/alpine:shared
neuro pull image://username/my-alpine:production alpine:from-registry

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_\-q, --quiet_|Run command in quiet mode \(DEPRECATED)|




### neuro image rm

Remove image from platform registry.<br/><br/>Image name must be URL with image:// scheme. Image name must contain tag.<br/>

**Usage:**

```bash
neuro image rm [OPTIONS] IMAGES...
```

**Examples:**

```bash

neuro image rm image://myfriend/alpine:shared
neuro image rm image:myimage:latest

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_-f_|Force deletion of all tags referencing the image.|




### neuro image size

Get image size<br/><br/>Image name must be URL with image:// scheme. Image name must contain tag.<br/>

**Usage:**

```bash
neuro image size [OPTIONS] IMAGE
```

**Examples:**

```bash

neuro image size image://myfriend/alpine:shared
neuro image size image:myimage:latest

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




### neuro image digest

Get digest of an image from remote registry<br/><br/>Image name must be URL with image:// scheme. Image name must contain tag.<br/>

**Usage:**

```bash
neuro image digest [OPTIONS] IMAGE
```

**Examples:**

```bash

neuro image digest image://myfriend/alpine:shared
neuro image digest image:myimage:latest

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




### neuro image tags

List tags for image in platform registry.<br/><br/>Image name must be URL with image:// scheme.<br/>

**Usage:**

```bash
neuro image tags [OPTIONS] IMAGE
```

**Examples:**

```bash

neuro image tags image://myfriend/alpine
neuro image tags -l image:myimage

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_-l_|List in long format, with image sizes.|




## neuro config

Client configuration.

**Usage:**

```bash
neuro config [OPTIONS] COMMAND [ARGS]...
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|


**Commands:**

|Usage|Description|
|---|---|
| _[neuro config login](#neuro-config-login)_| Log into Neuro Platform |
| _[neuro config login\-with-token](#neuro-config-login-with-token)_| Log into Neuro Platform with token |
| _[neuro config login-headless](#neuro-config-login-headless)_| Log into Neuro Platform from non-GUI server environment |
| _[neuro config show](#neuro-config-show)_| Print current settings |
| _[neuro config show-token](#neuro-config-show-token)_| Print current authorization token |
| _[neuro config show-quota](#neuro-config-show-quota)_| Print quota and remaining computation time for active cluster |
| _[neuro config aliases](#neuro-config-aliases)_| List available command aliases |
| _[neuro config get-clusters](#neuro-config-get-clusters)_| Fetch and display the list of available clusters |
| _[neuro config switch-cluster](#neuro-config-switch-cluster)_| Switch the active cluster |
| _[neuro config docker](#neuro-config-docker)_| Configure docker client to fit the Neuro Platform |
| _[neuro config logout](#neuro-config-logout)_| Log out |




### neuro config login

Log into Neuro Platform.<br/><br/>URL is a platform entrypoint URL.

**Usage:**

```bash
neuro config login [OPTIONS] [URL]
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




### neuro config login-with-token

Log into Neuro Platform with token.<br/><br/>TOKEN is authentication token provided by administration team. URL is a<br/>platform entrypoint URL.

**Usage:**

```bash
neuro config login-with-token [OPTIONS] TOKEN [URL]
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




### neuro config login-headless

Log into Neuro Platform from non-GUI server environment.<br/><br/>URL is a platform entrypoint URL.<br/><br/>The command works similar to "neuro login" but instead of opening a browser<br/>for performing OAuth registration prints an URL that should be open on guest<br/>host.<br/><br/>Then user inputs a code displayed in a browser after successful login back<br/>in neuro command to finish the login process.

**Usage:**

```bash
neuro config login-headless [OPTIONS] [URL]
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




### neuro config show

Print current settings.

**Usage:**

```bash
neuro config show [OPTIONS]
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




### neuro config show-token

Print current authorization token.

**Usage:**

```bash
neuro config show-token [OPTIONS]
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




### neuro config show-quota

Print quota and remaining computation time for active cluster.

**Usage:**

```bash
neuro config show-quota [OPTIONS] [USER]
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




### neuro config aliases

List available command aliases.

**Usage:**

```bash
neuro config aliases [OPTIONS]
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




### neuro config get-clusters

Fetch and display the list of available clusters.

**Usage:**

```bash
neuro config get-clusters [OPTIONS]
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




### neuro config switch-cluster

Switch the active cluster.<br/><br/>CLUSTER_NAME is the cluster name to select.  The interactive prompt is used<br/>if the name is omitted \(default).

**Usage:**

```bash
neuro config switch-cluster [OPTIONS] [CLUSTER_NAME]
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




### neuro config docker

Configure docker client to fit the Neuro Platform.

**Usage:**

```bash
neuro config docker [OPTIONS]
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_\--docker-config PATH_|Specifies the location of the Docker client configuration files|




### neuro config logout

Log out.

**Usage:**

```bash
neuro config logout [OPTIONS]
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




## neuro completion

Output shell completion code.

**Usage:**

```bash
neuro completion [OPTIONS] COMMAND [ARGS]...
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|


**Commands:**

|Usage|Description|
|---|---|
| _[neuro completion generate](#neuro-completion-generate)_| Provide an instruction for shell completion generation |
| _[neuro completion patch](#neuro-completion-patch)_| Automatically patch shell configuration profile to enable completion |




### neuro completion generate

Provide an instruction for shell completion generation.

**Usage:**

```bash
neuro completion generate [OPTIONS] [bash|zsh]
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




### neuro completion patch

Automatically patch shell configuration profile to enable completion

**Usage:**

```bash
neuro completion patch [OPTIONS] [bash|zsh]
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




## neuro acl

Access Control List management.

**Usage:**

```bash
neuro acl [OPTIONS] COMMAND [ARGS]...
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|


**Commands:**

|Usage|Description|
|---|---|
| _[neuro acl grant](#neuro-acl-grant)_| Shares resource with another user |
| _[neuro acl revoke](#neuro-acl-revoke)_| Revoke user access from another user |
| _[neuro acl list](#neuro-acl-list)_| List shared resources |
| _[neuro acl add-role](#neuro-acl-add-role)_| Add new role |
| _[neuro acl remove-role](#neuro-acl-remove-role)_| Remove existing role |




### neuro acl grant

Shares resource with another user.<br/><br/>URI shared resource.<br/><br/>USER username to share resource with.<br/><br/>PERMISSION sharing access right: read, write, or manage.<br/>

**Usage:**

```bash
neuro acl grant [OPTIONS] URI USER [read|write|manage]
```

**Examples:**

```bash

neuro acl grant storage:///sample_data/ alice manage
neuro acl grant image:resnet50 bob read
neuro acl grant job:///my_job_id alice write

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




### neuro acl revoke

Revoke user access from another user.<br/><br/>URI previously shared resource to revoke.<br/><br/>USER to revoke URI resource from.<br/>

**Usage:**

```bash
neuro acl revoke [OPTIONS] URI USER
```

**Examples:**

```bash

neuro acl revoke storage:///sample_data/ alice
neuro acl revoke image:resnet50 bob
neuro acl revoke job:///my_job_id alice

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




### neuro acl list

List shared resources.<br/><br/>The command displays a list of resources shared BY current user \(default).<br/><br/>To display a list of resources shared WITH current user apply --shared<br/>option.<br/>

**Usage:**

```bash
neuro acl list [OPTIONS] [URI]
```

**Examples:**

```bash

neuro acl list
neuro acl list storage://
neuro acl list --shared
neuro acl list --shared image://

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_\--full-uri_|Output full URI.|
|_\-s, --scheme TEXT_|Filter resources by scheme, e.g. job, storage, image or user. Deprecated, use the uri argument instead.|
|_--shared_|Output the resources shared by the user.|
|_-u TEXT_|Use specified user or role.|




### neuro acl add-role

Add new role.<br/>

**Usage:**

```bash
neuro acl add-role [OPTIONS] ROLE_NAME
```

**Examples:**

```bash

neuro acl add-role mycompany/subdivision

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




### neuro acl remove-role

Remove existing role.<br/>

**Usage:**

```bash
neuro acl remove-role [OPTIONS] ROLE_NAME
```

**Examples:**

```bash

neuro acl remove-role mycompany/subdivision

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




## neuro blob

Blob storage operations.

**Usage:**

```bash
neuro blob [OPTIONS] COMMAND [ARGS]...
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|


**Commands:**

|Usage|Description|
|---|---|
| _[neuro blob cp](#neuro-blob-cp)_| Simple utility to copy files and directories into and from Blob Storage |
| _[neuro blob ls](#neuro-blob-ls)_| List buckets or bucket contents |
| _[neuro blob glob](#neuro-blob-glob)_| List resources that match PATTERNS |




### neuro blob cp

Simple utility to copy files and directories into and from Blob Storage.<br/><br/>Either SOURCES or DESTINATION should have `blob://` scheme. If scheme is<br/>omitted, file:// scheme is assumed. It is currently not possible to copy<br/>files between Blob Storage \(`blob://`) destination, nor with `storage://`<br/>scheme paths.<br/><br/>Use `/dev/stdin` and `/dev/stdout` file names to upload a file from standard<br/>input or output to stdout.<br/><br/>Any number of \--exclude and --include options can be passed.  The filters<br/>that appear later in the command take precedence over filters that appear<br/>earlier in the command.  If neither \--exclude nor --include options are<br/>specified the default can be changed using the storage.cp-exclude<br/>configuration variable documented in "neuro help user-config".<br/><br/>File permissions, modification times and other attributes will not be passed<br/>to Blob Storage metadata during upload.

**Usage:**

```bash
neuro blob cp [OPTIONS] [SOURCES]... [DESTINATION]
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_--continue_|Continue copying partially-copied files. Only for copying from Blob Storage.|
|_\--exclude-from-files FILES_|A list of file names that contain patterns for exclusion files and directories. Used only for uploading. The default can be changed using the storage.cp\-exclude-from-files configuration variable documented in "neuro help user-config"|
|_--exclude_|Exclude files and directories that match the specified pattern.|
|_--include_|Don't exclude files and directories that match the specified pattern.|
|_\--glob / --no-glob_|Expand glob patterns in SOURCES with explicit scheme.  \[default: True]|
|_\-T, --no-target-directory_|Treat DESTINATION as a normal file.|
|_\-p, --progress / -P, --no-progress_|Show progress, on by default.|
|_\-r, --recursive_|Recursive copy, off by default|
|_\-t, --target-directory DIRECTORY_|Copy all SOURCES into DIRECTORY.|
|_\-u, --update_|Copy only when the SOURCE file is newer than the destination file or when the destination file is missing.|




### neuro blob ls

List buckets or bucket contents.

**Usage:**

```bash
neuro blob ls [OPTIONS] [PATHS]...
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_-l_|use a long listing format.|
|_\-h, --human-readable_|with -l print human readable sizes \(e.g., 2K, 540M).|
|_\-r, --recursive_|List all keys under the URL path provided, not just 1 level depths.|
|_--sort \[name &#124; size &#124; time]_|sort by given field, default is name.|




### neuro blob glob

List resources that match PATTERNS.

**Usage:**

```bash
neuro blob glob [OPTIONS] [PATTERNS]...
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




## neuro secret

Operations with secrets.

**Usage:**

```bash
neuro secret [OPTIONS] COMMAND [ARGS]...
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|


**Commands:**

|Usage|Description|
|---|---|
| _[neuro secret ls](#neuro-secret-ls)_| List secrets |
| _[neuro secret add](#neuro-secret-add)_| Add secret KEY with data VALUE |
| _[neuro secret rm](#neuro-secret-rm)_| Remove secret KEY |




### neuro secret ls

List secrets.

**Usage:**

```bash
neuro secret ls [OPTIONS]
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_\--full-uri_|Output full disk URI.|




### neuro secret add

Add secret KEY with data VALUE.<br/><br/>If VALUE starts with @ it points to a file with secrets content.<br/>

**Usage:**

```bash
neuro secret add [OPTIONS] KEY VALUE
```

**Examples:**

```bash

neuro secret add KEY_NAME VALUE
neuro secret add KEY_NAME @path/to/file.txt

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




### neuro secret rm

Remove secret KEY.

**Usage:**

```bash
neuro secret rm [OPTIONS] KEY
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




## neuro disk

Operations with disks.

**Usage:**

```bash
neuro disk [OPTIONS] COMMAND [ARGS]...
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|


**Commands:**

|Usage|Description|
|---|---|
| _[neuro disk ls](#neuro-disk-ls)_| List disks |
| _[neuro disk create](#neuro-disk-create)_| Create a disk with at least storage amount STORAGE |
| _[neuro disk get](#neuro-disk-get)_| Get disk DISK_ID |
| _[neuro disk rm](#neuro-disk-rm)_| Remove disk DISK_ID |




### neuro disk ls

List disks.

**Usage:**

```bash
neuro disk ls [OPTIONS]
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_\--full-uri_|Output full disk URI.|
|_\--long-format_|Output all info about disk.|




### neuro disk create

Create a disk with at least storage amount STORAGE.<br/><br/>To specify the amount, you can use the following suffixes: "kKMGTPEZY" To<br/>use decimal quantities, append "b" or "B". For example: - 1K or 1k is 1024<br/>bytes - 1Kb or 1KB is 1000 bytes - 20G is 20 * 2 ^ 30 bytes - 20Gb or 20GB<br/>is 20.000.000.000 bytes<br/><br/>Note that server can have big granularity \(for example, 1G) so it will<br/>possibly round-up the amount you requested.<br/>

**Usage:**

```bash
neuro disk create [OPTIONS] STORAGE
```

**Examples:**

```bash

neuro disk create 10G
neuro disk create 500M

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_--name NAME_|Optional disk name|
|_\--timeout-unused TIMEDELTA_|Optional disk lifetime limit after last usage in the format '1d2h3m4s' \(some parts may be missing). Set '0' to disable. Default value '1d' can be changed in the user config.|




### neuro disk get

Get disk DISK_ID.

**Usage:**

```bash
neuro disk get [OPTIONS] DISK
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_\--full-uri_|Output full disk URI.|




### neuro disk rm

Remove disk DISK_ID.

**Usage:**

```bash
neuro disk rm [OPTIONS] DISKS...
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




## neuro help

Get help on a command.

**Usage:**

```bash
neuro help [OPTIONS] [COMMAND]...
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




## neuro run

Run a job with predefined resources configuration.<br/><br/>IMAGE docker image name to run in a job.<br/><br/>CMD list will be passed as arguments to the executed job's image.<br/>

**Usage:**

```bash
neuro run [OPTIONS] IMAGE [CMD]...
```

**Examples:**

```bash

# Starts a container pytorch:latest on a machine with smaller GPU resources
# (see exact values in `neuro config show`) and with two volumes mounted:
#   storage:/<home-directory>   --> /var/storage/home (in read-write mode),
#   storage:/neuromation/public --> /var/storage/neuromation (in read-only mode).
neuro run --preset=gpu-small --volume=storage::/var/storage/home:rw \
--volume=storage:/neuromation/public:/var/storage/home:ro pytorch:latest

# Starts a container using the custom image my-ubuntu:latest stored in neuro
# registry, run /script.sh and pass arg1 and arg2 as its arguments:
neuro run -s cpu-small image:my-ubuntu:latest --entrypoint=/script.sh arg1 arg2

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_--browse_|Open a job's URL in a web browser|
|_\-d, --description DESC_|Optional job description in free format|
|_--detach_|Don't attach to job logs and don't wait for exit code|
|_--entrypoint TEXT_|Executable entrypoint in the container \(note that it overwrites `ENTRYPOINT` and `CMD` instructions of the docker image)|
|_\-e, --env VAR=VAL_|Set environment variable in container. Use multiple options to define more than one variable. See `neuro help secrets` for information about passing secrets as environment variables.|
|_\--env-file PATH_|File with environment variables to pass|
|_\-x, --extshm / -X, --no-extshm_|Request extended '/dev/shm' space  \[default: True]|
|_--http PORT_|Enable HTTP port forwarding to container  \[default: 80]|
|_\--http-auth / --no-http-auth_|Enable HTTP authentication for forwarded HTTP port  \[default: True]|
|_\--life-span TIMEDELTA_|Optional job run-time limit in the format '1d2h3m4s' \(some parts may be missing). Set '0' to disable. Default value '1d' can be changed in the user config.|
|_\-n, --name NAME_|Optional job name|
|_\--pass-config / --no-pass-config_|Upload neuro config to the job  \[default: False]|
|_\--port-forward LOCAL\_PORT:REMOTE_RORT_|Forward port\(s) of a running job to local port\(s) \(use multiple times for forwarding several ports)|
|_\-s, --preset PRESET_|Predefined resource configuration \(to see available values, run `neuro config show`)|
|_--privileged_|Run job in privileged mode, if it is supported by cluster.  \[default: False]|
|_\-q, --quiet_|Run command in quiet mode \(DEPRECATED)|
|_\--restart \[never &#124; on-failure &#124; always]_|Restart policy to apply when a job exits  \[default: never]|
|_\--schedule-timeout TIMEDELTA_|Optional job schedule timeout in the format '3m4s' \(some parts may be missing).|
|_--share USER_|Share job write permissions to user or role.|
|_--tag TAG_|Optional job tag, multiple values allowed|
|_\-t, --tty / -T, --no-tty_|Allocate a TTY, can be useful for interactive jobs. By default is on if the command is executed from a terminal, non-tty mode is used if executed from a script.|
|_\-v, --volume MOUNT_|Mounts directory from vault into container. Use multiple options to mount more than one volume. See `neuro help secrets` for information about passing secrets as mounted files.|
|_\--wait-for-seat / --no-wait-for-seat_|Wait for total running jobs quota  \[default: False]|
|_\--wait-start / --no-wait-start_|Wait for a job start or failure  \[default: True]|
|_\-w, --workdir TEXT_|Working directory inside the container|




## neuro ps

List all jobs.<br/>

**Usage:**

```bash
neuro ps [OPTIONS]
```

**Examples:**

```bash

neuro ps -a
neuro ps -a --owner=user-1 --owner=user-2
neuro ps --name my-experiments-v1 -s failed -s succeeded
neuro ps --description=my favourite job
neuro ps -s failed -s succeeded -q
neuro ps -t tag1 -t tag2

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_\-a, --all_|Show all jobs regardless the status.|
|_\-d, --description DESCRIPTION_|Filter out jobs by description \(exact match).|
|_--distinct_|Show only first job if names are same.|
|_--format COLUMNS_|Output table format, see "neuro help ps\-format" for more info about the format specification. The default can be changed using the job.ps-format configuration variable documented in "neuro help user-config"|
|_\--full-uri_|Output full image URI.|
|_\-n, --name NAME_|Filter out jobs by name.|
|_\-o, --owner TEXT_|Filter out jobs by owner \(multiple option). Supports `ME` option to filter by the current user.|
|_\-q, --quiet_|Run command in quiet mode \(DEPRECATED)|
|_\--recent-first / --recent-last_|Show newer jobs first or last|
|_--since DATE\_OR_TIMEDELTA_|Show jobs created after a specific date \(including). Use value of format '1d2h3m4s' to specify moment in past relatively to current time.|
|_\-s, --status \[pending &#124; suspended &#124; running &#124; succeeded &#124; failed &#124; cancelled]_|Filter out jobs by status \(multiple option).|
|_\-t, --tag TAG_|Filter out jobs by tag \(multiple option)|
|_--until DATE\_OR_TIMEDELTA_|Show jobs created before a specific date \(including). Use value of format '1d2h3m4s' to specify moment in past relatively to current time.|
|_\-w, --wide_|Do not cut long lines for terminal width.|




## neuro status

Display status of a job.

**Usage:**

```bash
neuro status [OPTIONS] JOB
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_\--full-uri_|Output full URI.|




## neuro exec

Execute command in a running job.<br/>

**Usage:**

```bash
neuro exec [OPTIONS] JOB CMD...
```

**Examples:**

```bash

# Provides a shell to the container:
neuro exec my-job /bin/bash

# Executes a single command in the container and returns the control:
neuro exec --no-tty my-job ls -l

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_\-t, --tty / -T, --no-tty_|Allocate a TTY, can be useful for interactive jobs. By default is on if the command is executed from a terminal, non-tty mode is used if executed from a script.|




## neuro port-forward

Forward port\(s) of a running job to local port\(s).<br/>

**Usage:**

```bash
neuro port-forward [OPTIONS] JOB LOCAL_PORT:REMOTE_RORT...
```

**Examples:**

```bash

# Forward local port 2080 to port 80 of job's container.
# You can use http://localhost:2080 in browser to access job's served http
neuro job port-forward my-fastai-job 2080:80

# Forward local port 2222 to job's port 22
# Then copy all data from container's folder '/data' to current folder
# (please run second command in other terminal)
neuro job port-forward my-job-with-ssh-server 2222:22
rsync -avxzhe ssh -p 2222 root@localhost:/data .

# Forward few ports at once
neuro job port-forward my-job 2080:80 2222:22 2000:100

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




## neuro attach

Attach local standard input, output, and error streams to a running job.

**Usage:**

```bash
neuro attach [OPTIONS] JOB
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_\--port-forward LOCAL\_PORT:REMOTE_RORT_|Forward port\(s) of a running job to local port\(s) \(use multiple times for forwarding several ports)|




## neuro logs

Print the logs for a job.

**Usage:**

```bash
neuro logs [OPTIONS] JOB
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




## neuro kill

Kill job\(s).

**Usage:**

```bash
neuro kill [OPTIONS] JOBS...
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




## neuro top

Display GPU/CPU/Memory usage.<br/>

**Usage:**

```bash
neuro top [OPTIONS] [JOBS]...
```

**Examples:**

```bash

neuro top
neuro top job-1 job-2
neuro top --owner=user-1 --owner=user-2
neuro top --name my-experiments-v1
neuro top -t tag1 -t tag2

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_\-d, --description DESCRIPTION_|Filter out jobs by description \(exact match).|
|_--format COLUMNS_|Output table format, see "neuro help top\-format" for more info about the format specification. The default can be changed using the job.top-format configuration variable documented in "neuro help user-config"|
|_\--full-uri_|Output full image URI.|
|_\-n, --name NAME_|Filter out jobs by name.|
|_\-o, --owner TEXT_|Filter out jobs by owner \(multiple option). Supports `ME` option to filter by the current user. Specify `ALL` to show jobs of all users.|
|_--since DATE\_OR_TIMEDELTA_|Show jobs created after a specific date \(including). Use value of format '1d2h3m4s' to specify moment in past relatively to current time.|
|_--sort COLUMNS_|Sort rows by specified column. Add "-" prefix to revert the sorting order. Multiple columns can be specified \(comma separated).  \[default: cpu]|
|_\-t, --tag TAG_|Filter out jobs by tag \(multiple option)|
|_--timeout FLOAT_|Maximum allowed time for executing the command, 0 for no timeout  \[default: 0]|
|_--until DATE\_OR_TIMEDELTA_|Show jobs created before a specific date \(including). Use value of format '1d2h3m4s' to specify moment in past relatively to current time.|




## neuro save

Save job's state to an image.<br/>

**Usage:**

```bash
neuro save [OPTIONS] JOB IMAGE
```

**Examples:**

```bash

neuro job save job-id image:ubuntu-patched
neuro job save my-favourite-job image:ubuntu-patched:v1
neuro job save my-favourite-job image://bob/ubuntu-patched

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




## neuro login

Log into Neuro Platform.<br/><br/>URL is a platform entrypoint URL.

**Usage:**

```bash
neuro login [OPTIONS] [URL]
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




## neuro logout

Log out.

**Usage:**

```bash
neuro logout [OPTIONS]
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|




## neuro cp

Copy files and directories.<br/><br/>Either SOURCES or DESTINATION should have storage:// scheme. If scheme is<br/>omitted, file:// scheme is assumed.<br/><br/>Use /dev/stdin and /dev/stdout file names to copy a file from terminal and<br/>print the content of file on the storage to console.<br/><br/>Any number of \--exclude and --include options can be passed.  The filters<br/>that appear later in the command take precedence over filters that appear<br/>earlier in the command.  If neither \--exclude nor --include options are<br/>specified the default can be changed using the storage.cp-exclude<br/>configuration variable documented in "neuro help user-config".<br/>

**Usage:**

```bash
neuro cp [OPTIONS] [SOURCES]... [DESTINATION]
```

**Examples:**

```bash

# copy local files into remote storage root
neuro cp foo.txt bar/baz.dat storage:
neuro cp foo.txt bar/baz.dat -t storage:

# copy local directory `foo` into existing remote directory `bar`
neuro cp -r foo -t storage:bar

# copy the content of local directory `foo` into existing remote
# directory `bar`
neuro cp -r -T storage:foo storage:bar

# download remote file `foo.txt` into local file `/tmp/foo.txt` with
# explicit file:// scheme set
neuro cp storage:foo.txt file:///tmp/foo.txt
neuro cp -T storage:foo.txt file:///tmp/foo.txt
neuro cp storage:foo.txt file:///tmp
neuro cp storage:foo.txt -t file:///tmp

# download other user's remote file into the current directory
neuro cp storage://{username}/foo.txt .

# download only files with extension `.out` into the current directory
neuro cp storage:results/*.out .

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_--continue_|Continue copying partially-copied files.|
|_\--exclude-from-files FILES_|A list of file names that contain patterns for exclusion files and directories. Used only for uploading. The default can be changed using the storage.cp\-exclude-from-files configuration variable documented in "neuro help user-config"|
|_--exclude_|Exclude files and directories that match the specified pattern.|
|_--include_|Don't exclude files and directories that match the specified pattern.|
|_\--glob / --no-glob_|Expand glob patterns in SOURCES with explicit scheme.  \[default: True]|
|_\-T, --no-target-directory_|Treat DESTINATION as a normal file.|
|_\-p, --progress / -P, --no-progress_|Show progress, on by default in TTY mode, off otherwise.|
|_\-r, --recursive_|Recursive copy, off by default|
|_\-t, --target-directory DIRECTORY_|Copy all SOURCES into DIRECTORY.|
|_\-u, --update_|Copy only when the SOURCE file is newer than the destination file or when the destination file is missing.|




## neuro ls

List directory contents.<br/><br/>By default PATH is equal user's home dir \(storage:)

**Usage:**

```bash
neuro ls [OPTIONS] [PATHS]...
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_\-d, --directory_|list directories themselves, not their contents.|
|_-l_|use a long listing format.|
|_\-h, --human-readable_|with -l print human readable sizes \(e.g., 2K, 540M).|
|_\-a, --all_|do not ignore entries starting with .|
|_--sort \[name &#124; size &#124; time]_|sort by given field, default is name.|




## neuro rm

Remove files or directories.<br/>

**Usage:**

```bash
neuro rm [OPTIONS] PATHS...
```

**Examples:**

```bash

neuro rm storage:foo/bar
neuro rm storage://{username}/foo/bar
neuro rm --recursive storage://{username}/foo/
neuro rm storage:foo/**/*.tmp

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_\--glob / --no-glob_|Expand glob patterns in PATHS  \[default: True]|
|_\-p, --progress / -P, --no-progress_|Show progress, on by default in TTY mode, off otherwise.|
|_\-r, --recursive_|remove directories and their contents recursively|




## neuro mkdir

Make directories.

**Usage:**

```bash
neuro mkdir [OPTIONS] PATHS...
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_\-p, --parents_|No error if existing, make parent directories as needed|




## neuro mv

Move or rename files and directories.<br/><br/>SOURCE must contain path to the file or directory existing on the storage,<br/>and DESTINATION must contain the full path to the target file or directory.<br/>

**Usage:**

```bash
neuro mv [OPTIONS] [SOURCES]... [DESTINATION]
```

**Examples:**

```bash

# move and rename remote file
neuro mv storage:foo.txt storage:bar/baz.dat
neuro mv -T storage:foo.txt storage:bar/baz.dat

# move remote files into existing remote directory
neuro mv storage:foo.txt storage:bar/baz.dat storage:dst
neuro mv storage:foo.txt storage:bar/baz.dat -t storage:dst

# move the content of remote directory into other existing
# remote directory
neuro mv -T storage:foo storage:bar

# move remote file into other user's directory
neuro mv storage:foo.txt storage://{username}/bar.dat

# move remote file from other user's directory
neuro mv storage://{username}/foo.txt storage:bar.dat

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_\--glob / --no-glob_|Expand glob patterns in SOURCES  \[default: True]|
|_\-T, --no-target-directory_|Treat DESTINATION as a normal file|
|_\-t, --target-directory DIRECTORY_|Copy all SOURCES into DIRECTORY|




## neuro images

List images.

**Usage:**

```bash
neuro images [OPTIONS]
```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_-l_|List in long format.|
|_\--full-uri_|Output full image URI.|
|_\-n, --name NAME_|Filter out images by name.|
|_\-o, --owner TEXT_|Filter out images by owner \(multiple option). Supports `ME` option to filter by the current user.|




## neuro push

Push an image to platform registry.<br/><br/>Remote image must be URL with image:// scheme. Image names can contain tag.<br/>If tags not specified 'latest' will be used as value.<br/>

**Usage:**

```bash
neuro push [OPTIONS] LOCAL_IMAGE [REMOTE_IMAGE]
```

**Examples:**

```bash

neuro push myimage
neuro push alpine:latest image:my-alpine:production
neuro push alpine image://myfriend/alpine:shared

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_\-q, --quiet_|Run command in quiet mode \(DEPRECATED)|




## neuro pull

Pull an image from platform registry.<br/><br/>Remote image name must be URL with image:// scheme. Image names can contain<br/>tag.<br/>

**Usage:**

```bash
neuro pull [OPTIONS] REMOTE_IMAGE [LOCAL_IMAGE]
```

**Examples:**

```bash

neuro pull image:myimage
neuro pull image://myfriend/alpine:shared
neuro pull image://username/my-alpine:production alpine:from-registry

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|
|_\-q, --quiet_|Run command in quiet mode \(DEPRECATED)|




## neuro share

Shares resource with another user.<br/><br/>URI shared resource.<br/><br/>USER username to share resource with.<br/><br/>PERMISSION sharing access right: read, write, or manage.<br/>

**Usage:**

```bash
neuro share [OPTIONS] URI USER [read|write|manage]
```

**Examples:**

```bash

neuro acl grant storage:///sample_data/ alice manage
neuro acl grant image:resnet50 bob read
neuro acl grant job:///my_job_id alice write

```

**Options:**

Name | Description|
|----|------------|
|_--help_|Show this message and exit.|


