from tkinter import *
from tkinter import ttk
from tkinter import filedialog
from os import path, getcwd, remove
from base64 import b64decode
from datetime import datetime
from secrets import token_urlsafe


class Empty(Exception):
    pass


class VertexStack:
    class _Element:
        def __init__(self, data):
            if len(data) != 6:
                raise ValueError("Invalid data entry. Expected structure: [line1, line2, text, x, y]")
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
    id = ""

    def __init__(self, parent, log, **kwargs):
        super().__init__(parent, **kwargs)
        self.grid(column=1, rowspan=5, sticky=(N, S, E, W))
        self.create_rectangle(4, 4, 500, 350, outline="dim gray", width=2, fill="white")
        self.bind("<Button-1>", self.addVertex)
        self.bind("<Control-z>", self.deleteLast)
        self._log = log

        self._vertex_count = 0
        self._vertices = VertexStack()
        self._last_action = []
        self._lines = []

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
        self.id = ''.join([c for c in token_urlsafe(10) if c not in '-_OI0l'])[:5]
        self._vertex_count += 1
    
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

    def restoreLast(self):
        if len(self._last_action) == 0:
            return

        x, y = self._last_action[3], self._last_action[4]
        l1 = self.create_line((x-self._CROSS_SIZE, y, x+self._CROSS_SIZE, y), fill="red", width=3)
        l2 = self.create_line((x, y-self._CROSS_SIZE, x, y+self._CROSS_SIZE), fill="red", width=3)
        t = self.create_text((x+self._CROSS_SIZE, y-self._CROSS_SIZE), text=self._LABELS[self._vertex_count], anchor="sw", font="TkMenuFont", fill="dim gray")
        
        self._vertices.push([l1, l2, t, x, y, "q"+str(self._vertex_count)])
        self._vertex_count += 1
        self._last_action = []

    def getStackSnapshot(self):
        return self._vertices
    
    def __len__(self):
        return len(self._vertices)

    def deleteLines(self):
        for l in self._lines:
            self.delete(l)

    def generateHamiltonian(self):
        self.deleteLines()
        distances = {}
        for i in range(len(self._vertices)):
            for j in range(i+1, len(self._vertices)):
                point1 = self._vertices.get(i)
                point2 = self._vertices.get(j)
                d = float("{:.2f}".format(((point2[3]-point1[3])**2 + (point2[4]-point1[4])**2)**0.5))
                distances[str(point1[5]+point2[5])] = d
                distances[str(point2[5]+point1[5])] = d
                self._lines.append(self.create_line((point1[3], point1[4], point2[3], point2[4]), fill="light gray", width=2))
                self._lines.append(self.create_text(((point1[3]+point2[3])/2, (point1[4]+point2[4])/2 - 5), text=str(d), anchor="sw", font="TkMenuFont", fill="light gray"))
        tour = TourMatrix(len(self._vertices), distances)
        
        return tour.getHamiltonian()
        
class TourMatrix():
    SCALE = 0.01

    def __init__(self, dim, dist):
        counter = 0
        self._field = []
        for _ in range(dim):
            f = []
            for _ in range(dim):
                f.append("q"+str(counter))
                counter += 1
            self._field.append(f)
        self._dim = dim
        self._distances = dist

    def getHamiltonian(self):
        h = [[0.0 for x in range(self._dim**2)] for y in range(self._dim**2)]
        # Diagonal
        for i in range(len(h)):
            h[i][i] = -8.0
        # "1 entry/row and 1 entry/column is allowed" rule
        for i in range(len(self._field)):
            for j in range(len(self._field[i])):
                # Iterate row
                for k in self._field[i][j+1:]:
                    index = str(self._field[i][j]+k).split("q")[1:]
                    h[int(index[0])][int(index[1])] = 8.0
                # Iterate column
                for k in range(len(self._field)):
                    if k > i:
                        index = str(self._field[i][j]+self._field[k][j]).split("q")[1:]
                        h[int(index[0])][int(index[1])] = 8.0
        # "distances" rule
        for i in range(len(self._field)):
            for j in range(len(self._field[i])):
                for k in range(len(self._field)):
                    if k == i:
                        continue
                    field1 = int(self._field[i][j][1:])
                    field2 = int(self._field[k][(j+1) % len(self._field[i])][1:])
                    if field1 < field2:
                        h[field1][field2] = float("{:.1f}".format(self._distances["q"+str(i)+"q"+str(k)]*self.SCALE))
                    else:
                        h[field2][field1] = float("{:.1f}".format(self._distances["q"+str(i)+"q"+str(k)]*self.SCALE))

        return h

class LogWindow(Text):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        # Configure tags
        self.tag_configure("warning", foreground="#e0ba1f")
        self.tag_configure("error", foreground="#e0291f")
        self.tag_configure("notification", foreground="black")

        self.insert('end', "--- GRAPH TO MATRIX - TSPQ (v.1.1.0) ---\n")
        self.insert('end', "[" + datetime.now().strftime("%Y/%m/%d %H:%M:%S") + "] START LOG")

        self['state'] = "disabled"
    
    def insertToGrid(self):
        self.grid(columnspan=3, row=7, sticky=(N, S, E, W), padx=10, pady=10)

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


class GraphToHMatrix:
    global DESC_PADDING
    DESC_PADDING = 30
    h_matrix = []
    h_matrix_name = "- n.a. -"
    tex_equation = {}

    def __init__(self, root):
        # Basic options
        self._root = root
        self._root.title("Graph to Matrix - TSPQ")
        self._generated = StringVar(value="Generated: "+self.h_matrix_name)

        # Create menu bar
        menubar = Menu(self._root)
        root['menu'] = menubar
        menu_file = Menu(menubar)
        menu_edit = Menu(menubar)
        menubar.add_cascade(menu=menu_file, label='File')
        menubar.add_cascade(menu=menu_edit, label='Edit')
        menu_file.add_command(label='Clear', command=self._clearCanvas)
        menu_file.add_command(label='Open...', command=self._openFile)
        menu_file.add_command(label='Exit', command=self._exitProgram)
        menu_edit.add_command(label='Undo', command=self._undo)
        menu_edit.add_command(label='Redo', command=self._redo)

        # Title
        ttk.Label(self._root, text="Draw on the canvas to set vertices.").grid(column=1, row=1, sticky=W)

        # Logging window
        self._log = LogWindow(self._root, width=40, height=5, background="white", wrap="none", state="normal")
        # Canvas
        self._c = GraphCanvas(self._root, self._log, width=500, height=350, background="white")

        # Labels and buttons
        ttk.Label(self._root, text="Click to generate the distances\nand the Hamilton matrix.\nThis can take a few moments,\ndepending on the number of\nvertices drawn.", justify="center").grid(column=2, row=2, padx=DESC_PADDING)
        ttk.Button(self._root, text="Generate", command=self._generateHamiltonian).grid(column=2, row=3)
        ttk.Label(self._root, textvariable=self._generated).grid(column=2, row=4)
        ttk.Button(self._root, text="Save Hamiltonian...", command=self._saveHamil).grid(column=2, row=5)
        ttk.Button(self._root, text="Save Vertices...", command=self._saveConfig).grid(column=2, row=6)

        self._log.insertToGrid()
        # Key bindings and shortcuts
        self._root.bind_all("<Control-z>", self._undo)
        self._root.bind_all("<Control-y>", self._redo)

    def _generateHamiltonian(self):
        self._log.logMsg("Generating Hamiltonian, please stand by...", "warning")
        self.h_matrix = self._c.generateHamiltonian()
        self.h_matrix_name = "hmatrix-" + self._c.id + "_x" + str(len(self.h_matrix))
        self._log.logMsg("Generating complete! Result: " + self.h_matrix_name)
        self._generated.set("Generated: "+self.h_matrix_name)

    def _saveHamil(self):
        if len(self.h_matrix) == 0:
            self._log.logMsg("Unable to save Hamilton matrix. No matrix generated ({0})".format(self.h_matrix), "error")
            return
        filename = filedialog.asksaveasfilename(initialfile=self.h_matrix_name+".txt", defaultextension=".txt", filetypes=[("Text Document", "*.txt"),("All Files", "*.*")])
        if not filename:
            self._log.logMsg("Unable to save Hamilton matrix. No save location specified", "error")
            return
        self._log.logMsg("Saving Hamilton matrix in: {0}".format(filename))
        content = ""
        for i in range(len(self.h_matrix)):
            for j in range(len(self.h_matrix[i])):
                content += str(self.h_matrix[i][j]) + " "
            content = content[:-1]
            if i != len(self.h_matrix) - 1:
                content += "\n"
        
        f = open(filename, "w")
        f.write(content)
        f.close()
        self._log.logMsg("Saving complete!")

    def _saveConfig(self):
        if len(self._c) == 0:
            self._log.logMsg("Unable to save configuration file. No vertices set (%d)" % len(self._c), "error")
            return

        filename = filedialog.asksaveasfilename(initialfile=self._c.id+".vertices", defaultextension=".vertices", filetypes=(("Vertices File", "*.vertices"), ("All Files", "*.*")))
        if not filename:
            self._log.logMsg("Unable to save configuration file. No save location specified", "error")
            return
        self._log.logMsg("Saving configuration file in: {0}".format(filename))
        vertices = self._c.getStackSnapshot()
        content = vertices.stringify()
        f = open(filename, "w")
        f.write(content)
        f.close()
        self._log.logMsg("Saving complete!")
        
    
    # Menubar functions
    def _clearCanvas(self):
        for _ in range(len(self._c)):
            self._c.deleteLast()
        self._c.deleteLines()

    def _openFile(self):
        filename = filedialog.askopenfilename(initialdir="./", filetypes=(("Vertices File", "*.vertices"),("All Files", "*.*")))
        if not filename:
            self._log.logMsg("Unable to load configuration file. No file specified", "error")
            return
        self._log.logMsg("Importing vertices configuration from {0}".format(filename))
        self._clearCanvas()
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
        self._log.logMsg("Import complete!")

    def _exitProgram(self):
        self._root.destroy()

    def _undo(self, e=None):
        self._c.deleteLast()

    def _redo(self, e=None):
        self._c.restoreLast()
    

if __name__ == "__main__":
    root = Tk()
    window = GraphToHMatrix(root)
    root.mainloop()