#!/usr/bin/env python3
# -*- coding: utf-8 -*-


# https://github.com/cquickstad/parallel_proc_runner


# Copyright 2018 Chad Quickstad
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import unittest
import threading
from time import sleep
from parallel_proc_runner_base import DummyRunner


class BaseRunnerTest(unittest.TestCase):
    def setUp(self):
        self.event_to_wait_for = threading.Event()
        self.job_mocking_event = threading.Event()

        # Class Under Test
        self.runner = DummyRunner('base runner')
        self.start_callback_called = False
        self.stop_callback_called = False
        self.stop_callback_result = None
        self.stop_callback_output = None

    def mock_start_callback(self, name):
        # Name should be passed to the callback
        self.assertEqual(self.runner.name, name)

        # Indicate that the callback indeed happened
        self.start_callback_called = True

    def mock_stop_callback(self, name, result, output):
        # Name should be passed to the callback
        self.assertEqual(self.runner.name, name)
        self.stop_callback_result = result
        self.stop_callback_output = output
        self.stop_callback_called = True
        # Check that stop event is not triggered yet
        self.assertFalse(self.runner.stop_event.is_set())

    def test_that_run_waits_for_start_gating_event(self):
        self.runner.set_start_gating_event(self.event_to_wait_for)
        self.runner.set_start_callback(self.mock_start_callback)
        self.runner.set_stop_callback(self.mock_stop_callback)
        self.runner.set_args(job_mocking_event=self.job_mocking_event)
        self.runner.start()
        sleep(0.01)  # Let thread have a chance to go
        self.assertFalse(self.start_callback_called)
        self.assertFalse(self.runner.running)
        self.event_to_wait_for.set()
        sleep(0.01)  # Let thread have a chance to go
        self.assertTrue(self.start_callback_called)
        self.assertTrue(self.runner.running)
        self.job_mocking_event.set()

    def test_that_callbacks_can_be_none(self):
        self.runner.set_start_gating_event(None)
        self.runner.set_start_callback(None)
        self.runner.set_stop_callback(None)
        self.runner.set_args(job_mocking_event=self.job_mocking_event)
        self.runner.start()
        self.job_mocking_event.set()

    def test_that_run_does_not_wait_when_start_gating_event_is_none(self):
        self.runner.set_start_gating_event(None)
        self.runner.set_start_callback(self.mock_start_callback)
        self.runner.set_stop_callback(self.mock_stop_callback)
        self.runner.set_args(job_mocking_event=self.job_mocking_event)
        self.runner.start()
        sleep(0.01)  # Let thread have a chance to go
        self.assertTrue(self.start_callback_called)
        self.assertTrue(self.runner.running)
        self.job_mocking_event.set()

    def test_that_job_runs_after_start_callback(self):
        self.runner.set_start_gating_event(self.event_to_wait_for)
        self.runner.set_start_callback(self.mock_start_callback)
        self.runner.set_stop_callback(self.mock_stop_callback)
        self.runner.set_args(job_mocking_event=self.job_mocking_event)
        self.runner.start()
        sleep(0.01)  # Let thread have a chance to go
        self.event_to_wait_for.set()
        sleep(0.01)  # Let thread have a chance to go
        self.assertTrue(self.start_callback_called)
        self.assertTrue(self.runner.running)
        self.assertFalse(self.runner.job_ran)
        self.job_mocking_event.set()
        sleep(0.01)  # Let thread have a chance to go
        self.assertTrue(self.runner.job_ran)

    def test_that_args_are_passed(self):
        self.runner.set_start_gating_event(self.event_to_wait_for)
        self.runner.set_start_callback(self.mock_start_callback)
        self.runner.set_stop_callback(self.mock_stop_callback)
        self.runner.set_args(job_mocking_event=self.job_mocking_event,
                             some_arg="Bla Bla")
        self.runner.start()
        sleep(0.01)  # Let thread have a chance to go
        self.event_to_wait_for.set()
        sleep(0.01)  # Let thread have a chance to go
        self.assertTrue(self.start_callback_called)
        self.assertFalse(self.runner.job_ran)
        self.job_mocking_event.set()
        sleep(0.01)  # Let thread have a chance to go
        self.assertEqual("Bla Bla", self.runner.setup_kwargs['some_arg'])
        self.assertTrue(self.runner.job_ran)

    def test_that_stop_callback_is_called_after_job_ran(self):
        self.runner.set_start_gating_event(self.event_to_wait_for)
        self.runner.set_start_callback(self.mock_start_callback)
        self.runner.set_stop_callback(self.mock_stop_callback)
        self.runner.set_args(job_mocking_event=self.job_mocking_event)
        self.runner.start()
        sleep(0.01)  # Let thread have a chance to go
        self.event_to_wait_for.set()
        sleep(0.01)  # Let thread have a chance to go
        self.assertFalse(self.stop_callback_called)
        self.assertTrue(self.runner.running)
        self.runner.set_result(0)
        self.job_mocking_event.set()
        sleep(0.01)  # Let thread have a chance to go
        self.assertTrue(self.stop_callback_called)
        self.assertFalse(self.runner.running)
        self.assertEqual("Success", self.stop_callback_result)
        self.assertEqual("Output from base runner", self.stop_callback_output)

    def test_that_stop_callback_reports_failure(self):
        self.runner.set_start_gating_event(self.event_to_wait_for)
        self.runner.set_start_callback(self.mock_start_callback)
        self.runner.set_stop_callback(self.mock_stop_callback)
        self.runner.set_args(job_mocking_event=self.job_mocking_event)
        self.runner.start()
        sleep(0.01)  # Let thread have a chance to go
        self.assertFalse(self.runner.running)
        self.event_to_wait_for.set()
        sleep(0.01)  # Let thread have a chance to go
        self.assertFalse(self.stop_callback_called)
        self.assertTrue(self.runner.running)
        self.runner.set_result(1)
        self.job_mocking_event.set()
        sleep(0.01)  # Let thread have a chance to go
        self.assertTrue(self.stop_callback_called)
        self.assertFalse(self.runner.running)
        self.assertEqual("FAIL (1)", self.stop_callback_result)
        self.assertEqual("Output from base runner", self.stop_callback_output)

    def test_that_stop_event_is_triggered_on_success(self):
        self.runner.set_start_gating_event(None)
        self.runner.set_start_callback(None)
        self.runner.set_stop_callback(self.mock_stop_callback)
        self.runner.set_args(job_mocking_event=self.job_mocking_event)
        self.runner.start()
        sleep(0.01)  # Let thread have a chance to go
        self.runner.set_result(0)
        self.assertFalse(self.runner.stop_event.is_set())
        self.job_mocking_event.set()
        sleep(0.1)  # Let thread have a chance to go
        # Check in stop callback that it is not yet set
        self.assertTrue(self.runner.stop_event.is_set())

    def test_that_stop_event_is_triggered_on_failure(self):
        self.runner.set_start_gating_event(None)
        self.runner.set_start_callback(None)
        self.runner.set_stop_callback(self.mock_stop_callback)
        self.runner.set_args(job_mocking_event=self.job_mocking_event)
        self.runner.start()
        sleep(0.01)  # Let thread have a chance to go
        self.runner.set_result(1)
        self.assertFalse(self.runner.stop_event.is_set())
        self.job_mocking_event.set()
        sleep(0.01)  # Let thread have a chance to go
        # Check in stop callback that it is not yet set
        self.assertTrue(self.runner.stop_event.is_set())

    def test_that_runner_can_run_again(self):
        self.runner.set_start_gating_event(self.event_to_wait_for)
        self.runner.set_start_callback(self.mock_start_callback)
        self.runner.set_stop_callback(self.mock_stop_callback)
        self.runner.set_args(job_mocking_event=self.job_mocking_event)

        # Run for the first time
        self.runner.start()
        sleep(0.01)  # Let thread have a chance to go
        self.assertFalse(self.start_callback_called)
        self.assertFalse(self.runner.running)
        self.event_to_wait_for.set()
        sleep(0.01)  # Let thread have a chance to go
        self.assertTrue(self.start_callback_called)
        self.assertTrue(self.runner.running)
        self.assertFalse(self.stop_callback_called)
        self.runner.set_result(1)
        self.job_mocking_event.set()
        sleep(0.01)  # Let thread have a chance to go
        self.assertTrue(self.stop_callback_called)
        self.assertFalse(self.runner.running)
        self.assertEqual("FAIL (1)", self.stop_callback_result)
        self.assertEqual("Output from base runner", self.stop_callback_output)

        # Reset the test events for running again
        self.event_to_wait_for.clear()
        self.job_mocking_event.clear()

        # Reset the indicators of the runner running
        self.start_callback_called = False
        self.stop_callback_called = False
        self.stop_callback_result = None
        self.stop_callback_output = None

        # Run again
        self.runner.start()
        sleep(0.01)  # Let thread have a chance to go
        self.assertFalse(self.start_callback_called)
        self.assertFalse(self.runner.running)
        self.assertEqual(self.runner.result_message, "")
        self.assertFalse(self.runner.stop_event.is_set())
        self.event_to_wait_for.set()
        sleep(0.01)  # Let thread have a chance to go
        self.assertTrue(self.start_callback_called)
        self.assertTrue(self.runner.running)
        self.assertFalse(self.stop_callback_called)
        self.runner.set_result(1)
        self.job_mocking_event.set()
        sleep(0.01)  # Let thread have a chance to go
        self.assertTrue(self.stop_callback_called)
        self.assertFalse(self.runner.running)
        self.assertEqual("FAIL (1)", self.stop_callback_result)
        self.assertEqual("Output from base runner", self.stop_callback_output)

    def test_that_stop_event_is_triggered_and_there_is_a_failure_result_on_exception(self):
        self.runner.set_start_gating_event(None)
        self.runner.set_start_callback(None)
        self.runner.set_stop_callback(self.mock_stop_callback)
        self.runner.set_args(job_mocking_event=self.job_mocking_event)
        self.runner.set_result(0)  # Make sure that it's the exception that causes the fail result
        self.runner.name = None  # This will cause an exception in the job() method of TestableBaseRunner
        self.job_mocking_event.set()  # No threads in this test, so trigger this ahead of time

        # So that we can test the exception, don't launch a thread. Call run() directly.
        self.runner.run()

        # Check in stop callback that it is not yet set
        self.assertTrue(self.runner.stop_event.is_set())
        self.assertEqual("FAIL (Exception)", self.stop_callback_result)
        self.assertEqual("\nTypeError: must be str, not NoneType", self.stop_callback_output)
        self.assertFalse(self.runner.running)


if __name__ == '__main__':
    unittest.main()
