#!/usr/bin/env python3
# -*- coding: utf-8 -*-


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


import threading
import sys
import os
import re
import uuid
import optparse
import webbrowser
import tkinter as tk
import tkinter.ttk as ttk
from tempfile import gettempdir
from enum import Enum
from time import sleep
from random import randint


class BaseJobRunner:
    """This base class that allows easy implementation of an application that can run parallel processes
    with a choice between a GUI or command-line interface"""

    def __init__(self, name):
        self.name = name

        # This object does not inherit from threading.Thread. Instead it uses threading.Thread as a member to run this
        # object's run() method. This is because this object supports running multiple times, but threading.Thread can
        # only run once.  The member thread is created every time start() is called.
        self.thread = None

        self.start_gating_event = None
        self.start_callback = self.dummy_method
        self.stop_callback = self.dummy_method
        self.stop_event = threading.Event()

        # For polling instead of using callbacks
        self.running = False
        self.result = -1
        self.output = ""
        self.result_message = ""

        self.setup_kwargs = dict()

    def dummy_method(self, *args, **kwargs):
        pass

    def set_start_gating_event(self, start_gating_event):
        self.start_gating_event = start_gating_event

    def set_start_callback(self, start_callback):
        self.start_callback = start_callback

    def set_stop_callback(self, stop_callback):
        self.stop_callback = stop_callback

    def set_args(self, **kwargs):
        self.setup_kwargs = kwargs

    def start(self):
        self.result = -1
        self.output = ""
        self.result_message = ""
        if self.stop_event.is_set():
            self.stop_event.clear()
        self.thread = threading.Thread(name=self.name, target=self.run)
        self.thread.start()

    def run(self):
        """When start() is called, this run() method will be called in a new thread"""

        self.running = False

        if self.start_gating_event is not None:
            self.start_gating_event.wait()

        self.running = True
        if self.start_callback is not None:
            self.start_callback(self.name)

        try:
            self.result, self.output = self.job()
            self.result_message = "Success" if self.result == 0 else "FAIL (" + str(self.result) + ")"

        except Exception as e:
            # Catch all exceptions in the child thread. This isn't generally a good idea, but we want exceptions to be
            # reported to the parent thread.
            self.result_message = "FAIL (Exception)"

            self.output += "\n" + type(e).__name__ + ": " + str(e)

        finally:
            self.running = False
            if self.stop_callback is not None:
                self.stop_callback(self.name, self.result_message, self.output)
            self.stop_event.set()

    def job(self):
        """Child type should implement job() to do the task this runner is trying to accomplish.
        The return value of job() and any output is passed to the result of the stop_callback.
        Any arguments needed for input to job should be supplied by self.setup_kwargs by the set_args() method."""
        result = 1
        output = "Override this method"
        return result, output

    def terminate(self):
        """Child type may choose to implement this to kill the run()/job() thread."""
        print("terminate() not implemented for", self.name)


class Cli:
    """ The (C)ommand (L)ine (I)nterface part of the app, for when running with the GUI
    is not desired."""

    def __init__(self, runners):
        self.runners = runners

        for r in runners:
            r.set_start_callback(self.call_when_runner_starts)
            r.set_stop_callback(self.call_when_runner_stops)

        self.result_info_list = list()

        self.start_callback_sema = threading.BoundedSemaphore()
        self.stop_callback_sema = threading.BoundedSemaphore()

    def call_when_runner_starts(self, name):
        with self.start_callback_sema:
            print(name, "starting...")

    def call_when_runner_stops(self, name, result_message, output):
        with self.stop_callback_sema:
            print(name, "finished.")
            self.result_info_list.append((name, result_message, output))

    def display_result_info(self):
        max_len = 0
        for name, result_message, output in self.result_info_list:
            max_len = max(max_len, len(name), len(result_message))
            output_lines = output.split("\n")
            for line in output_lines:
                max_len = max(max_len, len(line))

        # Don't let max_len get too long
        max_len = min(max_len, 200)

        separator = ""
        for i in range(0, max_len + 2):  # + 2 to match leading "# "
            separator += "#"

        for name, result_message, output in self.result_info_list:
            output_lines = output.split("\n")
            print("\n\n")
            print(separator)
            print("#", name)
            print(separator)
            print("# Result:", result_message)
            print(separator)
            for line in output_lines:
                print("#", line)

    def get_exit_return_code(self):
        failing_jobs = list()
        for name, result_message, output in self.result_info_list:
            if "Success" not in result_message:
                failing_jobs.append(name)

        print("\n\n")

        failures_detected = len(failing_jobs) > 0
        if failures_detected:
            print("Failing jobs:")
            for job in failing_jobs:
                print("    ", job)

            print("\n", str(len(failing_jobs)), "job(s) failed.")
        else:
            print("All tests passed")

        if failures_detected:
            sys.exit(1)

    def run(self):
        for r in self.runners:
            print(r.name, "is waiting to start...")
            r.start()

        for r in self.runners:
            r.stop_event.wait()

        self.display_result_info()
        sys.exit(self.get_exit_return_code())


class WidgetState(Enum):
    INIT, WAITING, RUNNING, DONE = range(0, 4)


class GuiProcessWidget:
    """The part of GUI that represents one of the processes
    """

    def __init__(self, master, name, runner, output_file_dir=""):
        self.name = name
        self.runner = runner
        self.state = WidgetState.INIT
        self.frame = tk.Frame(master, height=self.get_height(), width=self.get_width())
        self.process_enable_var = tk.IntVar()
        self.process_enable_var.set(1)
        self.check_button = None
        self.create_check_button()

        self.status_label = None
        self.progress_bar = None
        self.terminate_button = None
        self.open_output_button = None
        if output_file_dir == "":
            output_file_dir = gettempdir()
        self.output_file_name = output_file_dir + "/" + str(uuid.uuid4()) + ".txt"  # UUID is unique

    def get_tk_widget(self):
        return self.frame

    @staticmethod
    def get_height():
        return 40

    @staticmethod
    def get_width():
        return 400

    def create_check_button(self):
        self.check_button = tk.Checkbutton(self.frame, text=self.name, variable=self.process_enable_var)
        if self.process_enable_var.get():
            self.check_button.select()
        else:
            self.check_button.deselect()
        self.check_button.grid(row=0, column=0, sticky=tk.NSEW)

    def get_name(self):
        return self.name

    def select(self):
        if self.check_button is not None:
            self.check_button.select()

    def deselect(self):
        if self.check_button is not None:
            self.check_button.deselect()

    def toggle(self):
        if self.check_button is not None:
            self.check_button.toggle()

    def make_status_label(self, text, **kwargs):
        if self.status_label is not None:
            self.status_label.destroy()
        self.status_label = tk.Label(self.frame, text=text, **kwargs)
        self.status_label.grid(row=0, column=0, sticky=tk.NSEW)

    def poll_done(self):
        if self.state == WidgetState.WAITING and self.runner.running:
            self.state = WidgetState.RUNNING
            self.transition_to_running()
        elif (self.state == WidgetState.WAITING and self.runner.stop_event.is_set()) \
                or (self.state == WidgetState.RUNNING and not self.runner.running):
            self.state = WidgetState.DONE
            self.transition_to_done()
        return self.state == WidgetState.DONE

    def create_terminate_button(self):
        self.terminate_button = tk.Button(self.frame, text="Terminate", command=self.terminate_action)
        self.terminate_button.grid(row=0, column=3, sticky=tk.NE)

    def create_open_output_button(self):
        self.open_output_button = tk.Button(self.frame, text="Open Output", command=self.open_output_action)
        self.open_output_button.grid(row=0, column=1, sticky=tk.NE)

    def transition_to_done(self):
        self.destroy_progress_bar()
        self.destroy_terminate_button()
        text = self.name + ": " + self.runner.result_message
        color = 'black'
        if "FAIL" in self.runner.result_message:
            color = 'red'
        if "Success" in self.runner.result_message:
            color = '#006400'  # Dark Green
        self.write_output_to_file(text + "\n" + self.runner.output)
        self.make_status_label(text, fg=color)
        self.create_open_output_button()

    def transition_to_running(self):
        text = self.name + ": Running..."
        self.make_status_label(text)
        self.create_and_animate_progress_bar()
        self.create_terminate_button()

    def create_and_animate_progress_bar(self):
        self.progress_bar = ttk.Progressbar(self.frame, orient=tk.HORIZONTAL, mode="indeterminate")
        self.progress_bar.grid(row=0, column=1, sticky=tk.NE)
        self.progress_bar.start()

    def transition_to_not_selected(self):
        self.destroy_status_label()
        self.destroy_progress_bar()
        self.destroy_terminate_button()
        self.destroy_open_output_button()
        self.make_status_label(self.name + ": Not Selected")

    def transition_to_waiting_to_start(self):
        self.destroy_status_label()
        self.destroy_progress_bar()
        self.destroy_terminate_button()
        self.destroy_open_output_button()
        self.make_status_label(self.name + ": Waiting to start...")
        self.runner.start()

    def start(self):
        started = False
        self.check_button.destroy()
        self.check_button = None
        if self.process_enable_var.get():
            started = True
            self.state = WidgetState.WAITING
            self.transition_to_waiting_to_start()
        else:
            self.state = WidgetState.DONE
            self.transition_to_not_selected()
            # self.runner.stop_event.
        return started

    def write_output_to_file(self, output):
        with open(self.output_file_name, 'w') as output_file:
            output_file.write(output)

    def open_output_action(self):
        webbrowser.open('file://' + self.output_file_name)

    def terminate_action(self):
        self.runner.terminate()

    def reset(self):
        self.state = WidgetState.INIT

        self.destroy_checkbutton()
        self.destroy_status_label()
        self.destroy_progress_bar()
        self.destroy_terminate_button()
        self.destroy_open_output_button()

        self.clean_up_files()
        self.create_check_button()

    def destroy_open_output_button(self):
        if self.open_output_button is not None:
            self.open_output_button.destroy()
            self.open_output_button = None

    def destroy_terminate_button(self):
        if self.terminate_button is not None:
            self.terminate_button.destroy()
            self.terminate_button = None

    def destroy_progress_bar(self):
        if self.progress_bar is not None:
            self.progress_bar.stop()
            self.progress_bar.destroy()
            self.progress_bar = None

    def destroy_status_label(self):
        if self.status_label is not None:
            self.status_label.destroy()
            self.status_label = None

    def destroy_checkbutton(self):
        if self.check_button is not None:
            self.check_button.destroy()
            self.check_button = None

    def clean_up_files(self):
        if os.path.isfile(self.output_file_name):
            os.remove(self.output_file_name)


class Gui:
    """Main window of the GUI. Contains GuiProcessWidgets.
    """

    def __init__(self, application_title, runners, output_file_dir=""):
        self.application_title = application_title
        self.runners = runners

        self.root = Gui.build_root(application_title)

        self.main_frame = Gui.build_main_frame(self.root)

        self.filter_text_entry = None  # Forward declare this before registering filter_text_update_callback

        self.upper_controls_frame, \
            self.select_all_button, \
            self.select_none_button, \
            self.select_inv_button, \
            self.filter_text_string_var, \
            self.filter_text_entry = Gui.build_upper_controls_frame(self.main_frame,
                                                                    self.select_all, self.select_none, self.select_inv,
                                                                    self.filter_text_update_callback)

        num_procs_to_show = 15
        self.process_canvas, \
            self.h_bar, \
            self.v_bar, \
            self.process_widgets = Gui.build_process_canvas(self.main_frame,
                                                            GuiProcessWidget.get_width(),
                                                            GuiProcessWidget.get_height() * num_procs_to_show,
                                                            runners,
                                                            output_file_dir)

        self.lower_controls_frame, \
            self.exit_button, \
            self.go_button = Gui.build_lower_controls_frame(self.main_frame, self.exit_action, self.go_action)
        self.reset_button = None

        self.root.protocol("WM_DELETE_WINDOW", self.wm_delete_window_action)  # Covers Alt+F4
        self.root.bind("<Control-q>", self.keyboard_exit_key_combination)
        self.root.bind("<Escape>", self.keyboard_exit_key_combination)
        self.root.bind("<Return>", self.keyboard_return_key)
        self.root.bind("<Alt-o>", self.keyboard_alt_o_combination)

    @staticmethod
    def build_root(application_title):
        root = tk.Tk()
        root.title(application_title)
        Gui.configure_expansion(root, 0, 0)
        return root

    @staticmethod
    def build_main_frame(root):
        main_frame = tk.Frame(root)
        main_frame.grid(row=0, column=0, sticky=tk.NSEW)
        Gui.configure_expansion(main_frame, 1, 0)
        return main_frame

    @staticmethod
    def build_upper_controls_frame(master, select_all_method, select_none_method, select_inv_method,
                                   filter_callback):
        upr_ctl_frm = tk.Frame(master)
        upr_ctl_frm.grid(row=0, column=0, columnspan=2, sticky=tk.NSEW)
        Gui.configure_column_expansion(upr_ctl_frm, 0)
        Gui.configure_column_expansion(upr_ctl_frm, 1)
        Gui.configure_column_expansion(upr_ctl_frm, 2)

        sel_all_btn = tk.Button(upr_ctl_frm, text="Select All", command=select_all_method)
        sel_none_btn = tk.Button(upr_ctl_frm, text="Select None", command=select_none_method)
        sel_inv_btn = tk.Button(upr_ctl_frm, text="Invert Selection", command=select_inv_method)

        filter_str = tk.StringVar()
        filter_str.trace("w", lambda name, index, mode, sv=filter_str: filter_callback(sv))

        filter_entry = tk.Entry(upr_ctl_frm, textvariable=filter_str)
        filter_entry.insert(0, "<filter selection (regex)>")

        Gui.place_in_expandable_cell(sel_all_btn, 0, 0)
        Gui.place_in_expandable_cell(sel_none_btn, 0, 1)
        Gui.place_in_expandable_cell(sel_inv_btn, 0, 2)
        filter_entry.grid(row=1, column=0, columnspan=3, sticky=tk.NSEW)

        return upr_ctl_frm, sel_all_btn, sel_none_btn, sel_inv_btn, filter_str, filter_entry

    @staticmethod
    def build_process_canvas(master, canvas_width, canvas_height, runners, output_file_dir):
        process_canvas = tk.Canvas(master, width=canvas_width, height=canvas_height)

        h_bar = tk.Scrollbar(master, orient=tk.HORIZONTAL, command=process_canvas.xview)
        h_bar.grid(row=2, column=0, sticky=tk.EW)

        v_bar = tk.Scrollbar(master, orient=tk.VERTICAL, command=process_canvas.yview)
        v_bar.grid(row=1, column=1, sticky=tk.NS)

        process_canvas.config(xscrollcommand=h_bar.set, yscrollcommand=v_bar.set)
        # process_canvas.bind_all("<MouseWheel>", ...)
        process_canvas.bind_all("<Button-4>", lambda event: process_canvas.yview_scroll(-1, "units"))
        process_canvas.bind_all("<Button-5>", lambda event: process_canvas.yview_scroll(1, "units"))

        canvas_width = 0
        canvas_height = 0
        process_widgets = list()
        for i, r in enumerate(runners):
            pw = GuiProcessWidget(process_canvas, r.name, r, output_file_dir)
            process_widgets.append(pw)
            pos_x = 0
            pos_y = pw.get_height() * i
            canvas_height += pw.get_height()
            canvas_width = pw.get_width()
            process_canvas.create_window(pos_x, pos_y, anchor=tk.NW, window=pw.get_tk_widget())

        process_canvas.config(scrollregion=(0, 0, canvas_width, canvas_height))

        Gui.place_in_expandable_cell(process_canvas, 1, 0)

        return process_canvas, h_bar, v_bar, process_widgets

    @staticmethod
    def build_lower_controls_frame(master, exit_action, go_action):
        lower_controls_frame = tk.Frame(master)
        lower_controls_frame.grid(row=3, column=0, columnspan=2, sticky=tk.NSEW)
        Gui.configure_column_expansion(lower_controls_frame, 0)
        Gui.configure_column_expansion(lower_controls_frame, 1)

        exit_button = tk.Button(lower_controls_frame, text="Exit", command=exit_action)
        Gui.place_in_expandable_cell(exit_button, 0, 0)

        go_button = Gui.build_go_button(lower_controls_frame, go_action)

        return lower_controls_frame, exit_button, go_button

    @staticmethod
    def build_go_button(master, go_action):
        b = tk.Button(master, text="Go", command=go_action)
        Gui.place_in_expandable_cell(b, 0, 1)
        return b

    @staticmethod
    def build_reset_button(master, reset_action):
        b = tk.Button(master, text="Reset", command=reset_action)
        Gui.place_in_expandable_cell(b, 0, 1)
        return b

    @staticmethod
    def place_in_expandable_cell(thing, row, col):
        thing.grid(row=row, column=col, sticky=tk.NSEW)

    @staticmethod
    def configure_expansion(thing, row, column):
        Gui.configure_column_expansion(thing, column)
        Gui.configure_row_expansion(thing, row)

    @staticmethod
    def configure_row_expansion(thing, row):
        tk.Grid.rowconfigure(thing, row, weight=1)

    @staticmethod
    def configure_column_expansion(thing, column):
        tk.Grid.columnconfigure(thing, column, weight=1)

    def select_all(self):
        for p in self.process_widgets:
            p.select()

    def select_none(self):
        for p in self.process_widgets:
            p.deselect()

    def select_inv(self):
        for p in self.process_widgets:
            p.toggle()

    def filter_text_update_callback(self, sv):
        regex = sv.get()
        try:
            pattern = re.compile(regex)
            if self.filter_text_entry is not None:
                self.filter_text_entry.config(bg='white')
            for p in self.process_widgets:
                if pattern.search(p.get_name()):
                    p.select()
                else:
                    p.deselect()
        except Exception:
            if self.filter_text_entry is not None:
                self.filter_text_entry.config(bg='red')

    def exit_action(self):
        for p in self.process_widgets:
            p.terminate_action()
        self.clean_up_files()
        self.main_frame.quit()

    def go_action(self):
        self.go_button.config(state=tk.DISABLED)
        num_started = 0
        for p in self.process_widgets:
            if p.start():
                num_started += 1

        if num_started > 0:
            self.root.after(250, self.process_widget_polling_loop)
        else:
            self.change_go_button_to_reset_button()

    def process_widget_polling_loop(self):
        if self.poll_all_widgets_done():
            self.all_widgets_done_action()
        else:
            self.root.after(250, self.process_widget_polling_loop)

    def poll_all_widgets_done(self):
        all_done = True  # Starts True because of the 'and' in the loop
        for i, p in enumerate(self.process_widgets):
            d = p.poll_done()
            all_done = all_done and d
        return all_done

    def reset_action(self):
        for p in self.process_widgets:
            p.reset()
        self.reset_button.destroy()
        self.reset_button = None
        self.go_button = Gui.build_go_button(self.lower_controls_frame, self.go_action)

    def all_widgets_done_action(self):
        if self.go_button is not None:
            self.change_go_button_to_reset_button()

    def change_go_button_to_reset_button(self):
        self.go_button.destroy()
        self.go_button = None
        self.reset_button = Gui.build_reset_button(self.lower_controls_frame, self.reset_action)

    def run(self):
        self.root.mainloop()

    def keyboard_exit_key_combination(self, event):
        self.clean_up_files()
        self.root.destroy()

    def keyboard_return_key(self, event):
        if self.go_button is not None:
            self.go_action()
        if self.reset_button is not None:
            self.reset_action()

    def keyboard_alt_o_combination(self, event):
        for w in self.process_widgets:
            if w.open_output_button is not None:
                w.open_output_action()
                break

    def wm_delete_window_action(self):
        """Callback for when the "X" is clicked to close the window"""
        self.clean_up_files()  # Insert this behavior
        self.root.destroy()  # Continue with original behavior

    def clean_up_files(self):
        for p in self.process_widgets:
            p.clean_up_files()


class ParallelProcRunnerAppBase:
    """A base class for the Parallel Process Runner app.
    Selects between the GUI or CLI."""

    def __init__(self, name, usage=None, output_file_dir=""):
        self.name = name
        self.output_file_dir = output_file_dir
        self.opt_parser = optparse.OptionParser(usage=usage)
        self.configure_default_options(self.opt_parser)
        self.configure_custom_options(self.opt_parser)
        (self.options, self.args) = self.opt_parser.parse_args()

    def configure_default_options(self, parser):
        parser.add_option("-c", "--cli", dest='gui', action='store_false',
                          help="use the CLI (command-line-interface), not the GUI.")

        parser.add_option("-g", "--gui", dest='gui', action='store_true', default=True,
                          help="use the GUI (graphical-user-interface), not the CLI")

    def configure_custom_options(self, parser):
        """Child may extend this"""
        pass

    def get_runners(self):
        """Child must implement to return an iterable containing objects that inherit from BaseJobRunner"""
        return list()

    def run(self):
        if self.options.gui:
            gui = Gui(self.name, self.get_runners(), self.output_file_dir)
            gui.run()
        else:
            cli = Cli(self.get_runners())
            cli.run()


class DummyRunner(BaseJobRunner):
    """For testing the BaseJobRunner.
    """

    def __init__(self, name):
        super().__init__(name)
        self.job_ran = False
        self.terminated = False
        self.job_result = -1

    def job(self):
        self.terminated = False
        self.job_ran = False
        self.setup_kwargs['job_mocking_event'].wait()
        self.job_ran = True
        if self.terminated:
            self.terminated = False
            return 255, "Job was terminated by user"
        return self.job_result, "Output from " + self.name

    def set_result(self, result):
        self.job_result = result

    def terminate(self):
        self.setup_kwargs['job_mocking_event'].set()
        self.terminated = True


class ExampleApp(ParallelProcRunnerAppBase):
    """For testing and demonstrating ParallelProcRunnerApp
    """

    def __init__(self):
        super().__init__("Test for ParallelProcRunner")

    def get_runners(self):
        runners = list()
        for i in range(0, 5):
            result = i % 2
            will_fail = result != 0

            name = "Process " + str(i)
            if will_fail:
                name += " (will fail)"
            else:
                name += " (will pass)"

            r = DummyRunner(name)
            runners.append(r)
            # r.set_start_gating_event(None if i == 0 else runners[i-1].stop_event)
            r.set_result(result)

            class DummyEvent:
                def __init__(self):
                    self.flag = False

                def set(self):
                    self.flag = True

                def wait(self):
                    i = 0
                    timeout = randint(5, 10)
                    while not self.flag and i < timeout:
                        sleep(1)
                        i += 1
                    self.flag = False

            dummy = DummyEvent()
            r.set_args(job_mocking_event=dummy)

            if i > 0:
                r.set_start_gating_event(runners[0].stop_event)
        return runners


if __name__ == '__main__':
    """For testing"""
    app = ExampleApp()
    app.run()

