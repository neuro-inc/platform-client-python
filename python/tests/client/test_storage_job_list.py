from typing import List

import pytest

from neuromation.cli.command_handlers import JobHandlerOperations
from neuromation.cli.formatter import JobListFormatter
from neuromation.client.jobs import JobDescription, JobStatusHistory


@pytest.fixture
def valid_job_description():
    return "non-empty job description 1234567890`!@#$%^&*()_+='\\/"


@pytest.fixture
def sorted_timestamps():
    return [
        "2018-11-25T12:28:21.298672+00:00",
        "2018-11-25T12:28:23.298672+00:00",
        "2019-09-25T12:28:21.298672+00:00",
    ]


@pytest.fixture
def jobs_to_test(sorted_timestamps, valid_job_description):
    description_list = [None, "", valid_job_description]
    status_list = [
        "pending",
        "failed",
        "succeeded",
        "running",
        "all",
        "failed,succeeded",
        "failed,all,succeeded",
        "all,running",
    ]

    def get_id_generator():
        id = 0
        while 1:
            id += 1
            yield f"job-{id}"

    id_generator = get_id_generator()

    command = "shell"
    image = "ubuntu"
    client = None

    return [
        JobDescription(
            status=status,
            id=next(id_generator),
            description=description,
            client=client,
            image=image,
            command=command,
            history=JobStatusHistory(
                status="pending",
                reason="",
                description="",
                created_at=created_at,
                started_at="",
                finished_at="",
            ),
        )
        for status in status_list
        for created_at in sorted_timestamps
        for description in description_list
    ]


@pytest.fixture
def jobs_mock(mocked_jobs, jobs_to_test):
    def job_list() -> List[JobDescription]:
        return jobs_to_test

    def jobs_status(id) -> JobDescription:
        return JobDescription(
            status="running", id=id, client=None, image="ubuntu", command="shell"
        )

    mock = mocked_jobs
    mock.list = job_list
    mock.status = jobs_status

    def mock_():
        return mock

    return mock_


class TestJobListFilter:
    @classmethod
    def _format(cls, jobs, quiet):
        formatter = JobListFormatter(quiet)
        return formatter.format_jobs(JobHandlerOperations._sort_job_list(jobs))

    @classmethod
    def _format_quiet(cls, jobs):
        return "\n".join([j.id for j in JobHandlerOperations._sort_job_list(jobs)])

    @pytest.mark.parametrize("quiet", [True, False])
    def test_job_filter_all(self, jobs_mock, jobs_to_test, quiet):
        expected = self._format(jobs_to_test, quiet=quiet)
        jobs = JobHandlerOperations("test-user").list_jobs(
            jobs_mock, quiet=quiet, status="all"
        )
        assert jobs == expected

    @pytest.mark.parametrize("quiet", [True, False])
    def test_job_no_status_filter(self, jobs_mock, jobs_to_test, quiet):
        expected = self._format([], quiet=quiet)
        jobs = JobHandlerOperations("test-user").list_jobs(
            jobs_mock, quiet=quiet, status=""
        )
        assert jobs == expected

    @pytest.mark.parametrize("quiet", [True, False])
    def test_job_filter_all_and_running(self, jobs_mock, jobs_to_test, quiet):
        expected = self._format(jobs_to_test, quiet=quiet)
        jobs = JobHandlerOperations("test-user").list_jobs(
            jobs_mock, quiet=quiet, status="all,running"
        )
        assert jobs == expected

    @pytest.mark.parametrize("quiet", [True, False])
    def test_job_filter_failed_and_running(self, jobs_mock, jobs_to_test, quiet):
        expected = self._format(
            [j for j in jobs_to_test if j.status in ["failed", "running"]], quiet=quiet
        )
        jobs = JobHandlerOperations("test-user").list_jobs(
            jobs_mock, quiet=quiet, status="failed,running"
        )
        assert jobs == expected

    @pytest.mark.parametrize("quiet", [True, False])
    def test_job_filter_running(self, jobs_mock, jobs_to_test, quiet):
        expected = self._format(
            [j for j in jobs_to_test if j.status == "running"], quiet=quiet
        )
        jobs = JobHandlerOperations("test-user").list_jobs(
            jobs_mock, status="running", quiet=quiet
        )
        assert jobs == expected

    @pytest.mark.parametrize("quiet", [True, False])
    def test_job_filter_failed(self, jobs_mock, jobs_to_test, quiet):
        expected = self._format(
            [j for j in jobs_to_test if j.status == "failed"], quiet=quiet
        )
        jobs = JobHandlerOperations("test-user").list_jobs(
            jobs_mock, status="failed", quiet=quiet
        )
        assert jobs == expected

    @pytest.mark.parametrize("quiet", [True, False])
    def test_job_filter_succeeded(self, jobs_mock, jobs_to_test, quiet):
        expected = self._format(
            [j for j in jobs_to_test if j.status == "succeeded"], quiet=quiet
        )
        jobs = JobHandlerOperations("test-user").list_jobs(
            jobs_mock, status="succeeded", quiet=quiet
        )
        assert jobs == expected

    @pytest.mark.parametrize("quiet", [True, False])
    def test_job_filter_dummy_status(self, jobs_mock, jobs_to_test, quiet):
        expected = self._format([], quiet=quiet)
        jobs = JobHandlerOperations("test-user").list_jobs(
            jobs_mock, status="not-a-status", quiet=quiet
        )
        assert jobs == expected

    @pytest.mark.parametrize("quiet", [True, False])
    def test_job_filter_with_empty_description(self, jobs_mock, jobs_to_test, quiet):
        expected = self._format([], quiet=quiet)
        jobs = JobHandlerOperations("test-user").list_jobs(
            jobs_mock, status="", description="", quiet=quiet
        )
        assert jobs == expected

    @pytest.mark.parametrize("quiet", [True, False])
    def test_job_filter_with_all_status_empty_description(
        self, jobs_mock, jobs_to_test, quiet
    ):
        expected = self._format(jobs_to_test, quiet=quiet)
        jobs = JobHandlerOperations("test-user").list_jobs(
            jobs_mock, status="all", description="", quiet=quiet
        )
        assert jobs == expected

    @pytest.mark.parametrize("quiet", [True, False])
    def test_job_filter_with_empty_status_empty_description(
        self, jobs_mock, jobs_to_test, quiet
    ):
        expected = self._format([], quiet=quiet)
        jobs = JobHandlerOperations("test-user").list_jobs(
            jobs_mock, status="", description="", quiet=quiet
        )
        assert jobs == expected

    @pytest.mark.parametrize("quiet", [True, False])
    def test_job_filter_running_status_empty_description__same_as_without_description(
        self, jobs_mock, jobs_to_test, quiet
    ):
        expected = self._format(
            [j for j in jobs_to_test if j.status == "running"], quiet=quiet
        )
        jobs = JobHandlerOperations("test-user").list_jobs(
            jobs_mock, status="running", description="", quiet=quiet
        )
        assert jobs == expected

    @pytest.mark.parametrize("quiet", [True, False])
    def test_job_filter_running_or_pending_status_nonempty_description(
        self, jobs_mock, jobs_to_test, quiet
    ):
        expected = self._format(
            [
                j
                for j in jobs_to_test
                if j.description == valid_job_description
                and j.status in ["running", "pending"]
            ],
            quiet=quiet,
        )
        jobs = JobHandlerOperations("test-user").list_jobs(
            jobs_mock,
            status="running,pending",
            description=valid_job_description,
            quiet=quiet,
        )
        assert jobs == expected

    @pytest.mark.parametrize("quiet", [True, False])
    def test_job_filter_pending_or_running_status_description_not_defined(
        self, jobs_mock, jobs_to_test, quiet
    ):
        expected = self._format(
            [j for j in jobs_to_test if j.status in ["running", "pending"]], quiet=quiet
        )
        jobs = JobHandlerOperations("test-user").list_jobs(
            jobs_mock, status="pending,running", description=None, quiet=quiet
        )
        assert jobs == expected

    @pytest.mark.parametrize("quiet", [True, False])
    def test_job_filter_description_not_found(self, jobs_mock, jobs_to_test, quiet):
        expected = self._format([], quiet=quiet)
        jobs = JobHandlerOperations("test-user").list_jobs(
            jobs_mock,
            description="non-existing job description!",
            status="all",
            quiet=quiet,
        )
        assert jobs == expected

    @pytest.mark.parametrize("quiet", [True, False])
    def test_job_filter_empty_status_and_dummy_description(
        self, jobs_mock, jobs_to_test, quiet
    ):
        expected = self._format(
            [
                j
                for j in jobs_to_test
                if j.description == "non-existing job description"
            ],
            quiet=quiet,
        )
        jobs = JobHandlerOperations("test-user").list_jobs(
            jobs_mock,
            status="",
            description="job not existing description",
            quiet=quiet,
        )
        assert jobs == expected

    @pytest.mark.parametrize("quiet", [True, False])
    def test_job_filter_non_empty_status_and_dummy_description(
        self, jobs_mock, jobs_to_test, quiet
    ):
        expected = self._format([], quiet=quiet)
        jobs = JobHandlerOperations("test-user").list_jobs(
            jobs_mock,
            status="running",
            description="non-existing job description",
            quiet=quiet,
        )
        assert jobs == expected

    @pytest.mark.parametrize("quiet", [True, False])
    def test_job_filter_status_and_description(self, jobs_mock, jobs_to_test, quiet):
        expected = self._format(
            [
                job
                for job in jobs_to_test
                if job.status == "running" and job.description == valid_job_description
            ],
            quiet=quiet,
        )
        jobs = JobHandlerOperations("test-user").list_jobs(
            jobs_mock, status="running", description=valid_job_description, quiet=quiet
        )
        assert jobs == expected


class TestJobListSort:
    def test_sort(self, jobs_mock, sorted_timestamps, valid_job_description):
        def slice_jobs_chronologically(jobs_list, substring):
            return [index for index, job in enumerate(jobs_list) if substring in job]

        for quiet in [True, False]:
            jobs = JobHandlerOperations("test-user").list_jobs(
                jobs_mock, status="all", quiet=quiet
            )
            jobs = jobs.split("\n")
            old_jobs = slice_jobs_chronologically(jobs, sorted_timestamps[0])
            mid_jobs = slice_jobs_chronologically(jobs, sorted_timestamps[1])
            new_jobs = slice_jobs_chronologically(jobs, sorted_timestamps[2])
            assert all(i > j for i in old_jobs for j in mid_jobs)
            assert all(i > j for i in mid_jobs for j in new_jobs)


def test_job_status_query(jobs_mock):
    jobs = JobHandlerOperations("test-user").status("id0", jobs_mock)
    assert jobs == JobDescription(
        status="running", id="id0", client=None, image="ubuntu", command="shell"
    )
