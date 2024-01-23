from tkinter import *
from tkinter import ttk
from tkinter import filedialog
from os import path, getcwd, remove
from base64 import b64decode
from datetime import datetime


class Empty(Exception):
    pass


class VertexStack:
    class _Element:
        def __init__(self, data):
            if len(data) != 6:
                raise ValueError(
                    "Invalid data entry. Expected structure: [line1, line2, text, x, y]")
            self._data = data

        def __str__(self):
            return "(L1: {0} L2: {1}, T: {2}, X: {3}, Y: {4}, Q: {5})".format(self._data[0], self._data[1], self._data[2], self._data[3], self._data[4], self._data[5])

        def get(self):
            return self._data

    def __init__(self):
        self._data = []

    def __len__(self):
        return len(self._data)

    def is_empty(self):
        return len(self._data) == 0

    def push(self, d):
        self._data.append(self._Element(d))

    def top(self):
        if self.is_empty():
            raise Empty('Stack is empty')
        return self._data[-1]

    def pop(self):
        if self.is_empty():
            return None
        d = self._data[-1].get()
        self._data.pop()
        return d

    def stringify(self):
        result = ""
        for d in self._data:
            c = d.get()
            result += str(c[3]) + " " + str(c[4]) + "\n"
        return result

    def get(self, e):
        if self.is_empty() or e >= len(self._data):
            raise Empty('Something is wrong')
        return self._data[e].get()


class Event:
    def __init__(self, x, y):
        self.x = x
        self.y = y


class GraphCanvas(Canvas):
    _CROSS_SIZE = 7
    _LABELS = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N', 'O', 'P', 'Q', 'R', 'S', 'T', 'U', 'V', 'W', 'X', 'Y', 'Z']

    def __init__(self, parent, log, **kwargs):
        super().__init__(parent, **kwargs)
        self.grid(columnspan=4, row=2, sticky=(N, S, E, W))
        self.create_rectangle(4, 4, 500, 350, outline="dim gray", width=2, fill="white")
        self._log = log

        self._vertex_count = 0
        self._vertices = VertexStack()
        self._lines = []

    def __len__(self):
        return len(self._vertices)

    def addVertex(self, event):
        x, y = event.x, event.y
        if self._vertex_count >= len(self._LABELS):
            self._log.logMsg("ERROR: Maximum number of vertices (%d) reached! Last entry will not be saved." % len(self._LABELS), "error")
            return
        l1 = self.create_line((x-self._CROSS_SIZE, y, x+self._CROSS_SIZE, y), fill="red", width=3)
        l2 = self.create_line((x, y-self._CROSS_SIZE, x, y+self._CROSS_SIZE), fill="red", width=3)
        t = self.create_text((x+self._CROSS_SIZE, y-self._CROSS_SIZE), text=self._LABELS[self._vertex_count], anchor="sw", font="TkMenuFont", fill="dim gray")
        
        self._log.logMsg("Added vertex at: x = {0}, y = {1}".format(x, y))
        if self._vertex_count == 8:
            self._log.logMsg("Computational limit of D-Wave 2000Q (8) exceeded. Are you sure you want to add more vertices?", "warning")
        self._vertices.push([l1, l2, t, x, y, "q"+str(self._vertex_count)])
        self._vertex_count += 1
    
    def drawTour(self, tour, num):
        tour_matrix = []
        points = []
        for i in range(0, len(tour)-1, len(self._vertices)):
            tour_matrix.append(tour[i:i+int(len(tour)**0.5)])
        for i in range(len(tour_matrix[0])):
            for j in range(len(tour_matrix)):
                if tour_matrix[j][i] == 1:
                    points.append(self._vertices.get(j))
                    if len(points) > 1:
                        d = float("{:.2f}".format(((points[-2][3]-points[-1][3])**2 + (points[-2][4]-points[-1][4])**2)**0.5))
                        self._lines.append(self.create_line((points[-1][3], points[-1][4], points[-2][3], points[-2][4]), fill="lime green", width=2))
                        self._lines.append(self.create_text(((points[-1][3]+points[-2][3])/2, (points[-1][4]+points[-2][4])/2 - 5), text=str(d), anchor="sw", font="TkMenuFont", fill="lime green"))
        d = float("{:.2f}".format(((points[-1][3]-points[0][3])**2 + (points[-1][4]-points[0][4])**2)**0.5))
        self._lines.append(self.create_line((points[-1][3], points[-1][4], points[0][3], points[0][4]), fill="lime green", width=2))
        self._lines.append(self.create_text(((points[-1][3]+points[0][3])/2, (points[-1][4]+points[0][4])/2 - 5), text=str(d), anchor="sw", font="TkMenuFont", fill="lime green"))

        self._log.logMsg("Drawn tour {0} | Energy: {1} {2}".format(num, tour[-1], ("(best)" if num == 0 else "")))

    def deleteLast(self):
        d = self._vertices.pop()
        if not d:
            self._log.logMsg("Cannot perform undo action. Canvas already empty", "warning")
            return
        self._last_action = d[:]
        
        self.delete(d[0])
        self.delete(d[1])
        self.delete(d[2])
        self._vertex_count -= 1

    def deleteLines(self):
        for l in self._lines:
            self.delete(l)


class LogWindow(Text):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        # Configure tags
        self.tag_configure("warning", foreground="#e0ba1f")
        self.tag_configure("error", foreground="#e0291f")
        self.tag_configure("notification", foreground="black")

        self.insert('end', "--- PATH VISUALIZER - TSPQ (v.1.0.1) ---\n")
        self.insert('end', "[" + datetime.now().strftime("%Y/%m/%d %H:%M:%S") + "] START LOG")

        self['state'] = "disabled"
    
    def insertToGrid(self):
        self.grid(columnspan=4, row=5, sticky=(N, S, E, W), padx=10, pady=10)

    def logMsg(self, msg, msg_type="notification"):
        msg_types = ["notification", "warning", "error"]
        if msg_type not in msg_types:
            raise ValueError("Invalid message type. Expected one of: %s" % msg_types)

        numlines = int(self.index('end - 1 line').split('.')[0])
        self['state'] = 'normal'
        if numlines == 24:
            self.delete(1.0, 2.0)
        if self.index('end-1c') != '1.0':
            self.insert('end', '\n')

        self.insert('end', "[" + datetime.now().strftime("%Y/%m/%d %H:%M:%S") + "] " + msg, (msg_type))
        self.see('end')
        self['state'] = 'disabled'


class PathVisualizer():
    solution_name = "- n. a. -"
    config_name = "- n. a. -"

    def __init__(self, root):
        # Basic options
        self._root = root
        self._root.title("Path Visualizer - TSPQ")
        self._opened_solution = StringVar(value="Opened solution(s): "+self.solution_name)
        self._opened_config = StringVar(value="Opened graph: "+self.config_name)

        # Create menu bar
        menubar = Menu(self._root)
        root['menu'] = menubar
        menu_file = Menu(menubar)
        menu_edit = Menu(menubar)
        menubar.add_cascade(menu=menu_file, label='File')
        menu_file.add_command(label='Clear', command=self._clearCanvas)
        menu_file.add_command(label='Open solution...', command=self._openSolution)
        menu_file.add_command(label='Open graph...', command=self._openConfig)
        menu_file.add_command(label='Exit', command=self._exitProgram)

        # Title
        ttk.Label(self._root, text="View the trips calculated by the quantum annealer on the canvas.", justify="center").grid(columnspan=4, row=1)

        # Logging window
        self._log = LogWindow(self._root, width=40, height=5, background="white", wrap="none", state="normal")
        # Canvas
        self._c = GraphCanvas(self._root, self._log, width=500, height=350, background="white")

        # Labels and buttons
        ttk.Label(self._root, textvariable=self._opened_config, justify="center").grid(columnspan=2, row=3, column=0)
        ttk.Label(self._root, textvariable=self._opened_solution, justify="center").grid(columnspan=2, row=3, column=2)
        ttk.Button(self._root, text="<<<", command=self._prevSolution).grid(column=0, row=4, pady=10)
        ttk.Button(self._root, text=">>>", command=self._nextSolution).grid(column=3, row=4, pady=10)
        ttk.Button(self._root, text="Open graph...", command=self._openConfig).grid(column=1, row=4, pady=10)
        ttk.Button(self._root, text="Open solution(s)...", command=self._openSolution).grid(column=2, row=4, pady=10)

        self._log.insertToGrid()
        self._loadedSolutions = []
        self._display = 0

    def _openSolution(self):
        if len(self._c) == 0:
            self._log.logMsg("Importing aborted. Open a graph first before viewing the solutions", "error")
            return
        filename = filedialog.askopenfilename(initialdir="./", filetypes=(("Text Document", "*.txt"),("All Files", "*.*")))
        if not filename:
            self._log.logMsg("Unable to load solutions. No file specified", "error")
            return
        self._log.logMsg("Importing solutions from {0}".format(filename))
        self._loadedSolutions = []
        self._c.deleteLines()
        f = open(filename, "r")
        c = 0
        while True:
            c += 1
            line = f.readline()
            if not line or line == "\n":
                break
            try:
                array = line[line.find("[")+1:line.find("]")].split(" ")
                if len(array) != len(self._c)**2:
                    self._log.logMsg("Unable to parse solutions. Array size ({0}) is not the quadratic of the number of vertices ({1})".format(len(array), len(self._c)), "error")
                    return
                for i in range(len(array)):
                    array[i] = int(array[i])
                    if array[i] != 1 and array[i] != 0:
                        self._log.logMsg("Unable to parse solutions. Non-binary entry found (line %d)" % c, "error")
                        return
                array.append(float("{:.2f}".format(float(line[:line.find("\t")]))))
                self._loadedSolutions.append(array)
            except:
                self._log.logMsg("Unable to parse solutions. Corrupted data (line %d)" % c, "error")
                return
            if c == 10:
                break
        f.close()
        self.solution_name = filename[filename.rfind("/")+1:filename.rfind(".")]
        self._opened_solution.set("Opened graph: "+self.solution_name)
        self._display = 0
        self._c.drawTour(self._loadedSolutions[self._display], self._display)
        self._log.logMsg("Import complete!")

    def _openConfig(self):
        filename = filedialog.askopenfilename(initialdir="./", filetypes=(("Vertices File", "*.vertices"),("All Files", "*.*")))
        if not filename:
            self._log.logMsg("Unable to load configuration file. No file specified", "error")
            return
        self._log.logMsg("Importing vertices configuration from {0}".format(filename))
        self._clearCanvas()
        self._loadedSolutions = []
        f = open(filename, "r")
        c = 0
        while True:
            c += 1
            line = f.readline()
            if not line or line == "\n":
                break
            pos = line[:-1].split(" ")
            try:
                for i in range(len(pos)):
                    pos[i] = int(pos[i])
            except:
                self._log.logMsg("Unable to parse configuration file. Corrupted data format (line %d)" % c, "error")
                return
            if len(pos) != 2 or not isinstance(pos[0], int) or not isinstance(pos[1], int):
                self._log.logMsg("Unable to verify configuration data. Corrupted data (line %d)" % c, "error")
                return
            
            self._c.addVertex(Event(pos[0], pos[1]))

        f.close()
        self.config_name = filename[filename.rfind("/")+1:filename.rfind(".")]
        self._opened_config.set("Opened graph: "+self.config_name)
        self._log.logMsg("Import complete!")

    def _prevSolution(self):
        if self._display == 0:
            return
        self._c.deleteLines()
        self._display -= 1
        self._c.drawTour(self._loadedSolutions[self._display], self._display)

    def _nextSolution(self):
        if self._display == len(self._loadedSolutions)-1:
            return
        self._c.deleteLines()
        self._display += 1
        self._c.drawTour(self._loadedSolutions[self._display], self._display)


    def _clearCanvas(self):
        for _ in range(len(self._c)):
            self._c.deleteLast()
        self._c.deleteLines()
        self._loadedSolutions = []
        self.config_name = "- n. a. -"
        self.solution_name = "- n. a. -"
        self._opened_config.set("Opened graph: "+self.config_name)
        self._opened_solution.set("Opened solution(s): "+self.solution_name)

    def _exitProgram(self):
        self._root.destroy()


if __name__ == "__main__":
    root = Tk()
    window = PathVisualizer(root)
    root.mainloop()