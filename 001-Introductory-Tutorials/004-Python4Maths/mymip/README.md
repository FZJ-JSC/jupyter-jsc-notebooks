
Basic CPLEX wrapper for python 3.x At the moment talks directly to
CPLEX only, future versions will hopefully allow using gurobi or 
other solvers with the same interface.

The module looks for `cplex*.dll` in various places under Windows
(or `libcplex*.so` for Linux). If it cannot find it, you may need to
manually edit the `loadCPLEX()` function in the mycplex.py file, or
add a link to the cplex library into this directory.

To update to a new version of CPLEX:
  * Update top of mycplex.py to make sure it finds the right library
    (may work automatially if you are lucky)
  * use makecpxconst.py to create a new cpxconst.py (possibly editing location
    of the cplex library again)
