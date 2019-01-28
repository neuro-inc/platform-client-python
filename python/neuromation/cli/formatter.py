import time
from typing import AbstractSet, Iterable, List, Optional

from dateutil.parser import isoparse  # type: ignore

from neuromation.clientv2 import FileStatus, JobDescription, JobStatus, Resources
from neuromation.clientv2.jobs import JobTelemetry


class BaseFormatter:
    @classmethod
    def _truncate_string(cls, input: Optional[str], max_length: int) -> str:
        if input is None:
            return ""
        if len(input) <= max_length:
            return input
        len_tail, placeholder = 3, "..."
        if max_length < len_tail or max_length < len(placeholder):
            return placeholder
        tail = input[-len_tail:] if max_length > len(placeholder) + len_tail else ""
        index_stop = max_length - len(placeholder) - len(tail)
        return input[:index_stop] + placeholder + tail

    @classmethod
    def _wrap(cls, text: Optional[str]) -> str:
        return "'" + (text or "") + "'"


class OutputFormatter(BaseFormatter):
    @classmethod
    def format_job(cls, job: JobDescription, quiet: bool = True) -> str:
        if quiet:
            return job.id
        return (
            f"Job ID: {job.id} Status: {job.status}\n"
            + f"Shortcuts:\n"
            + f"  neuro job status {job.id}  # check job status\n"
            + f"  neuro job monitor {job.id} # monitor job stdout\n"
            + f"  neuro job kill {job.id}    # kill job"
        )


class StorageLsFormatter(BaseFormatter):
    FORMAT = "{type:<15}{size:<15,}{name:<}".format

    def format_ls(self, lst: List[FileStatus]) -> str:
        return "\n".join(
            self.FORMAT(type=status.type.lower(), name=status.path, size=status.size)
            for status in lst
        )


class JobStatusFormatter(BaseFormatter):
    @classmethod
    def format_job_status(cls, job_status: JobDescription) -> str:
        result: str = f"Job: {job_status.id}\n"
        result += f"Owner: {job_status.owner if job_status.owner else ''}\n"
        if job_status.description:
            result += f"Description: {job_status.description}\n"
        result += f"Status: {job_status.status}"
        if (
            job_status.history
            and job_status.history.reason
            and job_status.status in [JobStatus.FAILED, JobStatus.PENDING]
        ):
            result += f" ({job_status.history.reason})"
        result += f"\nImage: {job_status.container.image}\n"

        result += f"Command: {job_status.container.command}\n"
        resource_formatter = ResourcesFormatter()
        result += (
            resource_formatter.format_resources(job_status.container.resources) + "\n"
        )

        if job_status.http_url:
            result = f"{result}Http URL: {job_status.http_url}\n"
        if job_status.container.env:
            result += f"Environment:\n"
            for key, value in job_status.container.env.items():
                result += f"{key}={value}\n"

        assert job_status.history
        result = f"{result}Created: {job_status.history.created_at}"
        if job_status.status in [
            JobStatus.RUNNING,
            JobStatus.FAILED,
            JobStatus.SUCCEEDED,
        ]:
            result += "\n" f"Started: {job_status.history.started_at}"
        if job_status.status in [JobStatus.FAILED, JobStatus.SUCCEEDED]:
            result += "\n" f"Finished: {job_status.history.finished_at}"
        if job_status.status == JobStatus.FAILED:
            result += "\n===Description===\n"
            result += f"{job_status.history.description}\n================="
        return result


class JobTelemetryFormatter(BaseFormatter):
    def __init__(self) -> None:
        self.tab = "\t"
        self.col_len = {
            "id": 40,
            "timestamp": 24,
            "cpu": 15,
            "memory": 15,
            "gpu": 15,
            "gpu_memory": 15,
        }

    def format_header_line(self) -> str:
        return self.tab.join(
            [
                "ID".ljust(self.col_len["id"]),
                "TIMESTAMP".ljust(self.col_len["timestamp"]),
                "CPU (%)".ljust(self.col_len["cpu"]),
                "MEMORY (MB)".ljust(self.col_len["memory"]),
                "GPU (%)".ljust(self.col_len["gpu"]),
                "GPU_MEMORY (MB)".ljust(self.col_len["gpu_memory"]),
            ]
        )

    def format_telemetry_line(self, job_id: str, info: JobTelemetry) -> str:
        timestamp = self._format_timestamp(info.timestamp)
        cpu = str(info.cpu)
        mem = str(info.memory)
        gpu = str(info.gpu_duty_cycle or "N/A")
        gpu_mem = str(info.gpu_memory or "N/A")
        return self.tab.join(
            [
                job_id.ljust(self.col_len["id"]),
                timestamp.ljust(self.col_len["timestamp"]),
                cpu.ljust(self.col_len["cpu"]),
                mem.ljust(self.col_len["memory"]),
                gpu.ljust(self.col_len["gpu"]),
                gpu_mem.ljust(self.col_len["gpu_memory"]),
            ]
        )

    @classmethod
    def _format_timestamp(cls, timestamp: float) -> str:
        return str(time.ctime(timestamp))


class JobListFormatter(BaseFormatter):
    def __init__(self, quiet: bool = False):
        self.quiet = quiet
        self.tab = "\t"
        self.column_lengths = {
            "id": 40,
            "status": 10,
            "image": 15,
            "description": 50,
            "command": 50,
        }

    def format_jobs(
        self,
        jobs: Iterable[JobDescription],
        statuses: AbstractSet[str] = frozenset(),
        description: str = "",
    ) -> str:
        if statuses:
            jobs = [j for j in jobs if j.status in statuses]
        if description:
            jobs = [j for j in jobs if j.description == description]

        jobs = sorted(jobs, key=lambda j: isoparse(j.history.created_at))
        lines = list()
        if not self.quiet:
            lines.append(self._format_header_line())
        lines.extend(map(self._format_job_line, jobs))
        return "\n".join(lines)

    def _format_header_line(self) -> str:
        return self.tab.join(
            [
                "ID".ljust(self.column_lengths["id"]),
                "STATUS".ljust(self.column_lengths["status"]),
                "IMAGE".ljust(self.column_lengths["image"]),
                "DESCRIPTION".ljust(self.column_lengths["description"]),
                "COMMAND".ljust(self.column_lengths["command"]),
            ]
        )

    def _format_job_line(self, job: JobDescription) -> str:
        def truncate_then_wrap(value: str, key: str) -> str:
            return self._wrap(self._truncate_string(value, self.column_lengths[key]))

        if self.quiet:
            return job.id.ljust(self.column_lengths["id"])

        description = truncate_then_wrap(job.description or "", "description")
        command = truncate_then_wrap(job.container.command or "", "command")
        return self.tab.join(
            [
                job.id.ljust(self.column_lengths["id"]),
                job.status.ljust(self.column_lengths["status"]),
                job.container.image.ljust(self.column_lengths["image"]),
                description.ljust(self.column_lengths["description"]),
                command.ljust(self.column_lengths["command"]),
            ]
        )


class ResourcesFormatter(BaseFormatter):
    def format_resources(self, resources: Resources) -> str:
        lines = list()
        lines.append(f"Memory: {resources.memory_mb} MB")
        lines.append(f"CPU: {resources.cpu:0.1f}")
        if resources.gpu:
            lines.append(f"GPU: {resources.gpu:0.1f} x {resources.gpu_model}")

        additional = list()
        if resources.shm:
            additional.append("Extended SHM space")

        if additional:
            lines.append(f'Additional: {",".join(additional)}')

        indent = "  "
        return f"Resources:\n" + indent + f"\n{indent}".join(lines)
