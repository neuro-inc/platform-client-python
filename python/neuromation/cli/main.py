import logging
import os
import sys
from pathlib import Path

import aiohttp
from aiodocker.exceptions import DockerError
from yarl import URL

import neuromation
from neuromation.cli.command_handlers import PlatformStorageOperation
from neuromation.cli.formatter import JobStatusFormatter, OutputFormatter
from neuromation.cli.rc import Config
from neuromation.clientv2 import (
    Action,
    ClientV2,
    Image,
    NetworkPortForwarding,
    Permission,
    Resources,
    Volume,
)
from neuromation.logging import ConsoleWarningFormatter
from neuromation.strings.parse import to_megabytes_str

from . import rc
from .command_progress_report import ProgressBase
from .commands import command, dispatch
from .defaults import DEFAULTS
from .docker_handler import DockerHandler
from .formatter import JobListFormatter, StorageLsFormatter
from .ssh_utils import connect_ssh, remote_debug


# For stream copying from file to http or from http to file
BUFFER_SIZE_MB = 16

log = logging.getLogger(__name__)
console_handler = logging.StreamHandler(sys.stderr)


def setup_logging():
    root_logger = logging.getLogger()
    root_logger.addHandler(console_handler)
    root_logger.setLevel(logging.DEBUG)

    # Select modules logging, if necessary
    # logging.getLogger("aiohttp.internal").propagate = False
    # logging.getLogger("aiohttp.client").setLevel(logging.DEBUG)


def setup_console_handler(handler, verbose, noansi=False):
    if not handler.stream.closed and handler.stream.isatty() and noansi is False:
        format_class = ConsoleWarningFormatter
    else:
        format_class = logging.Formatter

    if verbose:
        handler.setFormatter(format_class("%(name)s.%(funcName)s: %(message)s"))
        loglevel = logging.DEBUG
    else:
        handler.setFormatter(format_class())
        loglevel = logging.INFO

    handler.setLevel(loglevel)


@command
def neuro(url, token, verbose, show_traceback, version):
    """    ◣
    ▇ ◣
    ▇ ◥ ◣
  ◣ ◥   ▇
  ▇ ◣   ▇
  ▇ ◥ ◣ ▇
  ▇   ◥ ▇    Neuromation Platform
  ▇   ◣ ◥
  ◥ ◣ ▇      Deep network training,
    ◥ ▇      inference and datasets
      ◥
Usage:
  neuro [options] COMMAND

Options:
  -u, --url URL         Override API URL [default: {api_url}]
  -t, --token TOKEN     API authentication token (not implemented)
  --verbose             Enable verbose logging
  --show-traceback      Show Python traceback on exception
  -v, --version         Print version and exit

Commands:
  model                 Model training, testing and inference
  job                   Manage existing jobs
  store                 Storage operations
  image                 Docker container image operations
  config                Configure API connection settings
  completion            Generate code to enable completion
  share                 Resource sharing management
  help                  Get help on a command
"""

    @command
    def config():
        """
        Usage:
            neuro config COMMAND

        Client configuration settings commands

        Commands:
            url             Updates API URL
            auth            Updates API Token
            forget          Forget stored API Token
            id_rsa          Updates path to Github RSA token,
                            in use for SSH/Remote debug
            show            Print current settings
        """

        @command
        def url(url):
            """
            Usage:
                neuro config url URL

            Updates settings with provided platform URL.

            Examples:
            neuro config url https://platform.neuromation.io/api/v1
            """
            rc.ConfigFactory.update_api_url(url)

        @command
        def id_rsa(file):
            """
            Usage:
                neuro config id_rsa FILE

            Updates path to id_rsa file with private key.
            File is being used for accessing remote shell, remote debug.

            Note: this is temporal and going to be
            replaced in future by JWT token.
            """
            if not os.path.exists(file) or not os.path.isfile(file):
                print(f"File does not exist id_rsa={file}.")
                return

            rc.ConfigFactory.update_github_rsa_path(file)

        @command
        def show():
            """
            Usage:
                neuro config show

            Prints current settings.
            """
            config = rc.ConfigFactory.load()
            print(config)

        @command
        def auth(token):
            """
            Usage:
                neuro config auth TOKEN

            Updates authorization token
            """
            # TODO (R Zubairov, 09/13/2018): check token correct
            # connectivity, check with Alex
            # Do not overwrite token in case new one does not work
            # TODO (R Zubairov, 09/13/2018): on server side we shall implement
            # protection against brute-force
            rc.ConfigFactory.update_auth_token(token=token)

        @command
        def forget():
            """
            Usage:
                neuro config forget

            Forget authorization token
            """
            rc.ConfigFactory.forget_auth_token()

        return locals()

    @command
    def store():
        """
        Usage:
            neuro store COMMAND

        Storage operations

        Commands:
          rm                 Remove files or directories
          ls                 List directory contents
          cp                 Copy files and directories
          mv                 Move or rename files and directories
          mkdir              Make directories
        """

        @command
        async def rm(path):
            """
            Usage:
                neuro store rm PATH

            Remove files or directories.

            Examples:
            neuro store rm storage:///foo/bar/
            neuro store rm storage:/foo/bar/
            neuro store rm storage://{username}/foo/bar/
            """
            uri = URL(path)

            async with ClientV2(url, token) as client:
                await client.storage.rm(uri)

        @command
        async def ls(path):
            """
            Usage:
                neuro store ls [PATH]

            List directory contents
            By default PATH is equal user`s home dir (storage:)
            """
            if path is None:
                uri = URL("storage://~")
            else:
                uri = URL(path)

            async with ClientV2(url, token) as client:
                res = await client.storage.ls(uri)

            return StorageLsFormatter().format_ls(res)

        @command
        async def cp(source, destination, recursive, progress):
            """
            Usage:
                neuro store cp [options] SOURCE DESTINATION

            Copy files and directories
            Either SOURCE or DESTINATION should have storage:// scheme.
            If scheme is omitted, file:// scheme is assumed.

            Options:
              -r, --recursive             Recursive copy
              -p, --progress              Show progress

            Examples:

            # copy local file ./foo into remote storage root
            neuro store cp ./foo storage:///
            neuro store cp ./foo storage:/

            # download remote file foo into local file foo with
            # explicit file:// scheme set
            neuro store cp storage:///foo file:///foo
            """
            timeout = aiohttp.ClientTimeout(
                total=None, connect=None, sock_read=None, sock_connect=30
            )
            src = URL(source)
            dst = URL(destination)

            log.debug(f"src={src}")
            log.debug(f"dst={dst}")

            progress = ProgressBase.create_progress(progress)
            if not src.scheme:
                src = URL("file:" + src.path)
            if not dst.scheme:
                dst = URL("file:" + dst.path)
            async with ClientV2(url, token, timeout=timeout) as client:
                if src.scheme == "file" and dst.scheme == "storage":
                    if recursive:
                        await client.storage.upload_dir(progress, src, dst)
                    else:
                        await client.storage.upload_file(progress, src, dst)
                elif src.scheme == "storage" and dst.scheme == "file":
                    if recursive:
                        await client.storage.download_dir(progress, src, dst)
                    else:
                        await client.storage.download_file(progress, src, dst)
                else:
                    raise RuntimeError(
                        f"Copy operation for {src} -> {dst} is not supported"
                    )

        @command
        async def mkdir(path):
            """
            Usage:
                neuro store mkdir PATH

            Make directories
            """

            uri = URL(path)

            async with ClientV2(url, token) as client:
                await client.storage.mkdirs(uri)

        @command
        async def mv(source, destination):
            """
            Usage:
                neuro store mv SOURCE DESTINATION

            Move or rename files and directories. SOURCE must contain path to the
            file or directory existing on the storage, and DESTINATION must contain
            the full path to the target file or directory.


            Examples:

            # move or rename remote file
            neuro store mv storage://{username}/foo.txt storage://{username}/bar.txt
            neuro store mv storage://{username}/foo.txt storage://~/bar/baz/foo.txt

            # move or rename remote directory
            neuro store mv storage://{username}/foo/ storage://{username}/bar/
            neuro store mv storage://{username}/foo/ storage://{username}/bar/baz/foo/
            """

            src = URL(source)
            dst = URL(destination)

            async with ClientV2(url, token) as client:
                await client.storage.mv(src, dst)

        return locals()

    @command
    def model():
        """
        Usage:
            neuro model COMMAND

        Model operations

        Commands:
          train              Start model training
          debug              Prepare debug tunnel for PyCharm
        """

        @command
        async def train(
            image,
            dataset,
            results,
            gpu,
            gpu_model,
            cpu,
            memory,
            extshm,
            http,
            ssh,
            cmd,
            preemptible,
            non_preemptible,
            description,
            quiet,
        ):
            """
            Usage:
                neuro model train [options] IMAGE DATASET RESULTS [CMD...]

            Start training job using model from IMAGE, dataset from DATASET and
            store output weights in RESULTS.

            COMMANDS list will be passed as commands to model container.

            Options:
                -g, --gpu NUMBER          Number of GPUs to request \
[default: {model_train_gpu_number}]
                --gpu-model MODEL         GPU to use [default: {model_train_gpu_model}]
                                          Other options available are
                                              nvidia-tesla-k80
                                              nvidia-tesla-p4
                                              nvidia-tesla-v100
                -c, --cpu NUMBER          Number of CPUs to request \
[default: {model_train_cpu_number}]
                -m, --memory AMOUNT       Memory amount to request \
[default: {model_train_memory_amount}]
                -x, --extshm              Request extended '/dev/shm' space
                --http NUMBER             Enable HTTP port forwarding to container
                --ssh NUMBER              Enable SSH port forwarding to container
                --preemptible             Run job on a lower-cost preemptible instance
                --non-preemptible         Force job to run on a non-preemptible instance
                -d, --description DESC    Add optional description to the job
                -q, --quiet               Run command in quiet mode (print only job id)
            """

            def get_preemptible():  # pragma: no cover
                if preemptible and non_preemptible:
                    raise neuromation.client.IllegalArgumentError(
                        "Incompatible options: --preemptible and --non-preemptible"
                    )
                return preemptible or not non_preemptible  # preemptible by default

            is_preemptible = get_preemptible()

            config: Config = rc.ConfigFactory.load()
            username = config.get_platform_user_name()
            pso = PlatformStorageOperation(username)

            try:
                dataset_url = URL(
                    "storage:/" + str(pso.render_uri_path_with_principal(dataset))
                )
            except ValueError:
                raise ValueError(
                    f"Dataset path should be on platform. " f"Current value {dataset}"
                )

            try:
                resultset_url = URL(
                    "storage:/" + str(pso.render_uri_path_with_principal(results))
                )
            except ValueError:
                raise ValueError(
                    f"Results path should be on platform. " f"Current value {results}"
                )

            network = NetworkPortForwarding.from_cli(http, ssh)
            memory = to_megabytes_str(memory)
            resources = Resources.create(cpu, gpu, gpu_model, memory, extshm)

            cmd = " ".join(cmd) if cmd is not None else None
            log.debug(f'cmd="{cmd}"')

            image = Image(image=image, command=cmd)

            async with ClientV2(url, token) as client:
                res = await client.models.train(
                    image=image,
                    resources=resources,
                    dataset=dataset_url,
                    results=resultset_url,
                    description=description,
                    network=network,
                    is_preemptible=is_preemptible,
                )
                job = await client.jobs.status(res.id)

            return OutputFormatter.format_job(job, quiet)

        @command
        async def debug(id, localport):
            """
            Usage:
                neuro model debug [options] ID

            Starts ssh terminal connected to running job.
            Job should be started with SSH support enabled.

            Options:
                --localport NUMBER    Local port number for debug \
[default: {model_debug_local_port}]

            Examples:
            neuro model debug --localport 12789 job-abc-def-ghk
            """
            config: Config = rc.ConfigFactory.load()
            git_key = config.github_rsa_path

            async with ClientV2(url, token) as client:
                await remote_debug(client, id, git_key, localport)

        return locals()

    @command
    def job():
        """
        Usage:
            neuro job COMMAND

        Model operations

        Commands:
          submit              Starts Job on a platform
          monitor             Monitor job output stream
          list                List all jobs
          status              Display status of a job
          kill                Kill job
          ssh                 Start SSH terminal
        """

        @command
        async def submit(
            image,
            gpu,
            gpu_model,
            cpu,
            memory,
            extshm,
            http,
            ssh,
            cmd,
            volume,
            env,
            env_file,
            preemptible,
            non_preemptible,
            description,
            quiet,
        ):
            """
            Usage:
                neuro job submit [options] [--volume MOUNT]...
                      [--env VAR=VAL]... IMAGE [CMD...]

            Start job using IMAGE

            COMMANDS list will be passed as commands to model container.

            Options:
                -g, --gpu NUMBER          Number of GPUs to request \
[default: {job_submit_gpu_number}]
                --gpu-model MODEL         GPU to use [default: {job_submit_gpu_model}]
                                          Other options available are
                                              nvidia-tesla-k80
                                              nvidia-tesla-p4
                                              nvidia-tesla-v100
                -c, --cpu NUMBER          Number of CPUs to request \
[default: {job_submit_cpu_number}]
                -m, --memory AMOUNT       Memory amount to request \
[default: {job_submit_memory_amount}]
                -x, --extshm              Request extended '/dev/shm' space
                --http NUMBER             Enable HTTP port forwarding to container
                --ssh NUMBER              Enable SSH port forwarding to container
                --volume MOUNT...         Mounts directory from vault into container
                                          Use multiple options to mount more than one \
volume
                -e, --env VAR=VAL...      Set environment variable in container
                                          Use multiple options to define more than one \
variable
                --env-file FILE           File with environment variables to pass
                --preemptible             Force job to run on a preemptible instance
                --non-preemptible         Force job to run on a non-preemptible instance
                -d, --description DESC    Add optional description to the job
                -q, --quiet               Run command in quiet mode (print only job id)


            Examples:
            # Starts a container pytorch:latest with two paths mounted. Directory /q1/
            # is mounted in read only mode to /qm directory within container.
            # Directory /mod mounted to /mod directory in read-write mode.
            neuro job submit --volume storage:/q1:/qm:ro --volume storage:/mod:/mod:rw \
pytorch:latest

            # Starts a container pytorch:latest with connection enabled to port 22 and
            # sets PYTHONPATH environment value to /python.
            # Please note that SSH server should be provided by container.
            neuro job submit --env PYTHONPATH=/python --volume \
storage:/data/2018q1:/data:ro --ssh 22 pytorch:latest
            """

            def get_preemptible():  # pragma: no cover
                if preemptible and non_preemptible:
                    raise neuromation.client.IllegalArgumentError(
                        "Incompatible options: --preemptible and --non-preemptible"
                    )
                return preemptible or not non_preemptible  # preemptible by default

            is_preemptible = get_preemptible()

            config: Config = rc.ConfigFactory.load()
            username = config.get_platform_user_name()

            # TODO (Alex Davydow 12.12.2018): Consider splitting env logic into
            # separate function.
            if env_file:
                with open(env_file, "r") as ef:
                    env = ef.read().splitlines() + env

            env_dict = {}
            for line in env:
                splited = line.split("=", 1)
                if len(splited) == 1:
                    val = os.environ.get(splited[0], "")
                    env_dict[splited[0]] = val
                else:
                    env_dict[splited[0]] = splited[1]

            cmd = " ".join(cmd) if cmd is not None else None
            log.debug(f'cmd="{cmd}"')

            memory = to_megabytes_str(memory)
            image = Image(image=image, command=cmd)
            network = NetworkPortForwarding.from_cli(http, ssh)
            resources = Resources.create(cpu, gpu, gpu_model, memory, extshm)
            volumes = Volume.from_cli_list(username, volume)

            async with ClientV2(url, token) as client:
                job = await client.jobs.submit(
                    image=image,
                    resources=resources,
                    network=network,
                    volumes=volumes,
                    is_preemptible=is_preemptible,
                    description=description,
                    env=env_dict,
                )
                return OutputFormatter.format_job(job, quiet)

        @command
        async def ssh(id, user, key):
            """
            Usage:
                neuro job ssh [options] ID

            Starts ssh terminal connected to running job.
            Job should be started with SSH support enabled.

            Options:
                --user STRING         Container user name [default: {job_ssh_user}]
                --key STRING          Path to container private key.

            Examples:
            neuro job ssh --user alfa --key ./my_docker_id_rsa job-abc-def-ghk
            """
            config: Config = rc.ConfigFactory.load()
            git_key = config.github_rsa_path

            async with ClientV2(url, token) as client:
                await connect_ssh(client, id, git_key, user, key)

        @command
        async def monitor(id):
            """
            Usage:
                neuro job monitor ID

            Monitor job output stream
            """
            timeout = aiohttp.ClientTimeout(
                total=None, connect=None, sock_read=None, sock_connect=30
            )

            async with ClientV2(url, token, timeout=timeout) as client:
                async for chunk in client.jobs.monitor(id):
                    if not chunk:
                        break
                    sys.stdout.write(chunk.decode(errors="ignore"))

        @command
        async def list(status, description, quiet):
            """
            Usage:
                neuro job list [options]

            Options:
              -s, --status (pending|running|succeeded|failed|all)
                  Filter out job by status(es) (comma delimited if multiple)
              -d, --description DESCRIPTION
                  Filter out job by job description (exact match)
              -q, --quiet
                  Run command in quiet mode (print only job ids)

            List all jobs

            Examples:
            neuro job list --description="my favourite job"
            neuro job list --status=all
            neuro job list --status=pending,running --quiet
            """

            status = status or "running,pending"

            # TODO: add validation of status values
            statuses = set(status.split(","))
            if "all" in statuses:
                statuses = set()

            async with ClientV2(url, token) as client:
                jobs = await client.jobs.list()

            formatter = JobListFormatter(quiet=quiet)
            return formatter.format_jobs(jobs, statuses, description)

        @command
        async def status(id):
            """
            Usage:
                neuro job status ID

            Display status of a job
            """
            async with ClientV2(url, token) as client:
                res = await client.jobs.status(id)
                return JobStatusFormatter.format_job_status(res)

        @command
        async def kill(job_ids):
            """
            Usage:
                neuro job kill JOB_IDS...

            Kill job(s)
            """
            errors = []
            async with ClientV2(url, token) as client:
                for job in job_ids:
                    try:
                        await client.jobs.kill(job)
                        print(job)
                    except ValueError as e:
                        errors.append((job, e))

            def format_fail(job: str, reason: Exception) -> str:
                return f"Cannot kill job {job}: {reason}"

            for job, error in errors:
                print(format_fail(job, error))

        return locals()

    @command
    def image():
        """
        Usage:
            neuro image COMMAND

        Docker image operations

        Commands:
          push                 Push docker image from local machine to cloud registry.
          pull                 Pull docker image from cloud registry to local machine.
        """

        @command
        async def push(image_name, remote_image_name):
            """
            Usage:
                neuro image push IMAGE_NAME [REMOTE_IMAGE_NAME]

            Push an image to platform registry.
            Image names can contains tag. If tags not specified 'latest' will \
be used as value

            Examples:
                neuro image push myimage
                neuro image push alpine:latest my-alpine:production
                neuro image push alpine image://myfriend/alpine:shared

            """
            config = rc.ConfigFactory.load()
            platform_user_name = config.get_platform_user_name()

            async with DockerHandler(
                platform_user_name, config.auth, config.docker_registry_url()
            ) as handler:
                await handler.push(image_name, remote_image_name)

        @command
        async def pull(image_name, local_image_name):
            """
            Usage:
                neuro image pull IMAGE_NAME [LOCAL_IMAGE_NAME]

            Pull an image from platform registry.
            Image names can contain tag.

            Examples:
                neuro image pull myimage
                neuro image pull image://myfriend/alpine:shared
                neuro image pull my-alpine:production alpine:from-registry

            """
            config = rc.ConfigFactory.load()
            platform_user_name = config.get_platform_user_name()
            async with DockerHandler(
                platform_user_name, config.auth, config.docker_registry_url()
            ) as handler:
                await handler.pull(image_name, local_image_name)

        return locals()

    @command
    async def share(uri, user, permission: str):
        """
            Usage:
                neuro share URI USER PERMISSION

            Shares resource specified by URI to a USER with PERMISSION \
(read|write|manage)

            Examples:
            neuro share storage:///sample_data/ alice manage
            neuro share image://{username}/resnet50 bob read
            neuro share image:resnet50 bob read
            neuro share job:///my_job_id alice write
        """
        uri = URL(uri)
        try:
            action = Action[permission.upper()]
        except KeyError as error:
            raise ValueError(
                "Resource not shared. Please specify one of read/write/manage."
            ) from error
        config = rc.ConfigFactory.load()
        platform_user_name = config.get_platform_user_name()
        permission = Permission.from_cli(
            username=platform_user_name, uri=uri, action=action
        )

        async with ClientV2(url, token) as client:
            try:
                await client.users.share(user, permission)
            except neuromation.client.IllegalArgumentError as error:
                raise ValueError(
                    "Resource not shared. Please verify resource-uri, user name."
                ) from error
        return "Resource shared."

    @command
    def completion():
        """
            Usage:
                neuro completion COMMAND

            Generates code to enable bash-completion.

            Commands:
                generate     Generate code enabling bash-completion.
                             eval $(neuro completion generate) enables completion
                             for the current session.
                             Adding eval $(neuro completion generate) to
                             .bashrc_profile enables completion permanently.
                patch        Automatically patch .bash_profile to enable completion
        """
        neuromation_dir = Path(__file__).parent.parent
        completion_file = neuromation_dir / "completion" / "completion.bash"
        activate_completion = "source '{}'".format(str(completion_file))

        @command
        def generate():
            """
               Usage:
                   neuro completion generate

               Generate code enabling bash-completion.
               eval $(neuro completion generate) enables completion for the current
               session.
               Adding eval $(neuro completion generate) to .bashrc_profile enables
               completion permanently.
            """
            print(activate_completion)

        @command
        def patch():
            """
               Usage:
                   neuro completion patch

               Automatically patch .bash_profile to enable completion
            """
            bash_profile_file = Path.home() / ".bash_profile"
            with bash_profile_file.open("a+") as bash_profile:
                bash_profile.write(activate_completion)
                bash_profile.write("\n")

        return locals()

    @command
    def help():
        """
            Usage:
                neuro help COMMAND [SUBCOMMAND[...]]

            Display help for given COMMAND

            Examples:
                neuro help store
                neuro help store ls

        """
        pass

    return locals()


def main():
    is_verbose = "--verbose" in sys.argv
    if is_verbose:
        sys.argv.remove("--verbose")

    is_show_traceback = "--show-traceback" in sys.argv
    if is_show_traceback:
        sys.argv.remove("--show-traceback")
        log_error = log.exception
    else:
        log_error = log.error

    setup_logging()
    setup_console_handler(console_handler, verbose=is_verbose)

    if any(version_key in sys.argv for version_key in ["-v", "--version"]):
        print(f"Neuromation Platform Client {neuromation.__version__}")
        return

    config = rc.ConfigFactory.load()
    format_spec = DEFAULTS.copy()
    platform_username = config.get_platform_user_name()
    if platform_username:
        format_spec["username"] = platform_username
    if config.url:
        format_spec["api_url"] = config.url

    try:
        res = dispatch(
            target=neuro, tail=sys.argv[1:], format_spec=format_spec, token=config.auth
        )
        if res:
            print(res)

    except neuromation.clientv2.IllegalArgumentError as error:
        log_error(f"Illegal argument(s) ({error})")
        sys.exit(os.EX_DATAERR)

    except neuromation.clientv2.ResourceNotFound as error:
        log_error(f"{error}")
        sys.exit(os.EX_OSFILE)

    except neuromation.clientv2.AuthenticationError as error:
        log_error(f"Cannot authenticate ({error})")
        sys.exit(os.EX_NOPERM)
    except neuromation.clientv2.AuthorizationError as error:
        log_error(f"You haven`t enough permission ({error})")
        sys.exit(os.EX_NOPERM)

    except neuromation.clientv2.ClientError as error:
        log_error(f"Application error ({error})")
        sys.exit(os.EX_SOFTWARE)

    except aiohttp.ClientError as error:
        log_error(f"Connection error ({error})")
        sys.exit(os.EX_IOERR)

    except DockerError as error:
        log.error(f"Docker API error: {error.message}")
        sys.exit(os.EX_PROTOCOL)

    except NotImplementedError as error:
        log_error(f"{error}")
        sys.exit(os.EX_SOFTWARE)
    except FileNotFoundError as error:
        log_error(f"File not found ({error})")
        sys.exit(os.EX_OSFILE)
    except NotADirectoryError as error:
        log_error(f"{error}")
        sys.exit(os.EX_OSFILE)
    except PermissionError as error:
        log_error(f"Cannot access file ({error})")
        sys.exit(os.EX_NOPERM)
    except OSError as error:
        log_error(f"I/O Error ({error})")
        raise error

    except KeyboardInterrupt:
        log_error("Aborting.")
        sys.exit(130)
    except ValueError as e:
        print(e)
        sys.exit(127)

    except Exception as e:
        log_error(f"{e}")
        raise e
