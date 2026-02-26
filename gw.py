#!/usr/bin/env python3
import curses
import json
import os
import sys
from datetime import datetime

# Shared config paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TASKS_FILE = os.path.join(BASE_DIR, "tasks.json")
WORKSPACES_FILE = os.path.join(BASE_DIR, "workspaces.txt")

VIEW_WORKSPACES = "workspaces"
VIEW_TASKS = "tasks"
VIEW_DETAIL = "detail"

def load_json(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            try:
                return json.load(f)
            except:
                return {}
    return {}

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def get_workspaces():
    ws = []
    if os.path.exists(WORKSPACES_FILE):
        with open(WORKSPACES_FILE, "r") as f:
            ws = [line.strip() for line in f if line.strip()]
    return sorted(list(set(ws)))

class AGUplinkCLI:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.view = VIEW_WORKSPACES
        self.selected_ws = None
        self.selected_task_idx = None
        self.cursor_pos = 0
        self.scroll_pos = 0     # For detail view
        self.list_offset = 0    # For workspace/task lists
        self.workspaces = []
        self.tasks = []
        
        # Curses setup
        curses.curs_set(0)
        try:
            curses.start_color()
            curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_CYAN) # Highlight
            curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK) # Success/Done
            curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK) # Warning/Todo
            curses.init_pair(4, curses.COLOR_WHITE, curses.COLOR_BLUE)  # Header detail
        except:
            pass # Colors might not be supported
        
        self.refresh_data()
        self.run()

    def refresh_data(self):
        self.workspaces = get_workspaces()
        data = load_json(TASKS_FILE)
        if self.selected_ws:
            self.tasks = data.get(self.selected_ws, [])
        else:
            self.tasks = []

    def draw_header(self):
        h, w = self.stdscr.getmaxyx()
        self.stdscr.attron(curses.color_pair(1))
        self.stdscr.addstr(0, 0, " 👻 AG-Uplink CLI v2.2 - Agent Manager ".ljust(w - 1))
        self.stdscr.attroff(curses.color_pair(1))
        
        breadcrumb = f" All Workspaces "
        if self.selected_ws:
            breadcrumb = f" Workspaces > {self.selected_ws} "
            if self.selected_task_idx is not None:
                task_desc = self.tasks[self.selected_task_idx]['desc']
                if len(task_desc) > 30: task_desc = task_desc[:27] + "..."
                breadcrumb += f" > {task_desc} "
        
        self.stdscr.addstr(1, 0, breadcrumb.ljust(w - 1), curses.A_REVERSE)

    def draw_footer(self):
        h, w = self.stdscr.getmaxyx()
        footer = " [UP/DOWN] Nav | [ENTER] Select | [a] Add Task | [d] Done | [q] Quit "
        if self.view == VIEW_TASKS:
            footer = " [UP/DOWN] Nav | [ENTER] View Conversation | [BACKSPACE] Back | [a] Add Task | [q] Quit "
        elif self.view == VIEW_DETAIL:
            footer = " [UP/DOWN] Scroll | [BACKSPACE] Back to List | [q] Quit "
        
        self.stdscr.attron(curses.A_DIM)
        self.stdscr.addstr(h - 1, 0, footer.ljust(w - 1))
        self.stdscr.attroff(curses.A_DIM)

    def draw_workspaces(self):
        h, w = self.stdscr.getmaxyx()
        max_rows = h - 5
        visible_ws = self.workspaces[self.list_offset:self.list_offset + max_rows]
        
        for i, ws in enumerate(visible_ws):
            actual_idx = i + self.list_offset
            if actual_idx == self.cursor_pos:
                self.stdscr.attron(curses.color_pair(1))
                self.stdscr.addstr(3 + i, 2, f"> {ws} ".ljust(w - 4))
                self.stdscr.attroff(curses.color_pair(1))
            else:
                self.stdscr.addstr(3 + i, 2, f"  {ws} ")
        
        if len(self.workspaces) > max_rows:
            self.stdscr.addstr(h - 2, 2, f" -- More workspaces above/below ({self.cursor_pos+1}/{len(self.workspaces)}) -- ", curses.A_DIM)

    def draw_tasks(self):
        h, w = self.stdscr.getmaxyx()
        if not self.tasks:
            self.stdscr.addstr(3, 2, " No tasks found for this workspace. Press 'a' to add one. ")
            return

        max_rows = h - 5
        visible_tasks = self.tasks[self.list_offset:self.list_offset + max_rows]
        
        for i, t in enumerate(visible_tasks):
            actual_idx = i + self.list_offset
            status_icon = " [X]" if t['status'] == 'done' else " [ ]"
            color = curses.color_pair(2) if t['status'] == 'done' else curses.color_pair(3)
            
            if actual_idx == self.cursor_pos:
                self.stdscr.attron(curses.color_pair(1))
                self.stdscr.addstr(3 + i, 2, f"> {status_icon} {t['desc']} ".ljust(w - 4))
                self.stdscr.attroff(curses.color_pair(1))
            else:
                self.stdscr.attron(color)
                self.stdscr.addstr(3 + i, 2, f"  {status_icon}")
                self.stdscr.attroff(color)
                self.stdscr.addstr(3 + i, 7, f" {t['desc']}")

        if len(self.tasks) > max_rows:
            self.stdscr.addstr(h - 2, 2, f" -- Scroll for more tasks ({self.cursor_pos+1}/{len(self.tasks)}) -- ", curses.A_DIM)

    def draw_detail(self):
        h, w = self.stdscr.getmaxyx()
        task = self.tasks[self.selected_task_idx]
        
        # Info block
        self.stdscr.attron(curses.A_BOLD)
        self.stdscr.addstr(3, 2, f"Target: {task['desc']}")
        self.stdscr.attroff(curses.A_BOLD)
        self.stdscr.addstr(4, 2, f"Status: {task['status'].upper()} | Created: {task['created_at']}")
        
        self.stdscr.addstr(6, 2, "--- CONVERSATION / OUTPUT ---", curses.A_DIM)
        
        output = task.get('output', "")
        visible_lines = h - 11
        
        if not output:
            self.stdscr.addstr(8, 4, "(No conversation data available yet)", curses.A_ITALIC)
        else:
            lines = output.split('\n')
            for i in range(min(visible_lines, len(lines) - self.scroll_pos)):
                idx = i + self.scroll_pos
                self.stdscr.addstr(8 + i, 4, lines[idx][:w-8])
        
            if len(lines) > visible_lines:
                self.stdscr.addstr(h - 3, 2, f" (Use ARROWS to scroll - Line {self.scroll_pos+1}/{len(lines)}) ", curses.A_REVERSE)

    def get_user_input(self, prompt_text):
        h, w = self.stdscr.getmaxyx()
        curses.echo()
        self.stdscr.addstr(h - 2, 0, prompt_text)
        self.stdscr.refresh()
        input_str = self.stdscr.getstr(h - 2, len(prompt_text)).decode('utf-8')
        curses.noecho()
        self.stdscr.addstr(h - 2, 0, " " * (w - 1))
        return input_str.strip()

    def run(self):
        while True:
            h, w = self.stdscr.getmaxyx()
            self.stdscr.clear()
            self.draw_header()
            
            if self.view == VIEW_WORKSPACES:
                self.draw_workspaces()
            elif self.view == VIEW_TASKS:
                self.draw_tasks()
            elif self.view == VIEW_DETAIL:
                self.draw_detail()
            
            self.draw_footer()
            self.stdscr.refresh()

            key = self.stdscr.getch()

            if key == ord('q'):
                break
            
            elif key == curses.KEY_UP:
                if self.view == VIEW_DETAIL:
                    self.scroll_pos = max(0, self.scroll_pos - 1)
                else:
                    self.cursor_pos = max(0, self.cursor_pos - 1)
                    if self.cursor_pos < self.list_offset:
                        self.list_offset = self.cursor_pos
            
            elif key == curses.KEY_DOWN:
                if self.view == VIEW_DETAIL:
                    task = self.tasks[self.selected_task_idx]
                    lines = task.get('output', "").split('\n')
                    visible_lines = h - 11
                    if len(lines) > visible_lines:
                        self.scroll_pos = min(len(lines) - visible_lines, self.scroll_pos + 1)
                else:
                    limit = len(self.workspaces) if self.view == VIEW_WORKSPACES else len(self.tasks)
                    self.cursor_pos = min(max(0, limit - 1), self.cursor_pos + 1)
                    max_rows = h - 5
                    if self.cursor_pos >= self.list_offset + max_rows:
                        self.list_offset = self.cursor_pos - max_rows + 1

            elif key == curses.KEY_ENTER or key == 10 or key == 13:
                if self.view == VIEW_WORKSPACES:
                    if self.workspaces:
                        self.selected_ws = self.workspaces[self.cursor_pos]
                        self.view = VIEW_TASKS
                        self.cursor_pos = 0
                        self.list_offset = 0
                        self.refresh_data()
                elif self.view == VIEW_TASKS:
                    if self.tasks:
                        self.selected_task_idx = self.cursor_pos
                        self.view = VIEW_DETAIL
                        self.scroll_pos = 0
                
            elif key == curses.KEY_BACKSPACE or key == 127:
                if self.view == VIEW_DETAIL:
                    self.view = VIEW_TASKS
                    self.selected_task_idx = None
                    self.scroll_pos = 0
                elif self.view == VIEW_TASKS:
                    self.view = VIEW_WORKSPACES
                    self.selected_ws = None
                    self.cursor_pos = 0
                    self.list_offset = 0
                    self.refresh_data()

            elif key == ord('a'):
                if self.view != VIEW_DETAIL:
                    target_ws = self.selected_ws
                    if not target_ws and self.workspaces:
                        target_ws = self.workspaces[self.cursor_pos]
                    
                    if target_ws:
                        desc = self.get_user_input(f" Add task for {target_ws}: ")
                        if desc:
                            data = load_json(TASKS_FILE)
                            if target_ws not in data: data[target_ws] = []
                            data[target_ws].append({
                                "desc": desc,
                                "status": "todo",
                                "output": "",
                                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            })
                            save_json(TASKS_FILE, data)
                            self.refresh_data()

            elif key == ord('d'):
                if self.view == VIEW_TASKS and self.tasks:
                    idx = self.cursor_pos
                    data = load_json(TASKS_FILE)
                    ws_tasks = data.get(self.selected_ws, [])
                    if idx < len(ws_tasks):
                        ws_tasks[idx]['status'] = 'done'
                        save_json(TASKS_FILE, data)
                        self.refresh_data()

if __name__ == "__main__":
    curses.wrapper(AGUplinkCLI)
