#!/usr/bin/env python3
## Author: Andreas Ernst
## Summary: 
## Simple interface for letting python 3 talk straight to CPLEX
## The intention is to resturcture this to enable gurobi to be
## used likewise

import gc # need to disable garbage collection for speed
from ctypes import * # for direct access to dynamic library
try:
    from .cpxconst import * # constants from CPLEX header file
except:
    from cpxconst import * # in case we are running as main
from collections import Iterable
from types import GeneratorType
from numbers import Number # can check for numeric types
import os,re,sys
from array import array
import collections
#from cplex_wrap import *

CPLEXversion = 12.6  # what version of CPLEX is loaded (or will try to load by default)

__doc__ = """Module for defining and solving linear programming models.
The main elements of this module are
- class Model which allows an LP to be defined (see help(Model) )
- sum(list) simply add's together the elements of the list
- ZeroOne, Integer, Continuous represent the appropriate variable types
  to be used as in: x in ZeroOne (to define that x is binary)
Note that mostly things behave as you would expect them to.
Eg when you have defined variables x & y then 'x + 2 y == 3' will create
a constraint and '2 <= x <= 5' will set the bounds on the variable x.
After solving, the solution value will be stored in the .x field of
a variable (ie x.x & y.x would give the primal solution values)
Similarly the equation objects will have a .x field set to the dual values
In addition variables have a .rc (reduced cost) for linear programs and
equations a .slack field.

The module also includes a Network class for using the CPLEX network simplex solver. (see help(Network) for more details).

Example usage:
  import mymip
  from mymip import Model,  ZeroOne, Integer, Continuous, sum,mycplex
  m = Model()
  m.param[mycplex.CPX_PARAM_SCRIND] = mycplex.CPX_ON
  m.param['SCRIND'] = 'ON'  # as above and easier to read
  help(m.param) # find out more about available cplex parameters
  help(m.param['SCRIND']) # find out what this parameter does
  N = range(10)
  x = [ [ m.variable('x%d_%d'%(i,j) ) for j in N] for i in N]
  y = [m.variable('y',Integer,lb=-1,ub=10) for i in N]
  z = m.variable() # name is optional
  m.min( sum( x[i][j] for i in N for j in N ) )
  m.SubjectTo( 2 * sum(y) + z >= 3 )
  m.SubjectTo(
   {"C%d"%j: # add named constraints using dictionaries
     sum( i * x[i][j] for i in N ) == y[j] + z for j in N})
  # make all y's integer and z binary:
  y in Integer and  z in ZeroOne
  for i in N:
    for j in N: 0 <= x[i][j] <= 2
  # provide a starting solution where some/all of the variable values are set 
  m.mipStart( (y[i],1) for i in N)
  m.optimise()
  mycplex.cplex.CPXwriteprob(m.Env,m.LP,'myprob.mps','MPS')
  print y.x ## show y solution

Warning: There is a slight confusion in the syntax y <= 1 sets the upper
         bound for y while 1.0*y <= 1 is a constraint (similarly y==1 sets
         both bounds). Hence m.SubjectTo(y==1) will fail.

NOTE: The "cplex" object in mycplex makes most functions available:
      from mycplex import cplex
      cplex.CPXgetstat(..)
      The model has a .LP property and .Env is the environment
      eg given model M:
         from array import array
         slack = array('d',[0.0] * len(M.eqn))
         cplex.CPXgetslack(M.Env,M.LP,mycplex.ptr(slack),0,len(M.eqn))
SPEED:
* For speed reasons garbage collection is disabled from when a Model()
  is first created until the model is loaded (or optimised)
* mycplex.pSUM( (x[i],coeff[i]) for i in N ) is much faster than
  sum( coeff[i] * x[i] for i in N), particularly for large N
  However it assumes that each variable occurs at most once in the expression.
"""  


def ptr(X):
    "Return 'pointer' (address as long int) for an array object"
    return c_void_p(X.buffer_info()[0])

def loadCPLEX(CPXversionNo=int(CPLEXversion*10)):
    global CPLEXversion,cplex
    cplex=None
    CPLEXversion = CPXversionNo / 10.0
    CPLEXdllPath = ""
    try:
        if os.sys.platform.startswith("linux"):
            CPLEXdllPath="libcplex%d.so" % CPXversionNo
            if os.getenv("CPLEX_ROOT") and os.getenv("CPLEX_OS_TYPE"):
                for bindir in ["/bin/","/cplex/bin/"]:
                    tmp=os.getenv("CPLEX_ROOT")+bindir+os.getenv("CPLEX_OS_TYPE")
                    if not os.path.exists(tmp): continue
                    for fn in os.listdir(tmp):
                        libcplex = re.match("libcplex([0-9]*).so",fn)
                        if libcplex:
                            CPXversionNo = int(libcplex.group(1))
                            CPLEXversion = float(CPXversionNo)/10.0
                            CPLEXdllPath = tmp+os.sep+fn
                            break
            if not os.path.exists(CPLEXdllPath):
                for pathdir in os.getenv("PATH").split(":"):
                    if not os.path.isdir(pathdir): continue
                    for lib in os.listdir(pathdir):
                        m = re.match("libcplex([0-9]+).so",lib)
                        if m:
                           CPLEXversion=float(m.group(1))
                           while CPLEXversion > 100: CPLEXversion /= 10.0
                           CPLEXversion=float("%.3f"%CPLEXversion) # crude rounding
                           CPLEXdllPath=pathdir+os.sep+lib
                           break
            if not os.path.exists(CPLEXdllPath):
                CPLEX_ROOT="/usr/local/cplex"
                if os.getenv("CPLEX_ROOT"):
                    CPLEX_ROOT=os.getenv("CPLEX_ROOT")
                CPLEXdllPath="'libcplex1*.so'" # any version >=10 and < 20
                for line in os.popen("find %s -name %s -print" %
                                     (CPLEX_ROOT,CPLEXdllPath)):
                    libcplex=re.search("libcplex([0-9]*).so",line)
                    if libcplex:
                        CPXversionNo = int(libcplex.group(1))
                        while  CPLEXversion > 100: CPLEXversion /=10.0
                        CPLEXdllPath = line.strip()
                        break
            if not os.path.exists(CPLEXdllPath):
                print("ERROR: cannot find cplex. Please update mymip.mycplex")
                cplex = None
            else:
                cplex = cdll.LoadLibrary(CPLEXdllPath)
        else: # windows
            if os.path.exists(r"C:\Program Files\IBM\ILOG"):
                CPXversionNo = int(os.listdir(r"C:\Program Files\IBM\ILOG")[-1].split("Studio")[-1])
                CPLEXversion = CPXversionNo
                while CPLEXversion > 100: CPLEXversion /= 10.0
                #print("Attempting to load CPLEX version %.2f" % CPLEXversion)
            for path in [".", r"C:\Program Files\IBM\ILOG\CPLEX_Studio%d\cplex\bin\x64_win64"%CPXversionNo] + [ p+os.sep+"mymip" for p in sys.path]:
                if os.path.exists(path) and ("cplex%d.dll"%CPXversionNo) in os.listdir(path):
                    CPLEXdllPath = path+os.sep+"cplex%d.dll"%CPXversionNo
                    #print "Trying loading of '%s'" % CPLEXdllPath
                    cplex = cdll.LoadLibrary(CPLEXdllPath)
                    break
    except Exception as error:
        raise ImportError("ERROR: cannot find CPLEX %.1f dll (%s)"% (
                CPLEXversion,CPLEXdllPath)+error.message)

loadCPLEX()

## ipynb stuff
def in_ipynb():
    try:
        get_ipython().config['IPKernelApp']['parent_appname']
        return True
    except:
        return False

if in_ipynb():
    import io,ctypes
    import tempfile
    from contextlib import contextmanager
    # use_errno parameter is optional, because I'm not checking errno anyway.
    libc = ctypes.CDLL(ctypes.util.find_library('c'), use_errno=True)
    class FILE(ctypes.Structure):
        pass
    FILE_p = ctypes.POINTER(FILE)
    # Alternatively, we can just use:
    # FILE_p = ctypes.c_void_p
    # These variables, defined inside the C library, are readonly.
    cstdin = FILE_p.in_dll(libc, 'stdin')
    cstdout = FILE_p.in_dll(libc, 'stdout')
    cstderr = FILE_p.in_dll(libc, 'stderr')
    # C function to disable buffering.
    csetbuf = libc.setbuf
    csetbuf.argtypes = (FILE_p, ctypes.c_char_p)
    csetbuf.restype = None
    # C function to flush the C library buffer.
    cfflush = libc.fflush
    cfflush.argtypes = (FILE_p,)
    cfflush.restype = ctypes.c_int
else:
    def capture_c_stdout(encoding='whatever'):
        "dummy function to allow 'with capture_c_stdout():' statement"
        return open('/dev/null','r') 

if in_ipynb():
  @contextmanager
  def capture_c_stdout(encoding='utf8'):
    # Flushing, it's a good practice.
    sys.stdout.flush()
    cfflush(cstdout)

    # We need to use a actual file because we need the file descriptor number.
    with tempfile.TemporaryFile(buffering=0) as temp:
        # Saving a copy of the original stdout.
        prev_sys_stdout = sys.stdout
        prev_stdout_fd = os.dup(1)
        os.close(1)

        # Duplicating the temporary file fd into the stdout fd.
        # In other words, replacing the stdout.
        os.dup2(temp.fileno(), 1)

        # Replacing sys.stdout for Python code.
        #
        # IPython Notebook version of sys.stdout is actually an
        # in-memory OutStream, so it does not have a file descriptor.
        # We need to replace sys.stdout so that interleaved Python
        # and C output gets captured in the correct order.
        #
        # We enable line_buffering to force a flush after each line.
        # And write_through to force all data to be passed through the
        # wrapper directly into the binary temporary file.
        temp_wrapper = io.TextIOWrapper(
            temp, encoding=encoding, line_buffering=True, write_through=True)
        sys.stdout = temp_wrapper

        # Disabling buffering of C stdout.
        csetbuf(cstdout, None)

        yield

        # Must flush to clear the C library buffer.
        cfflush(cstdout)

        # Restoring stdout.
        os.dup2(prev_stdout_fd, 1)
        os.close(prev_stdout_fd)
        sys.stdout = prev_sys_stdout

        # Printing the captured output.
        temp_wrapper.seek(0)
        print(temp_wrapper.read(), end='')

class EnvHolder:
    """Class to hold the CPLEX environment and unload cplex when
    the module is unloaded (program execution all done"""
    def __init__(self,Env):
        self.env = Env
    def __del__(self):
        print("Closing CPLEX")
        cplex.CPXcloseCPLEX.argypes=[c_void_p]
        status = cplex.CPXcloseCPLEX(byref(self.env))
        if status: print("ERROR: unable to close CPLEX library",status)
        
status = c_int(-99)
cplex.CPXopenCPLEX.restype = c_void_p
Env = c_void_p(cplex.CPXopenCPLEX(byref(status)))
if status.value != 0:
    print("ERROR %d: can't open CPLEX" % status.value)
    raise ImportError ## can't load cplex library
_envholder = EnvHolder(Env) # to ensure closure of CPLEX at the end

ListType=type([])
DictType=type({})
TupleType=type((1,2))
def isIterable(obj): return not isinstance(obj, str) and isinstance(obj, Iterable)

class VariableType:
    """Allows setting of a variable type (eg Binary)"""
    def __init__(self,type,lower=-1e+20,upper=+1e+20):
        self.continuous = (type == b'C')
        self.lb = lower
        self.ub = upper
    def __contains__(self,var):
        "x in VariableType should set type (& optionally bounds)"
        if type(var) == Variable:
            var.setContinuous(self.continuous)
            if self.lb <= self.ub:
                var.setLower(self.lb)
                var.setUpper(self.ub)
        else:
            for v in var: self.__contains__(v)
        return True # always true afterwards

ZeroOne = VariableType(b'B',0,1)
Integer = VariableType(b'I')
Continuous = VariableType(b'C')
SemiCont = VariableType(b'S')
SemiInt = VariableType(b'N')
    
class Constraint(object):
    """Row of a linear program
    Constraints can be defined by comparing two expressions
    The solver will set a .x field with the dual value after any
    successful solve (if the problem has no integer variables).
    The .slack field is set to the slack value after a solve
    The .id field gives the CPLEX row index."""
    def __init__(self,LHS,sense,RHS):
        """LHS & RHS are expressions (or numbers), sense is one of L/E/G"""
        #zero = Expression(0)
        self.LHS=LHS-RHS # copies expression 
        #if type(LHS) is Expression:
        #    self.LHS = LHS - RHS # make sure we copy expression
        #else:
        #    self.LHS = zero + LHS 
        #self.LHS -= RHS
        self.RHS = -self.LHS[None]
        del self.LHS[None]
        self.sense = sense
        self._model = None
        self.id = -1
        self.name=""

    def setModel(self,model,id):
        self._model = model
        self.id = id
        self.LHS = None # clear coefficient store -> already in model

    def __str__(self):
        """Pretty-print version"""
        sense = { b'L' : " <= ", b'E' : " == ", b'G' : " >= "}
        if self.id >= 0:
            return "Constraint %d" % self.id
        else:
            return str(self.LHS) + sense[self.sense] + str(self.RHS)

class Expression(object):
    """Linear combination of variables."""
    
    def __init__(self,coeff=0,variable=None):
        "Create an exression with a single term"
        self._expr = { variable: coeff }

    def __getitem__(self,var):
        "Get coefficient of variable var"
        return self._expr.get(var,0)
    
    def __delitem__(self,var):
        "Delete variable from expression"
        if var in self._expr: del self._expr[var]
    
    def __len__(self):
        "Number of entries in expression"
        return len(self._expr)
    
    def items(self):
        "Return list of (variable,coefficient) pairs"
        return self._expr.items()   

    def set(self,items):
        "Set expression given list/iterable of (variable,coefficient) pairs"
        self._expr = dict(items)
        return self
    
    def copy(self):
        "Create a copy of the expression"
        result = Expression()
        result._expr = self._expr.copy()
        return result

    def __add__(self,other):
        return self.copy().__iadd__(other)

    def __radd__(self,other):
        return self.copy().__iadd__(other)

    def __iadd__(self,other):
        typeOther = type(other)
        if isinstance(other,Number):
            if other: #don't bother for zero values
                self._expr[None] = self._expr.get(None,0) + other
        elif typeOther is Expression:
            for (key,value) in other._expr.items():
                self._expr[key] = value + self._expr.get(key,0)
        elif typeOther is Variable:
            self._expr[other] = 1.0 + self._expr.get(other,0)
        else:
            raise TypeError( "%s incompatible operand in addition" % other)
        return self

    def __sub__(self,other):
        "self - other"
        return self.copy().__isub__(other)

    def __rsub__(self,other):
        "other - self"
        otherNum = float(other) # only called if other is not object
        result = self.copy()
        result *= -1
        result._expr[None] = result._expr.get(None,0) + otherNum
        return result

    def __isub__(self,other):
        "Subtract other from self"
        typeOther = type(other)
        if isinstance(other,Number):
            self._expr[None] = self._expr.get(None,0) - other
        elif typeOther is Expression:
                for (key,value) in other._expr.items():
                    self._expr[key] = self._expr.get(key,0) - value 
        elif typeOther is Variable:
                self._expr[other] = self._expr.get(other,0) - 1.0 
        else:
            raise TypeError("%s incompatible operand in addition" % other)
        return self
   
    def __div__(self,number):
        return self.copy().__idiv__(number)

    def __mul__(self,other):
        "Multiply expression by a number"
        return self.copy().__imul__(other)
        
    def __rmul__(self,other):
        "(Pre-) multiply expression with a number"
        return self.copy().__imul__(other)
        
    def __imul__(self,other):
        "Modify expression by multiplying with a constant"
        otherNum = float(other) # should cause exception if not float/int
        for (key,value) in self._expr.items():
            self._expr[key] *= otherNum
        return self

    def __idiv__(self,other):
        "Modify expression by dividing with a constant"
        otherNum = float(other) # should cause exception if not float/int
        for (key,value) in self._expr.items():
            self._expr[key] /= otherNum
        return self

    def __le__(self,other):
        """self <= other: defines a constraint"""
        return Constraint(self,b'L',other)
    def __ge__(self,other):
        """self >= other: defines a constraint"""
        return Constraint(self,b'G',other)
    def __eq__(self,other):
        """self == other: defines a constraint"""
        return Constraint(self,b'E',other)

    def __str__(self):
        "Printable version of expression (not executable python code)"
        result = str(self._expr.get(None,""))
        for (key,value) in self._expr.items():
            if key != None and value != 0:
                if value > 0: result += " + "
                else:         result += " - "
                if abs(value) != 1: result += str(abs(value)) + " "
                result += str(key)
        return result
        
ExpressionType = type(Expression())

def pSUM(pairList):
    """pSUM( (variable,coefficient) for ....) creates an expression of coefficient*variable.
    Assumes that each variable occurs at most once, though they can be in arbitrary order."""
    return Expression().set(pairList)
    

class Variable(object):
    """Linear programming variable
    Variables may be added or multiplied by a number to give an expression
    The .lb, .ub and .continous fields should be considered READ ONLY,
    use setLower(), setUpper(), setContinuous() to modify these.
    The model will set a .x field with the solution if solve is successful
    the .id field gives the CPLEX column index.
    """
    def __init__(self, model, name, id,Type=b'C'):
        self.id  = id
        self._model = model
        self._name = name
        if type(Type) == type(ZeroOne):
            self.lb = Type.lb
            self.ub = Type.ub
            self.continuous = Type.continuous
        else:
            self.lb = 0
            self.ub = 1e+20
            self.continuous = (Type == b'C')
    def __hash__(self): return self.id # dangerous as id might change
    def __mul__(self,number):
        return Expression(float(number),self)
    def __rmul__(self,number):
        return Expression(float(number),self)
    def __div__(self,number):
        return Expression(1.0/float(number),self)
    def __add__(self,other):
        return Expression(1.0,self).__iadd__(other)
    def __radd__(self,other):
        return Expression(1.0,self).__iadd__(other)
    def __sub__(self,other):
        return Expression(1.0,self).__isub__(other)
    def __rsub__(self,other):
        return Expression(-1.0,self).__iadd__(other)
    def setUpper(self,value):
        "Set upper bound: possibly updating model directly"
        self.ub = float(value)
        if self._model.solverInitialised:
            indices = c_int(self.id)
            bd = c_double(value)
            cplex.CPXchgbds(self._model.Env,self._model.LP,c_int(1),
                            byref(indices),c_char_p(b"U"),byref(bd))
    def setLower(self,value):
        "Set lower bound: possibly updating model directly"
        self.lb = float(value)
        if self._model.solverInitialised:
            indices = c_int(self.id)
            bd = c_double(value)
            cplex.CPXchgbds(self._model.Env,self._model.LP,c_int(1),
                            byref(indices),c_char_p(b"L"),byref(bd))
    def getCost(self):
        "Return cost coefficient"
        if 0 <= self.id < len(self._model.obj):
            return self._model.obj[self.id]
        return 0
    def setCost(self,cost):
        "Set cost coefficient of variable"
        self._model.setCosts([(self,cost)])
    def setContinuous(self,continuous):
        if self.continuous == continuous: return
        self.continuous = continuous
        if self._model.solverInitialised:
            indices = array('i',[self.id])
            if continuous: ctype = array('b',b"C")
            else:         ctype = array('b',b"I")
            cplex.CPXchgctype(self._model.Env,self._model.LP,c_int(1),
                              ptr(indices),ptr(ctype))

    def __le__(self,other):
        if isinstance(other,Number):
            self.setUpper(other)
            return self.lb <= self.ub
        elif type(other) is type(self) or type(other) is ExpressionType:
            return Expression(1.0,self) <= other
        return False
        
    def __ge__(self,other):
        if isinstance(other,Number):
            self.setLower(other)
            return self.lb <= self.ub
        elif type(other) is type(self) or type(other) is ExpressionType:
            return Expression(1.0,self) >= other
        return False

    def __eq__(self,other):
        if isinstance(other,Number):
            self.setLower(other)
            self.setUpper(other)
            return 1
        elif type(other) is type(self) or type(other) is ExpressionType:
            return Expression(1.0,self) == other
        return False
    
        
    def __str__(self):
        return self._name
        
def sum(X,start=0):
    "Replacement for standard sum that does incremental add"
    for x in X: start += x
    return start

# def sum(list):
#     """Return the sum of first argument."""
#     if list == []: return 0
#     return reduce(lambda x,y: x+y,list)

class CpxParam:
    ## _pType[name] = {0,1,2,3} for double/bool/int/string
    ## _p[name] = index used by CPLEX
    ## _v[name] = value of symbolic name (eg ON/OFF)
    """This class is used to query and change CPLEX parameters.
    It looks like a dictionary where param[name] gives the value
    of the named parameter (names are as per cplex.h #defines
    without CPX_PARM_: so CPX_PARAM_STARTALG is param['STARTALG']).
    Note that for assignment the right hand side can be a numeric
    value or the string name of a constant (without CPX prefix).
    Eg: param['STARTALG'] = 'ALG_NET'  or param['EPAGAP'] = 0.01
    Documentation on parameters is available through help:
    param.help('STARTALG')

    WARNING: The documentation has not been updated since at least CPLEX 10.1
    """
    ## _p contains: (parameter number,parameter type, documentation)
    ##  type = 0 (double), 1 (bool), 2 (int) or 3 (string)
    _p = { 
        "ADVIND" : (1001,2,"""Advanced start indicator. 
If set to 1 or 2, this parameter indicates that CPLEX should use advanced starting information when optimization is initiated. 
For MIP models, settings 1 and 2 are currently identical. Both will cause CPLEX to continue with a partially explored MIP tree if one is available. If tree exploration has not yet begun, settings 1 or 2 indicate that CPLEX should use a loaded MIP start, if available. 
For continuous models solved with simplex, setting 1 will use the currently loaded basis. If a basis is available only for the original, unpresolved model, or if CPLEX has a start vector rather than a simplex basis, then the simplex algorithm will proceed on the unpresolved model. With setting 2, CPLEX will first perform presolve on the model and on the basis or start vector, and then proceed with optimization on the presolved problem.  
Setting 2 can be particularly useful for solving fixed MIP models, where a start vector but no corresponding basis is available. 
 For continuous models solved with the barrier algorithm, settings 1 or 2 will continue optimization from the last available barrier iterate. """),
"AGGCUTLIM" : (2054,2,"""Constraint aggregation limit for cut generation. 
Limits the number of constraints that can be aggregated for generating flow cover and mixed integer rounding cuts. """),
"AGGFILL" : (1002,2,"""Preprocessing aggregator fill. 
Limits variable substitutions by the aggregator. If the net result of a single substitution is more nonzeros than this value, the substitution is not made. """),
"AGGIND" : (1003,2,"""Preprocessing aggregator application limit. 
Invokes the aggregator to use substitution where possible to reduce the number of rows and columns before the problem is solved. If set to a positive value, the aggregator is applied the specified number of times or until no more reductions are possible. """),
"ADVIND" : (1001,3,"""If set to 1 or 2, this parameter indicates that CPLEX should use advanced starting information when optimization is initiated.
For MIP models, setting 1 (one) will cause CPLEX to continue with a partially explored MIP tree if one is available. If tree exploration has not yet begun, setting 1 (one) specifies that CPLEX should use a loaded MIP start, if available. Setting 2 retains the current incumbent (if there is one), re-applies presolve, and starts a new search from a new root. Setting 2 can be particularly useful for solving fixed MIP models, where a start vector but no corresponding basis is available.
For continuous models solved with simplex, setting 1 (one) will use the currently loaded basis. If a basis is available only for the original, unpresolved model, or if CPLEX has a start vector rather than a simplex basis, then the simplex algorithm will proceed on the unpresolved model. With setting 2, CPLEX will first perform presolve on the model and on the basis or start vector, and then proceed with optimization on the presolved problem.
For continuous models solved with the barrier algorithm, settings 1 or 2 will continue optimization from the last available barrier iterate."""),
"BARALG" : (3007,2,"""Barrier algorithm. 
The default setting 0 uses the "infeasibility - estimate start" algorithm (setting 1) when solving subproblems in a MIP problem, and the standard barrier algorithm (setting 3) in other cases. The standard barrier algorithm is almost always fastest. However, on problems that are primal or dual infeasible (common for MIP subproblems), the standard algorithm may not work as well as the alternatives. The two alternative algorithms (settings 1 and 2) may eliminate numerical difficulties related to infeasibility, but are generally slower. """),
"BARCOLNZ" : (3009,2,"""Barrier column nonzeros. 
Used in the recognition of dense columns. If columns in the presolved and aggregated problem exist with more entries than this value, such columns are considered dense and are treated specially by the CPLEX Barrier Optimizer to reduce their effect. """),
"BARCROSSALG" : (3018,2,"""Barrier crossover algorithm. 
Determines which, if any, crossover is performed at the end of a barrier optimization. This parameter also applies when CPLEX uses the barrier algorithm to solve an LP or QP problem, or when it is used to solve the continuous relaxation of an MILP or MIQP at a node in a MIP. """),
"BARDISPLAY": (3010,2,"""Barrier display information. 
Determines the level of barrier progress information to be displayed. """),
"BAREPCOMP" : (3002,0,"""Convergence tolerance for LP and QP problems. 
For problems with quadratic constraints (QCP), see CPX_PARAM_BARQCPEPCOMP. 
Sets the tolerance on complementarity for convergence. The barrier algorithm terminates with an optimal solution if the relative complementarity is smaller than this value. 
Changing this tolerance to a smaller value may result in greater numerical precision of the solution, but also increases the chance of a convergence failure in the algorithm and consequently may result in no solution at all. Therefore, caution is advised in deviating from the default setting. """),
"BARGROWTH" : (3003,0,"""Barrier growth limit. 
Used to detect unbounded optimal faces. At higher values, the barrier algorithm is less likely to conclude that the problem has an unbounded optimal face, but more likely to have numerical difficulties if the problem has an unbounded face. """),
"BARITLIM" : (3012,2,"""Barrier iteration limit. 
Sets the number of barrier iterations before termination. When set to 0, no barrier iterations occur, but problem "setup" occurs and information about the setup is displayed (such as Cholesky factor statistics). """),
"BARMAXCOR" : (3013,2,"""Barrier maximum correction limit. 
Sets the maximum number of centering corrections done on each iteration. An explicit value greater than 0 may improve the numerical performance of the algorithm at the expense of computation time. """),
"BAROBJRNG" : (3004,0,"""/strong> Barrier objective range. 
Sets the maximum absolute value of the objective function. The barrier algorithm looks at this limit to detect unbounded problems. """),
"BARORDER" : (3014,2,"""/strong> Barrier ordering algorithm. 
Sets the algorithm to be used to permute the rows of the constraint matrix in order to reduce fill in the Cholesky factor. """),
"BARQCPEPCOMP" : (3020,0,"""/strong> Convergence tolerance for quadratically constrained problems (QCP).  
For LPs and for QPs (that is, when all the constraints are linear) see CPX_PARAM_BAREPCOMP. 
Sets the tolerance on complementarity for convergence. The barrier algorithm terminates with an optimal solution if the relative complementarity is smaller than this value. 
Changing this tolerance to a smaller value may result in greater numerical precision of the solution, but also increases the chance of a convergence failure in the algorithm and consequently may result in no solution at all. Therefore, caution is advised in deviating from the default setting. """),
"BARSTARTALG" : (3017,2,"""Barrier starting point algorithm. 
Sets the algorithm to be used to compute the initial starting point for the barrier optimizer. """),
"BARTHREADS" : (3016,2,"""Barrier thread limit. 
Determines the maximum number of parallel processes (threads) that will be invoked by the parallel barrier optimizer. The default value of 0 means that the limit will be determined by the value of CPX_PARAM_THREADS, the global thread limit parameter. A positive value will override the value found in CPX_PARAM_THREADS. """),
"BBINTERVAL" : (2039,2,"""MIP strategy best bound interval. 
When you set this parameter to best estimate node selection, the bbinterval is the interval at which the best bound node, instead of the best estimate node, is selected from the tree. A bbinterval of 0 means to never select the best bound node. A bbinterval of 1 means always to select the best bound node, and is thus equivalent to nodeselect 1. Higher values of bbinterval mean that the best bound node will be selected less frequently; experience has shown it to be beneficial to occasionally select the best bound node, and therefore the default bbinterval is 7. """),
"BNDSTRENIND" : (2029,2,"""Bound strengthening indicator. 
Used when solving mixed integer programs. Bound strengthening tightens the bounds on variables, perhaps to the point where the variable can be fixed and thus removed from consideration during branch &amp; cut.  """),
"BRDIR" : (2001,2,"""MIP branching direction. 
Used to decide which branch, the up or the down branch, should be taken first at each node. """),
"BTTOL" : (2002,0,"""Backtracking tolerance. 
Controls how often backtracking is done during the branching process. The decision when to backtrack depends on three values that change during the course of the optimization: 
- the objective function value of the best integer feasible solution ("incumbent") 
- the best remaining objective function value of any unexplored node ("best node") 
- the objective function value of the most recently solved node ("current objective"). 
If a cutoff tolerance (see CPX_PARAM_CUTUP and CPX_PARAM_CUTLO) has been set by the user then that value is used as the incumbent until an integer feasible solution is found. The "target gap" is defined to be the absolute value of the difference between the incumbent and the best node, multiplied by this backtracking parameter. CPLEX does not backtrack until the absolute value of the difference between the objective of the current node and the best node is at least as large as the target gap. Low values of this backtracking parameter thus tend to increase the amount of backtracking, which makes the search process more of a pure best-bound search. Higher parameter values tend to decrease backtracking, making the search more of a pure depth-first search. The backtracking value has effect only after an integer feasible solution is found or when a cutoff has been specified. Note that this backtracking value merely permits backtracking but does not force it; CPLEX may choose to continue searching a limb of the tree if it seems a promising candidate for finding an integer feasible solution. """),
"CLIQUES" : (2003,2,"""MIP cliques indicator. 
Determines whether or not clique cuts should be generated for the problem. Setting the value to 0, the default, indicates that the attempt to generate cliques should continue only if it seems to be helping. """),
"CLOCKTYPE" : (1006,2,"""Computation time reporting. 
Determines how computation times are measured on UNIX platforms. Computation time on Windows systems is always measured as wall clock time. Small variations in measured time on identical runs may be expected on any computer system under either setting of this parameter. """),
"COEREDIND" : (2004,2,"""/strong> Coefficient reduction setting 
Determines how coefficient reduction is used. Coefficient reduction improves the objective value of the initial (and subsequent) LP relaxations solved during branch &amp; cut by reducing the number of non-integral vertices. """),
"COLREADLIM" : (1023,2,"""Variable (column) read limit. 
This parameter does not restrict the size of a problem. Rather, it indirectly specifies the default amount of memory that will be pre-allocated before a problem is read from a file. If the limit is exceeded, more memory is automatically allocated.  """),
"CONFLICTDISPLAY" : (1074,2,"""Conflict information display 
Determines what CPLEX reports when the conflict refiner is working. """),
"COVERS" : (2005,2,"""MIP covers indicator. 
Determines whether or not cover cuts should be generated for the problem. Setting the value to 0, the default, indicates that the attempt to generate covers should continue only if it seems to be helping. """),
"CRAIND" : (1007,2,"""Simplex crash ordering. 
Determines how CPLEX orders variables relative to the objective function when selecting an initial basis. """),
"CUTLO" : (2006,0,"""Lower cutoff. 
When the problem is a maximization problem, the lower cutoff parameter is used to cut off any nodes that have an objective value at or below the lower cutoff value. When a mixed integer optimization problem is continued, the larger of these values and the updated cutoff found during optimization are used during the next mixed integer optimization. A too-restrictive value for the lower cutoff parameter may result in no integer solutions being found. """),
"CUTPASS" : (2056,2,"""Number of cutting plane passes. 
Sets the upper limit on the number of cutting plane passes CPLEX performs when solving the root node of a MIP model. """),
"CUTSFACTOR" : (2033,0,"""Row multiplier factor for cuts. 
Limits the number of cuts that can be added. The number of rows in the problem with cuts added is limited to CUTSFACTOR times the original number of rows. If the problem is presolved, the original number of rows is that from the presolved problem. 
A CUTSFACTOR of 1.0 or less means that no cuts will be generated. Because cuts can be added and removed during the course of optimization, CUTSFACTOR may not correspond directly to the number of cuts seen during the node log or in the summary table at the end of optimization. """),
"CUTUP" : (2007,0,"""Upper cutoff. 
Cuts off any nodes that have an objective value at or above the upper cutoff value, when the problem is a minimization problem. When a mixed integer optimization problem is continued, the smaller of these values and the updated cutoff found during optimization are used during the next mixed integer optimization. A too-restrictive value for the upper cutoff parameter may result in no integer solutions being found. """),
"DATACHECK" : (1056,2,"""Data consistency checking indicator. 
When this parameter is set to CPX_ON, the routines CPXcopy____, CPXread____ and CPXchg____ perform extensive checking of data in their array arguments, such as checking that indices are within range, that there are no duplicate entries, and that values are valid for the type of data or are valid numbers. This checking is useful for debugging applications. When this checking identifies trouble, you can gather more specific detail by calling one of the routines in check.c. """),
"DEPIND" : (1008,2,"""Dependency indicator. 
Determines whether to activate the dependency checker. If on, the dependency checker searches for dependent rows during preprocessing. If off, dependent rows are not identified. """),
"DISJCUTS" : (2053,2,"""MIP disjunctive cuts indicator. 
Determines whether or not disjunctive cuts should be generated for the problem. Setting the value to 0, the default, indicates that the attempt to generate disjunctive cuts should continue only if it seems to be helping. """),
"DIVETYPE" : (2060,2,"""MIP dive strategy. 
The MIP traversal strategy occasionally performs probing dives, where it looks ahead at both children nodes before deciding which node to choose. The default (automatic) setting lets CPLEX choose when to perform a probing dive, 1 directs CPLEX never to perform probing dives, 2 always to probe, 3 spend more time exploring potential solutions that are similar to the current incumbent. Setting 2, always to probe, is helpful for finding integer solutions. """),
"DPRIIND" : (1009,2,"""Dual simplex pricing algorithm. 
The default pricing (0) usually provides the fastest solution time, but many problems benefit from alternate settings. """),
"EPAGAP" : (2008,0,"""Absolute mipgap tolerance. 
Sets an absolute tolerance on the gap between the best integer objective and the objective of the best node remaining. When this difference falls below the value of the EpAGap parameter, the mixed integer optimization is stopped. """),
"EPGAP" : (2009,0,"""Relative mipgap tolerance. 
Sets a relative tolerance on the gap between the best integer objective and the objective of the best node remaining. When the value  
 |bestnode-bestinteger|/(1e-10+|bestinteger|)  
falls below the value of the EpGap parameter, the mixed integer optimization is stopped. For example, to instruct CPLEX to stop as soon as it has found a feasible integer solution proved to be within five percent of optimal, set the relative mipgap tolerance to 0.05.  """),
"EPINT" : (2010,0,"""Integrality tolerance. 
Specifies the amount by which an integer variable can be different from an integer and still be considered feasible. A value of zero is permitted, and the optimizer will attempt to meet this tolerance. However, in some models, computer roundoff may still result in small, nonzero deviations from integrality. If any of these deviations exceed the value of this parameter, or exceed 1e-10 in the case where this parameter has been set to a value less than that, a solution status of CPX_STAT_OPTIMAL_INFEAS will be returned instead of the usual CPX_STAT_OPTIMAL. """),
"EPLIN" : (2068,0,"""Epsilon used in linearization. 
Sets the epsilon (degree of tolerance) used in linearization in Concert Technology. Not applicable in the Callable Library. Not available in the Interactive Optimizer. This parameter controls how strict inequalities are managed during linearization. In other words, it provides an epsilon for determining when two values are not equal during linearization. For example, when x is a numeric variable (that is, an instance of IloNumVar),  
x &lt; a  
becomes  
x &lt;= a-eplin.  
Similarly, x!=a  
becomes  
{(x &lt; a) || (x &gt; a)}  
which is linearized automatically for you in Concert Technology as  
{( x &lt;= a-eplin) || (x &gt;= a+eplin)}. 
Exercise caution in changing this parameter from its default value: the smaller the epsilon, the more numerically unstable the model will tend to become. If you are not getting an expected solution for a Concert Technology model that uses linearization, it might be that this solution is cut off because of the relatively high EpLin value. In such a case, carefully try reducing it.  """),
"EPMRK" : (1013,0,"""Markowitz tolerance. 
Influences pivot selection during basis factoring. Increasing the Markowitz threshold may improve the numerical properties of the solution. """),
"EPOPT" : (1014,0,"""Optimality tolerance. 
Influences the reduced-cost tolerance for optimality. This parameter governs how closely CPLEX must approach the theoretically optimal solution. """),
"EPPER" : (1015,0,"""Perturbation constant. 
Sets the amount by which CPLEX perturbs the upper and lower bounds or objective coefficients on the variables when a problem is perturbed in the simplex algorithm. This parameter can be set to a smaller value if the default value creates too large a change in the problem. """),
"EPRELAX" : (2073,0,"""Relaxation for feasOpt. 
This parameter controls the amount of relaxation for the routine CPXfeasopt in the Callable Library or the method feasOpt in Concert Technology.  
In the case of a MIP, it serves the purpose of the absolute gap for the feasOpt model in Phase I (the one to minimize relaxation). Using this parameter, you can implement other stopping criteria as well. To do so, first call feasOpt with the stopping criteria that you prefer; then set this parameter to the resulting objective of the Phase I model; unset the other stopping criteria, and call feasOpt again. Since the solution from the first call already matches this parameter, Phase I will terminate immediately in this second call to feasOpt, and Phase II will start. 
In the case of an LP, this parameter controls the lower objective limit (CPX_PARAM_OBJLLIM) for Phase I of feasOpt and is thus relevant only when the primal optimizer is in use. """),
"EPRHS" : (1016,0,"""Feasibility tolerance. 
The feasibility tolerance specifies the degree to which a problem's basic variables may violate their bounds. Feasibility influences the selection of an optimal basis and can be reset to a higher value when a problem is having difficulty maintaining feasibility during optimization. You may also wish to lower this tolerance after finding an optimal solution if there is any doubt that the solution is truly optimal. If the feasibility tolerance is set too low, CPLEX may falsely conclude that a problem is infeasible. If you encounter reports of infeasibility during Phase II of the optimization, a small adjustment in the feasibility tolerance may improve performance. """),
"FEASOPTMODE" : (1084,2,"""Mode of FeasOpt 
Determines how FeasOpt measures  the relaxation when finding a minimal relaxation in an infeasible model. FeasOpt works in two phases. In its first phase, it attempts to minimize its relaxation of the infeasible model. That is, it attempts to find a feasible solution that requires minimal change. In its second phase, it finds an optimal solution among those that require only as much relaxation as it found necessary in the first phase.  
Values of this parameter indicate two aspects to ILOG CPLEX: (1) whether to stop in phase one or continue to phase two and (2) how to measure the relaxation (as a sum of required relaxations; as the number of constraints and bounds required to be relaxed; as a sum of the squares of required relaxations). """),
"FLOWCOVERS" : (2040,2,"""MIP flow cover cuts indicator. 
Determines whether or not to generate flow cover cuts for the problem. Setting the value to 0, the default, indicates that the attempt to generate flow cover cuts should continue only if it seems to be helping. """),
"FLOWPATHS" : (2051,2,"""MIP flow path cut indicator. 
Determines whether or not flow path cuts should be generated for the problem. Setting the value to 0, the default, indicates that the attempt to generate flow path cuts should continue only if it seems to be helping. """),
"FRACCAND" : (2048,2,"""Candidate limit for generating Gomory fractional cuts. 
Limits the number of candidate variables for generating Gomory fractional cuts. """),
"FRACCUTS" : (2049,2,"""MIP Gomory fractional cuts indicator. 
Determines whether or not Gomory fractional cuts should be generated for the problem. Setting the value to 0, the default, indicates that the attempt to generate Gomory fractional cuts should continue only if it seems to be helping. """),
"FRACPASS" : (2050,2,"""Pass limit for generating Gomory fractional cuts. 
Limits the number of passes for generating Gomory fractional cuts. At the default setting of 0, CPLEX decides. The parameter is ignored if the Gomory fractional cut parameter, CPX_PARAM_FRACCUTS, is set to a nonzero value. """),
"GUBCOVERS" : (2044,2,"""MIP GUB cuts indicator. 
Determines whether or not to generate GUB cuts for the problem. Setting the value to 0, the default, indicates that the attempt to generate GUB cuts should continue only if it seems to be helping. """),
"HEURFREQ" : (2031,2,"""MIP heuristic frequency. 
Determines how often to apply the periodic heuristic. Setting the value to -1 turns off the periodic heuristic. Setting the value to 0, the default, applies the periodic heuristic at an interval chosen automatically. Setting the value to a positive number applies the heuristic at the requested node interval. For example, setting HEURISTICFREQ to 20 dictates that the heuristic be called at node 0, 20, 40, 60, etc.  """),
"IMPLBD" : (2041,2,"""MIP implied bound cuts indicator. 
Determines whether or not to generate implied bound cuts for the problem. Setting the value to 0, the default, indicates that the attempt to generate implied bound cuts should continue only if it seems to be helping. """),
"INTSOLLIM" : (2015,2,"""MIP solution limit. 
Sets the number of MIP solutions to be found before stopping. """),
"ITLIM" : (1020,2,"""Simplex maximum iteration limit. 
Sets the maximum number of iterations to be performed before the algorithm terminates without reaching optimality. When set to 0 (zero), no simplex method iteration occurs. However, CPLEX factors the initial basis from which solution routines provide information about the associated initial solution.  """),
"LBHEUR" : (2063,2,"""Local branching heuristic. 
This parameter lets you control whether CPLEX applies a local branching heuristic to try to improve new incumbents found during a MIP search. By default, this parameter is off. If you turn it on, CPLEX will invoke a local branching heuristic only when it finds a new incumbent. If CPLEX finds multiple incumbents at a single node, the local branching heuristic will be applied only to the last one found. """),
"LPMETHOD" : (1062,2,"""Algorithm for linear optimization. 
Determines which algorithm is used when CPXlpopt (or optimize in the Interactive Optimizer) is invoked. Currently, the behavior of the Automatic setting is that CPLEX almost always invokes the dual simplex algorithm when it is solving an LP model from scratch. When it is continuing from an advanced basis, it will check whether the basis is primal or dual feasible, and choose the primal or dual simplex algorithm accordingly. If multiple threads have been requested,   concurrent optimization algorithm is selected by the automatic setting. The Automatic setting may be expanded in the future so that CPLEX chooses the algorithm based on additional problem characteristics.  """),
"MEMORYEMPHASIS" : (1082,2,"""Reduces use of memory. 
This parameter lets you indicate to CPLEX that it should conserve memory where possible. When you set this parameter to its nondefault value, CPLEX will choose tactics, such as data compression or disk storage, for some of the data computed by the simplex,  barrier, and MIP optimizers. Of course, conserving memory may impact performance in some models. Also, while solution information will be available after optimization, certain computations that require a basis that has been factored (for example, for the computation of the condition number Kappa) may be unavailable. """),
"MIPCBREDLP" : (2055,2,"""MIP callback original or reduced, presolved model indicator. 
Controls whether your callback accesses vectors of the original model (off) or vectors of the reduced, presolved model (on, default). Advanced routines to control MIP callbacks (such as CPXgetcallbacklp, CPXsetheuristiccallbackfunc, CPXsetbranchcallbackfunc, CPXgetbranchcallbackfunc, CPXsetcutcallbackfunc, CPXsetincumbentcallbackfunc, CPXgetcallbacksosinfo, CPXcutcallbackadd, CPXcutcallbackaddlocal, and others) consider the setting of this parameter and access the original model or the reduced, presolved model accordingly.  
In the C++, Java, and .NET APIs of CPLEX, only the original model is available to callbacks. In other words, this parameter is effective only for certain advanced routines of the Callable Library. """),
"MIPDISPLAY" : (2012,2,"""MIP node log display information. 
Determines what CPLEX reports to the screen during mixed integer optimization. The amount of information displayed increases with increasing values of this parameter. A setting of 0 causes no node log to be displayed until the optimal solution is found. A setting of 1 displays an entry for each integer feasible solution found. Each entry contains the objective function value, the node count, the number of unexplored nodes in the tree, and the current optimality gap. A setting of 2 also generates an entry for every n-th node (where n is the setting of the MIP INTERVAL parameter). A setting of 3 additionally generates an entry for every nth node giving the number of cuts added to the problem for the previous INTERVAL nodes. A setting of 4 additionally generates entries for the LP root relaxation according to the set simplex display setting. A setting of 5 additionally generates entries for the LP subproblems, also according to the set simplex display setting. """),
"MIPEMPHASIS" : (2058,2,"""MIP emphasis indicator. 
With the default setting of BALANCED, CPLEX works toward a rapid proof of an optimal solution, but balances that with effort toward finding high quality feasible solutions early in the optimization. When this parameter is set to FEASIBILITY, CPLEX frequently will generate more feasible solutions as it optimizes the problem, at some sacrifice in the speed to the proof of optimality. When set to OPTIMALITY, less effort may be applied to finding feasible solutions early. With the setting BESTBOUND, even greater emphasis is placed on proving optimality through moving the best bound value, so that the detection of feasible solutions along the way becomes almost incidental. When the parameter is set to HIDDENFEAS, the MIP optimizer works hard to find high quality feasible solutions that are otherwise very difficult to find, so consider this setting when the FEASIBILITY setting has difficulty finding solutions of acceptable quality.  """),
"MIPINTERVAL" : (2013,2,"""MIP node log interval. 
Controls the frequency of node logging when CPX_PARAM_MIPDISPLAY is set higher than 1. """),
"MIPORDIND" : (2020,2,"""MIP priority order indicator. 
When set to on, uses the priority order (if it exists) for the next mixed integer optimization. """),
"MIPORDTYPE" : (2032,2,"""MIP priority order generation. 
Used to select the type of generic priority order to generate when no priority order is present. """),
"MIPTHREADS" : (2014,2,"""MIP thread limit 
Determines the maximum number of parallel processes (threads) that will be invoked by the Parallel MIP optimizer. The default value of 0 means that the limit will be determined by the value of CPX_PARAM_THREADS, the global thread limit parameter. A positive value will override the value found in CPX_PARAM_THREADS. """),
"MIRCUTS" : (2052,2,"""MIP MIR (mixed integer rounding) cut indicator. 
Determines whether or not to generate MIR cuts for the problem. Setting the value to 0, the default, indicates that the attempt to generate MIR cuts should continue only if it seems to be helping. """),
"MPSLONGNUM" : (1081,2,"""MPS and REW file format precision of numeric output. 
Determines the precision of numeric output in the MPS and REW file formats. When this parameter is set to its default value 1 (one), numbers are written to MPS files in full-precision; that is, up to 15 significant digits may be written. The setting 0 (zero) writes files that correspond to the standard MPS format, where at most 12 characters can be used to represent a value. This limit may result in loss of precision. """),
"NETDISPLAY" : (5005,2,"""Network logging display indicator. 
Settings 1 and 2 differ only during Phase I. Setting 2 shows monotonic values, whereas 1 usually does not. """),
"NETEPOPT" : (5002,0,"""Optimality tolerance for CPXNETprimopt. 
The optimality tolerance specifies the amount a reduced cost may violate the criterion for an optimal solution. """),
"NETEPRHS" : (5003,0,"""Feasibility tolerance for CPXNETprimopt. 
The feasibility tolerance specifies the degree to which a problem's flow value may violate its bounds. This tolerance influences the selection of an optimal basis and can be reset to a higher value when a problem is having difficulty maintaining feasibility during optimization. You may also wish to lower this tolerance after finding an optimal solution if there is any doubt that the solution is truly optimal. If the feasibility tolerance is set too low, CPLEX may falsely conclude that a problem is infeasible. If you encounter reports of infeasibility during Phase II of the optimization, a small adjustment in the feasibility tolerance may improve performance. """),
"NETFIND" : (1022,2,"""Simplex network extraction level. 
Establishes the level of network extraction for network simplex optimizations. The default value is suitable for recognizing commonly used modeling approaches when representing a network problem within an LP formulation. """),
"NETITLIM" : (5001,2,"""Network simplex iteration limit. 
Sets the maximum number of iterations to be performed before the algorithm terminates without reaching optimality. """),
"NETPPRIIND" : (5004,2,"""Network Simplex pricing algorithm. 
The default (0) shows best performance for most problems, and currently is equivalent to 3. """),
"NODEFILEIND" : (2016,2,"""Node storage file indicator. 
Used when working memory, (CPX_PARAM_WORKMEM, WorkMem) has been exceeded by the size of the tree. If the node file parameter is set to zero when the tree memory limit is reached, optimization is terminated. Otherwise, a group of nodes is removed from the in-memory set as needed. By default, CPLEX transfers nodes to node files when the in-memory set is larger than 128 MBytes, and it keeps the resulting node `files' in compressed form in memory. At settings 2 and 3, the node files are transferred to disk, in uncompressed and compressed form respectively, into a directory named by the parameter CPX_PARAM_WORKDIR (WorkDir), and CPLEX actively manages which nodes remain in memory for processing.  """),
"NODELIM" : (2017,2,"""MIP node limit. 
Sets the maximum number of nodes solved before the algorithm terminates without reaching optimality. When this parameter is set to 0 (zero), CPLEX does not create any nodes, but it does solve the root node LP relaxation and repeatedly apply cuts and resolve this LP. """),
"NODESEL" : (2018,2,"""MIP node selection strategy. 
Used to set the rule for selecting the next node to process when backtracking. The depth-first search strategy chooses the most recently created node. The best-bound strategy chooses the node with the best objective function for the associated LP relaxation. The best-estimate strategy selects the node with the best estimate of the integer objective value that would be obtained from a node once all integer infeasibilities are removed. An alternative best-estimate search is also available. """),
"NUMERICALEMPHASIS" : (1083,2,"""Emphasizes precision in numerically unstable or difficult problems. 
This parameter lets you indicate to CPLEX that it should emphasize precision in numerically difficult or unstable problems, with consequent performance trade-offs in time and memory. """),
"NZREADLIM" : (1024,2,"""Nonzero element read limit. 
This parameter does not restrict the size of a problem. Rather, it indirectly specifies the default amount of memory that will be pre-allocated before a problem is read from a file. If the limit is exceeded, more memory is automatically allocated.  """),
"OBJDIF" : (2019,0,"""Absolute objective difference cutoff. 
Used to update the cutoff each time a mixed integer solution is found. This absolute value is subtracted from (added to) the newly found integer objective value when minimizing (maximizing). This forces the mixed integer optimization to ignore integer solutions that are not at least this amount better than the best one found so far. The objective difference parameter can be adjusted to improve problem solving efficiency by limiting the number of nodes; however, setting this parameter at a value other than zero (the default) can cause some integer solutions, including the true integer optimum, to be missed. Negative values for this parameter can result in some integer solutions that are worse than or the same as those previously generated, but does not necessarily result in the generation of all possible integer solutions. """),
"OBJLLIM" : (1025,0,"""Lower objective value limit. 
Setting a lower objective function limit causes CPLEX to halt the optimization process once the minimum objective function value limit has been exceeded. This limit applies only during Phase II of the simplex algorithm. """),
"OBJULIM" : (1026,0,"""Upper objective value limit. 
Setting an upper objective function limit causes CPLEX to halt the optimization process once the maximum objective function value limit has been exceeded. This limit applies only during Phase II of the simplex algorithm. """),
"PERIND" : (1027,2,"""Simplex perturbation indicator. 
Setting this parameter to 1 causes all problems to be automatically perturbed as optimization begins. A setting of 0 allows CPLEX to determine dynamically, during solution, whether progress is slow enough to merit a perturbation. The situations in which a setting of 1 helps are rare and restricted to problems that exhibit extreme degeneracy. """),
"PERLIM" : (1028,2,"""Simplex perturbation limit. 
Sets the number of degenerate iterations before perturbation is performed. """),
"POLISHTIME" : (2066,0,"""Time spent polishing a solution. 
This parameter lets you indicate to CPLEX how much time in seconds to spend after a normal mixed integer optimization in polishing a solution. Default is zero, no polishing time. """),
"PPRIIND" : (1029,2,"""Primal Simplex pricing algorithm. 
The default pricing (0) usually provides the fastest solution time, but many problems benefit from alternative settings. """),
"PREDUAL" : (1044,2,"""Presolve dual setting. 
Determines whether CPLEX Presolve should pass the primal or dual linear programming problem to the linear programming optimization algorithm. By default, CPLEX chooses automatically. If the PreDual parameter is set to 1 (one), the CPLEX presolve algorithm is applied to the primal problem, but the resulting dual linear program is passed to the optimizer. This is a useful technique for problems with more constraints than variables. """),
"PREIND" : (1030,2,"""Presolve indicator. 
When set to 1, invokes the CPLEX Presolve to simplify and reduce problems. """),
"PRELINEAR" : (1058,2,"""Linear reduction indicator. 
If only linear reductions are performed, each variable in the original model can be expressed as a linear form of variables in the presolved model. This guarantees, for example, that users can add their own custom cuts to the presolved model. """),
"PREPASS" : (1052,2,"""Limit on the number of Presolve passes made. 
When set to a nonzero value, invokes CPLEX Presolve to simplify and reduce problems. 
When set to a positive value, Presolve is applied the specified number of times, or until no more reductions are possible. At the default value of -1, Presolve should continue only if it seems to be helping. 
When set to zero, CPLEX does not apply Presolve, but other reductions may occur, depending on settings of other parameters and specifics of your model. """),
"PRESLVND" : (2037,2,"""Node presolve selector. 
Indicates whether node presolve should be performed at the nodes of a mixed integer programming solution. Node presolve can significantly reduce solution time for some models. The default setting is generally effective at determining whether to apply node presolve, although runtimes can be reduced for some models by turning node presolve off. """),
"PRICELIM" : (1010,2,"""Simplex pricing candidate list size. 
Sets the maximum number of variables kept in the pricing candidate list. """),
"PROBE" : (2042,2,"""MIP probing level. 
Determines the amount of probing on variables to be performed before MIP branching. Higher settings perform more probing. Probing can be very powerful but very time consuming at the start. Setting the parameter to values above the default of 0 (automatic) can result in dramatic reductions or dramatic increases in solution time, depending on the model. """),
"PROBETIME" : (2065,0,"""Time spent probing 
Limits the amount of time in seconds spent probing. """),
"QPMAKEPSDIND" : (4010,2,"""Indefinite MIQP indicator. 
Determines whether CPLEX will attempt to reformulate a MIQP or MIQCP model that contains only binary variables. When this feature is active, adjustments will be made to the elements of a quadratic matrix that is not nominally positive semi-definite (PSD, as required by CPLEX for all QP and most QCP formulations), to make it PSD, and will also attempt to tighten an already PSD matrix for better numeric behavior. The default setting of 1 means yes, CPLEX should attempt to reformulate, but you can turn it off if necessary; most models should benefit from the default setting. """),
"QPMETHOD" : (1063,2,"""Algorithm for continuous quadratic optimization. 
Determines which algorithm is used when CPXqpopt (or optimize in the Interactive Optimizer) is invoked. Currently, the behavior of the Automatic setting is that CPLEX invokes the barrier optimizer for continuous QP models.  
The Automatic setting may be expanded in the future so that CPLEX chooses the algorithm based on additional problem characteristics. """),
"QPNZREADLIM" : (4001,2,"""QP Q matrix nonzero read limit. 
This parameter does not restrict the size of a problem. Rather, it indirectly specifies the default amount of memory that will be pre-allocated before a problem is read from a file. If the limit is exceeded, more memory is automatically allocated.  """),
"REDUCE" : (1057,2,"""Primal and dual reduction type. 
Determines whether primal reductions, dual reductions, both, or neither are performed during preprocessing. """),
"REINV" : (1031,2,"""Simplex refactoring frequency. 
Sets the number of iterations between refactoring of the basis matrix. """),
"RELAXPREIND" : (2034,2,"""Relaxed LP presolve indicator. 
Determines whether LP presolve is applied to the root relaxation in a mixed integer program. Sometimes additional reductions can be made beyond any MIP presolve reductions that were already done. By default, CPLEX applies presolve to the initial relaxation in order to hasten time to the initial solution.  """),
"RELOBJDIF" : (2022,0,"""Relative objective difference cutoff. 
Used to update the cutoff each time a mixed integer solution is found. The value is multiplied by the absolute value of the integer objective and subtracted from (added to) the newly found integer objective when minimizing (maximizing). This forces the mixed integer optimization to ignore integer solutions that are not at least this amount better than the one found so far. The relative objective difference parameter can be adjusted to improve problem solving efficiency by limiting the number of nodes; however, setting this parameter at a value other than zero (the default) can cause some integer solutions, including the true integer optimum, to be missed. If both RELOBJDIFFERENCE and OBJDIFFERENCE are nonzero, the value of OBJDIFFERENCE is used. """),
"REPAIRTRIES" : (2067,2,"""Try to repair infeasible MIP start. 
This parameter lets you indicate to CPLEX whether and how many times it should try to repair an infeasible MIP start that you supplied. The parameter has no effect if the MIP start you supplied is feasible. It has no effect if no MIP start was supplied. """),
"REPEATPRESOLVE" : (2064,2,"""Reapply presolve after processing the root node. 
This integer parameter tells CPLEX whether to re-apply presolve, with or without cuts, to a MIP model after processing at the root is otherwise complete.  """),
"RINSHEUR" : (2061,2,"""RINS heuristic frequency. 
Determines how often to apply the relaxation induced neighborhood search (RINS) heuristic. This heuristic attempts to improve upon the best solution found so far. It will not be applied until CPLEX has found at least one incumbent solution.  
Setting the value to -1 turns off the RINS heuristic. Setting the value to 0, the default, applies the RINS heuristic at an interval chosen automatically by CPLEX. Setting the value to a positive number applies the RINS heuristic at the requested node interval. For example,setting RINSHeur to 20 dictates that the RINS heuristic be called at node 0, 20, 40, 60, etc.  
RINS is a powerful heuristic for finding high quality feasible solutions, but it may be expensive. """),
"ROWREADLIM" : (1021,2,"""Constraint (row) read limit. 
This parameter does not restrict the size of a problem. Rather, it indirectly specifies the default amount of memory that will be pre-allocated before a problem is read from a file. If the limit is exceeded, more memory is automatically allocated.  """),
"SCAIND" : (1034,2,"""Scale parameter. 
Indicates how to scale the problem matrix. 
 """),
"SCRIND" : (1035,2,"""Messages to screen indicator. 
Indicates whether or not results messages are displayed on screen in a Callable Library application.  
To turn off output to the screen, in a C++ application, use cplex.setOut(env.getNullStream()), where cplex is an instance of the class IloCplex and env is an instance of the class IloEnv, the environment.  
In a Java application, use cplex.setOut(null).  
In a .NET application, use Cplex.SetOut(Null). """),
"SIFTALG" : (1077,2,"""Sifting subproblem algorithm 
Sets the algorithm to be used for solving sifting subproblems. The default automatic setting will typically use a mix of barrier and primal simplex. """),
"SIFTDISPLAY" : (1076,2,"""Sifting display information. 
Determines the amount of information to be displayed about the progress of sifting. 
 """),
"SIFTITLIM" : (1078,2,"""Upper limit on sifting iterations. 
Sets the maximum number of sifting iterations that may be performed if convergence to optimality has not been reached. """),
"SIMDISPLAY" : (1019,2,"""Simplex iteration display information. 
Determines how often CPLEX reports during simplex optimization. """),
"SINGLIM" : (1037,2,"""Simplex singularity repair limit. 
Restricts the number of times CPLEX attempts to repair the basis when singularities are encountered during the simplex algorithm. When this limit is exceeded, CPLEX replaces the current basis with the best factorable basis that has been found. """),
"STARTALG" : (2025,2,"""MIP starting algorithm. 
Determines which continuous optimizer will be used to solve the initial relaxation of a MIP.  
The default Automatic setting (0) of this parameter currently selects the dual simplex optimizer for root relaxations for MILP and MIQP. The Automatic setting may be expanded in the future so that CPLEX chooses the algorithm based on additional characteristics of the model.  
For MILP (integer constraints and otherwise continuous variables), all settings are permitted. 
For MIQP (integer constraints and positive semi-definite quadratic terms in the objective), settings 5 (Sifting) and 6 (Concurrent) are not implemented; if you happen to choose them, setting 5 (Sifting) reverts to 0 and setting 6 (Concurrent) reverts to 4.  
For MIQCP (integer constraints and positive semi-definite quadratic terms among the constraints), only the Barrier optimizer is implemented, and therefore no settings other than 0 and 4 are permitted.  """),
"SOLNPOOLINTENSITY" : (2107, 2, """ Controls the trade-off between the number of solutions generated for the solution pool and the amount of time or memory consumed. This parameter applies both to MIP optimization and to the populate procedure.
Values from 1 (one) to 4 invoke increasing effort to find larger numbers of solutions. Higher values are more expensive in terms of time and memory but are likely to yield more solutions."""),
"STRONGCANDLIM" : (2045,2,"""MIP candidate list  
Controls the length of the candidate list when CPLEX uses the setting strong branching variable selection (set mip strategy variableselect 3). """),
"STRONGITLIM" : (2046,2,"""MIP simplex iterations 
Controls the number of simplex iterations performed on each variable in the candidate list when CPLEX uses the setting strong branching variable selection (set mip strategy variableselect 3). The default setting 0 chooses the iteration limit automatically. """),
"STRONGTHREADLIM" : (2047,2,"""MIP parallel threads 
Controls the number of parallel threads used to perform strong branching. Note that this parameter does nothing if the MIP thread limit (set mip limits threads) is greater than 1. Note also that the global thread limit, CPX_PARAM_THREADS, does not affect this parameter. """),
"SUBALG" : (2026,2,"""MIP subproblem algorithm. 
Determines which continuous optimizer will be used to solve the subproblems in a MIP, after the initial relaxation.  
The default Automatic setting (0) of this parameter currently selects the dual simplex optimizer for subproblem solution for 
MILP and MIQP. The Automatic setting may be expanded in the future so that CPLEX chooses the algorithm based on additional characteristics of the model. 
For MILP (integer constraints and otherwise continuous variable), all settings are permitted.  
For MIQP (integer constraints and positive semi-definite quadratic terms in objective), setting 3 (Network) is not permitted, and setting 5 (Sifting) reverts to 0 (Automatic).  
For MIQCP (integer constraints and positive semi-definite quadratic terms among the constraints), only the Barrier optimizer is implemented, and therefore no settings other than 0 (Automatic) and 4 (Barrier) are permitted.  """),
"SUBMIPNODELIM" : (2062,2,"""Limit on nodes explored when a subMIP is being solved. 
Restricts the number of nodes explored when CPLEX is solving a subMIP. CPLEX solves subMIPs when it builds a solution from a partial MIP start, when repairing an infeasible MIP start, when executing the relaxation induced neighborhood search (RINS) heuristic, when branching locally, or when polishing a solution. """),
"SYMMETRY" : (2059,2,"""Symmetry breaking. 
Determines whether symmetry breaking reductions will be automatically executed, during the preprocessing phase, in a MIP model. """),
"THREADS" : (1067,2,"""Global default thread count. 
Determines the default number of parallel processes (threads) that will be invoked by any CPLEX parallel optimizer. This provides a convenient way to control parallelism with a single parameter setting. The value in place for this parameter can be overridden for any particular CPLEX parallel optimizer by setting the appropriate thread limit (CPX_PARAM_BARTHREADS or CPX_PARAM_MIPTHREADS). """),
"TILIM" : (1039,0,"""Global time limit. 
Sets the maximum time, in seconds, for a call to an optimizer. This time limit applies also to the conflict refiner. 
The time is measured in terms of either CPU time or elapsed time, according to the setting of the ClockType parameter. The time limit for an optimizer applies to the sum of all its steps, such as preprocessing,crossover, and internal calls to other optimizers.  
In a sequence of calls to optimizers, the limit is not cumulative but applies to each call individually. For example, if you set a time limit of 10 seconds, and you call mipopt twice then there could be a total of (at most) 20 seconds of running time if each call consumes its maximum allotment. """),
"TRELIM" : (2027,0,"""Tree memory limit. 
Sets an absolute upper limit on the size (in megabytes) of the branch &amp; cut tree. If this limit is exceeded, CPLEX terminates optimization. """),
"VARSEL" : (2028,2,"""MIP variable selection strategy. 
Sets the rule for selecting the branching variable at the node which has been selected for branching. The maximum infeasibility rule chooses the variable with the value furtherest from an integer; the minimum infeasibility rule chooses the variable with the value closest to an integer but still fractional. The minimum infeasibility rule (-1) may lead more quickly to a first integer feasible solution, but is usually slower overall to reach the optimal integer solution. The maximum infeasibility rule (1) forces larger changes earlier in the tree. Pseudo cost (2) variable selection is derived from pseudo-shadow prices. Strong branching (3) causes variable selection based on partially solving a number of subproblems with tentative branches to see which branch is the most promising. This strategy can be effective on large, difficult MIP problems. Pseudo reduced costs (4) are a computationally less-intensive form of pseudo costs. The default value (0) allows CPLEX to select the best rule based on the problem and its progress. """),
"WORKDIR" : (1064,3,"""/strong> Directory for working files. 
Specifies the name of an existing directory into which CPLEX may store temporary working files, such as for MIP node files or for out-of-core barrier. """),
"WORKMEM" : (1065,0,"""Memory available for working storage. 
Specifies an upper limit on the amount of central memory, in megabytes, that CPLEX is permitted to use for working memory before swapping to disk files. See also CPX_PARAM_WORKDIR, WorkDir. """)
}
    _v = {
        "ON" : 1, "OFF" : 0, "MAX" : -1, "MIN" : 1, "PPRIIND_PARTIAL" : -1,
        "PPRIIND_AUTO" : 0, "PPRIIND_DEVEX" : 1, "PPRIIND_STEEP" : 2,
        "PPRIIND_STEEPQSTART" : 3, "PPRIIND_FULL" : 4, "DPRIIND_AUTO" : 0,
        "DPRIIND_FULL" : 1, "DPRIIND_STEEP" : 2, "DPRIIND_FULLSTEEP" : 3,
        "DPRIIND_STEEPQSTART" : 4, "DPRIIND_DEVEX" : 5,
        "PARALLEL_DETERMINISTIC":1, "PARALLEL_AUTO":0,
        "PARALLEL_OPPORTUNISTIC":-1, "ALG_NONE" : -1,
        "ALG_AUTOMATIC" : 0, "ALG_PRIMAL" : 1, "ALG_DUAL" : 2, "ALG_NET" : 3,
        "ALG_BARRIER" : 4, "ALG_SIFTING" : 5, "ALG_CONCURRENT" : 6, "ALG_BAROPT" : 7,
        "ALG_PIVOTIN" : 8, "ALG_PIVOTOUT" : 9, "ALG_PIVOT" : 10, "ALG_FEASOPT" : 11,"ALG_MIP":12,
        "ALG_ROBUST" : 13, "AT_LOWER" : 0, "BASIC" : 1, "AT_UPPER" : 2, "FREE_SUPER" :
        3, "NO_VARIABLE" : 2100000000, "PREREDUCE_PRIMALANDDUAL" : 3,
        "PREREDUCE_DUALONLY" : 2, "PREREDUCE_PRIMALONLY" : 1,
        "PREREDUCE_NOPRIMALORDUAL" : 0, "FEASOPT_MIN_SUM" : 0, "FEASOPT_OPT_SUM" : 1,
        "FEASOPT_MIN_INF" : 2, "FEASOPT_OPT_INF" : 3, "FEASOPT_MIN_QUAD" : 4,
        "FEASOPT_OPT_QUAD" : 5, "BARORDER_AUTO" : 0, "BARORDER_AMD" : 1,
        "BARORDER_AMF" : 2, "BARORDER_ND" : 3, "MIPEMPHASIS_BALANCED" : 0,
        "MIPEMPHASIS_FEASIBILITY" : 1, "MIPEMPHASIS_OPTIMALITY" : 2,
        "MIPEMPHASIS_BESTBOUND" : 3, "MIPEMPHASIS_HIDDENFEAS" : 4, "VARSEL_MININFEAS"
        : -1, "VARSEL_DEFAULT" : 0, "VARSEL_MAXINFEAS" : 1, "VARSEL_PSEUDO" : 2,
        "VARSEL_STRONG" : 3, "VARSEL_PSEUDOREDUCED" : 4, "NODESEL_DFS" : 0,
        "NODESEL_BESTBOUND" : 1, "NODESEL_BESTEST" : 2, "NODESEL_BESTEST_ALT" : 3,
        "MIPORDER_COST" : 1 , "MIPORDER_BOUNDS" : 2 , "MIPORDER_SCALEDCOST" : 3,
        "BRANCH_GLOBAL" : 0, "BRANCH_DOWN" : -1, "BRANCH_UP" : 1, "BRDIR_DOWN" : -1,
        "BRDIR_AUTO" : 0, "BRDIR_UP" : 1, "NO_DISPLAY_OBJECTIVE" : 0, "TRUE_OBJECTIVE"
        : 1, "PENALIZED_OBJECTIVE" : 2, "PRICE_AUTO" : 0, "PRICE_PARTIAL" : 1,
        "PRICE_MULT_PART" : 2, "PRICE_SORT_MULT_PART" : 3}
    
    def __init__(self):
        pass

    def name(self,index):
        "Name of parameter given index"
        n = array('b',b"\x00"*CPX_STR_PARAM_MAX)		
        cplex.CPXgetparamname(Env,c_int(index),ptr(n))
        return n.tostring().strip(b'\x00').decode() # return as string
        
    def _lookup(self,index):
        "Return parameter (index,type) tuple"
        Env = globals()["Env"]
        if type(index) != type(""):
            id = c_int(index)
        else:
            if index in locals():
                id = c_int(locals()[index])
            elif "CPX_"+index in locals():
                id = c_int(locals()["CPX_"+index])
            elif "CPX_PARAM_"+index in locals():
                id = c_int(locals()["CPX_PARAM_"+index])
            else:
                id = c_int(0)
                tp = c_int(0)
                index = str(index).upper()
                if not index.startswith("CPX"): # is this a parameter??
                    if cplex.CPXgetparamnum(Env,("CPX_PARAM_"+index).encode(),byref(id))!=0:
                        id = c_int(0)
                if id.value <= 0 and cplex.CPXgetparamnum(Env,index.encode(),byref(id)) != 0:
                    id,tp,doc = self._p[index]
                    id = c_int(id)
        
        tp = c_int(0)
        cplex.CPXgetparamtype(Env,id,byref(tp))
        # CPLEX type numbers: 0 (None), 1 (int), 2 (double), 3 (string), 4 (long)
        # my type numbers: 0 (double), 1 (bool), 2 (int) or 3 (string), 4 (long) 
        return (id.value,[2,2,0,3,4][tp.value])
            
    def __getitem__(self,index):
        """param[index] returns parameter value.
        Index must be a string corresponding to a CPLEX parameter as defined
        in cplex.h (without the leading CPX_PARAM_) or the parameter index as an integer.
        Index is not case sensitive."""
        Env = globals()["Env"]
        id,type = self._lookup(index)
        id = c_int(id)
        if type == 0:
            v = c_double(0)
            cplex.CPXgetdblparam(Env,id,byref(v))
        elif type == 3:
            v = array('b',b" "*1024)
            cplex.CPXgetstrparam(Env,id,ptr(v))
            return v.decode()
        elif type == 4:
            v = c_long(0)
            cplex.CPXgetlongparam(Env,id,byref(v))
        else:
            v = c_int(0)
            cplex.CPXgetintparam(Env,id,byref(v))
        return v.value
    
    def __setitem__(self,index,value):
        """param[index] = value sets value
        Index must be a string corresponding to a CPLEX parameter as #defined
        in cplex.h (without the leading CPX_PARAM_) or an integer index
        Index is not case sensitive.
        If 'value' is a string for a numeric parameter, then it is assumed
        to refer to a names constant eg 'ON' or 'ALG_NET' as #defined in
        cplex.h but without the leading CPX_"""
        id,tp = self._lookup(index)
        id=c_int(id)
        Env = globals()["Env"]
        if tp != 3 and type(value) == type(""):
            value = self._v[value.upper()]
        #print "Setting",index,"(%d)"%id.value,"to",value
        if tp == 0:
            status = cplex.CPXsetdblparam(Env,id,c_double(float(value)))
        elif tp == 3:
            status = cplex.CPXsetstrparam(Env,id,str(value).encode())
        elif tp == 4:
            status = cplex.CPXsetlongparam(Env,id,c_long(value))
        else:
            status = cplex.CPXsetintparam(Env,id,c_int(int(value)))
        if status:
            print("ERROR",status,": setting parameter",index,"=",value)
            print("      Usage:",self._p[index.upper()][2]) # doc
        return status
        
    def keys(self): return CpxParam._p.keys()
    def has_key(self,item): return item.upper() in CpxParam._p
    def __in__(self,item): return item.upper() in CpxParam._p
    def get(self, key, failobj=None):
        if self.has_key(key): return self[key]
        else: return failobj
    def help(self,param):
        "Print documentation on parameter"
        print(self._p[param.upper()][2])
    def doc(self,param):
        "return documentation on parameter"
        return self._p[param.upper()][2]

    
class Model(object):
    """Define and solve linear programming models

    This class allows the creation of variables, defining
    equations and objectives and solves using CPLEX
    Fields:
    variable_count - number of variables
    var            - list of variables
    eqn            - list of all equations
    param          - dictionary of CPLEX parameters (see help(Model.param))
    Methods:
    variable(name) - create and return variable, name is a string
    max/min(obj)   - obj must be a linear expression giving the objective
    setCosts(obj)  - Like max/min but only modifies cost coeff. for
                     variables occuring in the expression. Also takes
                     a list of var,coefficient pairs
    SubjectTo(cons)- cons is a collection of constraints (can be list,
                     dictionary, single constraint, or list of lists...)
    addRows(cons)  - add list of constraints (after initial solve)
    deleteRows(rws)- remove list of constraints currently in the model
    mipStart(soln) - set initial solution (pairs of variable/values)
    optimise()     - relaxed solution, sets primal solution in .x field of vars 
    branchAndBound() - call after optimise() for solver's B&B method
    objective()    - objective value (after optimisation)
    status()       - solution status as string (after optimisation)

    Note:
      Changes to variable bounds/type even after the model has been optimised
      will be reflected in the model.
    """

    def __init__(self):
        D = self.VarDictionary = {None: -1} # constant/RHS
        N = self.var = []
        self.mip = False
        self.param = CpxParam()
        status = c_int(0)
        self.Env = globals()["Env"]
        cplex.CPXcreateprob.restype = c_void_p
        self.LP = c_void_p(cplex.CPXcreateprob(Env,byref(status),b"Model"))
        if status.value: print("ERROR %d: can't create LP" % status.value)
        self.solverInitialised = 0
        self.eqn = []
        self._eqnBlockCnt=0
        gc.disable()

    ## Destructor is not called because of circular references (in Variable and
    ## Constraint). Can be solved by using weak references but weak references
    ## cannot have attributes. Therefore explicitly call close until we found a
    ## solution to this issue
    #def __del__(self):
    #    cplex.CPXfreeprob.argcypes = [c_void_p,c_void_p]
    #    cplex.CPXfreeprob.argcypes = [c_void_p,c_void_p]
    #    if status.value: print "ERROR %d: unable to free LP\n" % status.value
    def close(self):
        cplex.CPXfreeprob.argcypes = [c_void_p,c_void_p]
        status = c_int(cplex.CPXfreeprob(self.Env,byref(self.LP)))
        if status.value: print("ERROR %d: unable to free LP\n" % status.value)

    def variable(self,name = "",type=b'C',lb=None,ub=None):
        "Create a new variable called 'name' and return it"
        if not name:
            name = "x%d" % len(self.var)
        if name in self.VarDictionary:
            return self.VarDictionary[name]
        v = self.VarDictionary[name] = Variable(self,name,len(self.var),type)
        self.var.append(v)
        if lb != None: v.lb = lb
        if ub != None: v.ub = ub
        return v
   
    def numRows(self):
        if self.solverInitialised:
            return cplex.CPXgetnumrows(self.Env,self.LP)
        return len(self.eqn)
    def numCols(self):
        if self.solverInitialised:
            return cplex.CPXgetnumcols(self.Env,self.LP)
        return len(self.var)
    def numNZ(self):
        "Return number of non-zero coefficients"
        if self.solverInitialised:
            return cplex.CPXgetnumnz(self.Env,self.LP)
        return sum( len(e.LHS) for e in self.eqn)
    
    def max(self,objective):
        """Set objective coefficients & objective type to maximise
        Objective can be an expression, a variable or a list of
        (variable,coefficient) pairs """
        self.sense = -1
        self.obj = array('d',len(self.var) * [0.0])
        if len(self.obj) == 0: return
        if type(objective) == ListType:
            coefList = objective
        elif type(objective) == ExpressionType:
            coefList = objective._expr.items()
        elif type(objective) == type(self.var[0]):    # variable?
            coefList = [ (objective,1.0) ]
        else:
            print("ERROR: Unknown objective type",type(objective),"ignored")
            return
        for (var,value) in coefList:
            if var: self.obj[var.id] = value
        if self.solverInitialised:
            indices = array('i',range(len(self.var))) 
            cplex.CPXchgobj(self.Env,self.LP,len(self.var),ptr(indices),
                            ptr(self.obj))
        gc.collect()                    # do interim garbage collection
    
    def min(self,objective):
        """Set objective coefficients & objective type to minimise.
        Objective can be an expression, a variable or a list of
        (variable,coefficient) pairs """
        self.sense = 1
        self.obj = array('d',len(self.var) * [0.0])
        if len(self.obj) == 0: return
        if type(objective) == ListType:
            coefList = objective
        elif type(objective) == ExpressionType:
            coefList = objective._expr.items() 
        elif type(objective) == type(self.var[0]):    # variable?
            coefList = [ (objective,1.0) ]
        else:
            print("ERROR: Unknown objective type",type(objective),"ignored")
            return
        for (var,value) in coefList:
            if var: self.obj[var.id] = value
        if self.solverInitialised:
            indices = array('i',range(len(self.var))) 
            cplex.CPXchgobj(self.Env,self.LP,len(self.var),ptr(indices),ptr(self.obj))
        gc.collect()                    # do interim garbage collection

    def setCosts(self,objective):
        """Set objective coefficients for variables in objective.
        Objective can be an expression or a list of (variable,value) pairs"""
        if type(objective) == ListType:
            coefList = objective
        else:                           # expression
            coefList = objective._expr.items()
        for var,coef in coefList:
            self.obj[var.id] = coef
        if self.solverInitialised:
            obj = array('d')
            idx = array('i')
            for var,coef in coefList:
                obj.append(coef)
                idx.append(var.id)
            cplex.CPXchgobj(self.Env,self.LP,len(obj),ptr(idx),ptr(obj))

    def changeRhs(self,Rhs):
        """Set the right hand side of constraints.
        Rhs can be a (constraint,value) pair or a list of (constraint,value) pairs."""
        if type(Rhs) == TupleType:
            rhsList = [Rhs]
        else:
            rhsList = Rhs
        ind = array("i",)
        rhs = array("d")
        for con,r in rhsList:
            con.RHS = r
            self.eqn[con.id].rhs = r
            ind.append(con.id)
            rhs.append(r)
        cplex.CPXchgrhs(self.Env,self.LP,c_int(len(ind)),ptr(ind),ptr(rhs))

    def changeConstraintSense(self,constraint):
        """Set the sense of constraints.
        constraint can be a (constraint,value) pair or a list of (constraint,value) pairs"""
        if type(constraint) == TupleType:
            senseList = [constraint]
        else:
            senseList = constraint
        ind = array("i")
        senses = array("b")
        for con,s in senseList:
            con.sense = s
            self.eqn[con.id].sense = s
            ind.append(con.id)
            senses.append(s)
        cplex.CPXchgsense(self.Env, self.LP, c_int(len(ind)), ptr(ind), ptr(senses))

    def changeConstraintCoeffs(self,constraint):
        """Change the coefficients of a constraint or a list of constraints."""
        print("NOT IMPLEMENTED YET")
#        CPXchgcoeflist(self.Env, self.LP, int numcoefs, const int * rowlist, const int * collist, const double * vallist)

    def _flattenConstraintList(self,*constraints,name=""):
        """Iterate over lists/tuples/dictionaries/... of constraints
        This is just a helper function for use by SubjectTo(), addRows()"""
        for constraint in constraints:
            cType = type(constraint)
            if cType is Constraint:
                constraint.name=name
                yield constraint
            elif cType is DictType: # assumes we have name:constraint
                for nm,row in constraint.items(): 
                    for c in self._flattenConstraintList(row,name=str(nm)):
                        yield c
            elif cType is type( (1,2) ) and len(constraint) == 2 and (
                   type(constraint[0]) is type("") or  type(constraint[1]) is type("")):
                if type(constraint[0]) is type(""):
                    for c in self._flattenConstraintList(constraint[1],name=constraint[0]):
                        yield c
                else:
                    for c in self._flattenConstraintList(
                            constraint[0],name=constraint[1]):
                        yield c                        
            elif isIterable(constraint):
                for i,item in enumerate(constraint):
                    for c in self._flattenConstraintList(item,name=name+"_%d"%i):
                        yield c
            else:
                raise Exception("Unknown constraint type "+str(cType))

    def _flattenVariableList(self,*vars):
        """Iterate over lists/tuples/dictionaries/... of constraints
        This is just a helper function for use by SubjectTo(), addRows()"""
        for v in vars:
            vType = type(v)
            if vType is Variable:
                yield v
            elif vType is DictType:
                for var in self._flattenVariableList(*v.values()):
                    yield var
            elif isIterable(v):
                for item in v:
                    for var in self._flattenVariableList(item):
                        yield var
            else:
                raise Exception("Unknown variable type "+str(vType))


    def SubjectTo(self,*constraints,name=""):
        """Add constraint or list of constraints. Pretty much any collection
        of constraints is allowed. Also can have multiple constraints added as
        multiple arguments.
        Eg: SubjectTo( sum(x[i][j] for j in N) == 1 for i in N )
        or  SubjectTo( [x[i][j] + x[j][i] == 1 for i in N for j in N if i<j])
        or  SubjectTo( { "s%d"%i: sum(x[i]) == 1 for i in N } ) # row names=s0,s1,...
        """
        if not name:
            name="R%d" % self._eqnBlockCnt
            self._eqnBlockCnt += 1
        if self.solverInitialised:
            self.addRows(*constraints,name=name)
        else:
            self.eqn += [c for c in self._flattenConstraintList(*constraints,name=name)]

    def newColumn(self,coefList=[],obj=0.0,lb=0,ub=1,name=""):
        """Add a new column/variable to the problem. With empty coefList this
        is just like variable() in creating a new variable. The coefList,
        if provided, must contain ordered pairs of the form (constraint,value)
        where constraint is an existing Constraint object previously added to
        the model.
        Ojb,lb,ub are the objective, lower and upper bound of the variable resp.
        Returns the newly created variable."""
        v = self.variable(name)
        v.lb = float(lb)  # not strictly speaking necessary if the problem
        v.ub = float(ub)  # is already in CPLEX but it's useful for consistency
                          # (and required if problem not yet loaded)
        if hasattr(self,"obj"): # alreay called min/max
            self.obj.append(float(obj))
        if self.solverInitialised: ## add directly to CPLEX
            lbArray = array('d',[float(lb)])
            ubArray = array('d',[float(ub)])
            objArray = array('d',[float(obj)])
            start = array('i',[0,len(coefList)])
            rowind = array('i')
            rowval = array('d')
            colname = (c_char_p*1)()
            colname[0] = str(v).encode() # convert to a proper c string
            for eqn,val in coefList:
                rowind.append(eqn.id)
                rowval.append(val)
            cplex.CPXaddcols(self.Env,self.LP,c_int(1),c_int(len(coefList)),
                             ptr(objArray),ptr(start),ptr(rowind),ptr(rowval),
                             ptr(lbArray),ptr(ubArray),
                             colname) # last argument is optional names
        else:
            v.setUpper(ub)
            v.setLower(lb)
            for eqn,val in coefList:
                eqn.LHS += val * v
        return v        

    def addRows(self,*constraints,name=""):
        """Add constraint or list of constraints.
        This method is like SubjectTo() but is intended for use when
        modifying the model after it has been initialised/loaded/optimised
        if name is given it is used as name for the constraint (If there are 
        multiple constraints then "_%d"%i is attached to each name)
        """
        if not name:
            name="R%d" % self._eqnBlockCnt
            self._eqnBlockCnt += 1
        if not self.solverInitialised: return self.SubjectTo(*constraints,name=name)
        numels = 0      
        elem = array("d")
        ind = array("i",)
        start = array("i",[0])
        rhs = array("d")
        sen = array("b")
        names = []
        for con in self._flattenConstraintList(*constraints):
            self.eqn.append(con)
            names.append( con.name.encode() if con.name else b"C%d"%len(self.eqn) )
            rhs.append(con.RHS)
            sen.append(con.sense[0])
            for (v,coef) in con.LHS.items():
                elem.append(coef)
                ind.append(v.id)
            numels += len(con.LHS)
            start.append(numels)
            con.setModel(self,len(self.eqn) - 1)
        rowname = (c_char_p*len(names))()
        for i,name in enumerate(names): rowname[i] = name
        cplex.CPXaddrows(self.Env,self.LP,
                         c_int(0), # no new columns. len(self.var),
                         c_int(len(rhs)),c_int(numels),
                         ptr(rhs),sen.tostring(),ptr(start),
                         ptr(ind),ptr(elem),c_void_p(0),rowname)
        #self.solver.addRows(len(cons),numels,ptr(elem),ptr(ind),ptr(start),
        #                    sen.tostring(),ptr(rhs))
    # end addRows

    def deleteRows(self,cons):
        "Delete list of constraints"
        if type(cons) is DictType:
            cons = cons.values()
        elif type(cons) is InstanceType:
            cons = [cons]
        rows = array("i",[0]*len(self.eqn))
        for c in cons: rows[c.id] = 1
        cplex.CPXdelsetrows(self.Env,self.LP,ptr(rows))
        for c in cons:
            self.eqn.remove(c)
            c.id = -1
            c._model = None
        for i in range(len(self.eqn)): self.eqn[i].id = i

    def load(self):
        """Put model from python data structures into CPLEX.
        This is normally done transparently when required but it can
        be useful to call this directly prior to calling CPLEX's print
        routines (for example)"""
        if self.solverInitialised: return
        collb = (c_double*len(self.var))()#array("d")
        colub = (c_double*len(self.var))()#array("d")
        colname = (c_char_p*len(self.var))()
        for i,v in enumerate(self.var):
            collb[i]=v.lb#collb.append(v.lb)
            colub[i]=v.ub#colub.append(v.ub)
            colname[i]=str(v).encode()
        colordered = 0 # are columns not major
        rhs = array("d",(con.RHS for con in self.eqn))
        sen = array('b', (con.sense[0] for con in self.eqn) )
        colCoef = [ [] for v in self.var]
        rowname=(c_char_p*max(1,len(self.eqn)))()
        for i,con in enumerate(self.eqn): # add equation to sparse matrix structure
            rowname[i]= con.name.encode() if con.name else b"C%d"%i
            for (v,coef) in con.LHS.items():
                colCoef[v.id].append((i,coef))
            con.setModel(self,i) # deletes con.LHS to free memory!
        nzCnt = sum( len(col) for col in colCoef)
        elem = array("d",(coef for col in colCoef for i,coef in col))
        ind = array("i",(i for col in colCoef for i,coef in col) )
        matcnt = array("i",(len(col) for col in colCoef))
        def accum(nums): # accumulator (generator)
            total = 0
            for x in nums:
                yield total
                total += x
            yield total
        start = array("i",accum(matcnt))
        rng = (c_double*max(1,len(self.eqn)))()#array("d",[0] * max(1,len(self.eqn)))
        # OK all data ready to go
        #print "ENV,LP,vars,eqns,sense:",self.Env,self.LP,len(self.var),\
        #        len(self.eqn),self.sense
        #print "Obj",self.obj
        #print "RHS:",rhs
        #print "Sense:",sen.tostring()
        #print "start:",start
        #print "M.cnt:",matcnt
        #print "M.ind:",ind
        #print "M.val:",elem
        #print "ColLB:",collb
        #print "ColUB:",colub
        #print "Range:",rng
        nRows = len(self.eqn)
        emptyRows = nRows == 0 and len(self.var) > 0
        if emptyRows: # create dummy row to work around a bug in cplex
            rhs.append(0.0)
            sen.append(b'E'[0])
            rowname[0]=b"dummy"
            nzCnt += 1
            elem.append(1.0)
            ind.append(len(self.var)-1) # last variable
            start[len(start)-1] = 1
            nRows = 1
        # cplex.CPXcopylp(self.Env,self.LP,c_int(len(self.var)),
        #                 c_int(nRows), c_char_p(self.sense),
        #                 ptr(self.obj),ptr(rhs),c_char_p(sen.tostring()),
        #                 ptr(start),ptr(matcnt),ptr(ind),ptr(elem),
        #                 ptr(collb),ptr(colub),ptr(rng))
        cplex.CPXcopylpwnames(
            self.Env,self.LP,c_int(len(self.var)),c_int(nRows),
            c_int(self.sense),ptr(self.obj),ptr(rhs),c_char_p(sen.tostring()),
            ptr(start),ptr(matcnt),ptr(ind),ptr(elem),
            collb,colub,rng,colname,rowname)
        if emptyRows: # delete dummy row
            cplex.CPXdelrows(self.Env,self.LP,0,0)
            #print "Loaded",cplex.CPXgetnumcols(self.Env,self.LP),"cols and",\
            #    cplex.CPXgetnumrows(self.Env,self.LP),"rows"
        ctype = array('b', b'C' * len(self.var))           
        for v in self.var:
            if not v.continuous:
                ctype[v.id] = b'I'[0]
                self.mip = True
        if self.mip:
            cplex.CPXcopyctype(self.Env,self.LP,c_char_p(ctype.tostring()))
        self.solverInitialised = True
        gc.enable()
        return  # end load()

    def mipStart(self,varvalPairs,effortLevel=CPX_MIPSTART_AUTO):
        """Provide a set of (variable,value) pairs that defines
        a solution (need not include every variable)
        The solution can be given as a dictionary, a list of pairs
        or a generator expression
        returns 0 if successful
        """
        mcnt=1
        if type(varvalPairs) == type({}):
            varvalPairs=varvalPairs.items()
        elif type(varvalPairs) == GeneratorType:
            varvalPairs = [vvp for vvp in varvalPairs]
        #else assume it's a list or set or similar
        idx=array('i',[vvp[0].id for vvp in varvalPairs])
        val=array('d',[vvp[1] for vvp in varvalPairs])
        beg=array('i',[0])
        eff=array('i',[effortLevel])
        return cplex.CPXaddmipstarts(self.Env,self.LP,1,len(val),ptr(beg),
                              ptr(idx),ptr(val),ptr(eff),c_void_p(0))
    
    def optimise(self):
        """Solve LP relaxation of problem using the model's solver.
        This function actually does the work of transfering data into the
        solver's internal data structures and is also responsible for storing
        the solution values back into the .x field of variables.
        """
        if not self.solverInitialised: self.load()
        with capture_c_stdout():
            if self.mip:
                cplex.CPXmipopt(self.Env,self.LP)
            else:
                cplex.CPXlpopt(self.Env,self.LP) #solve()
        # retrieve primal solution
        x = array("d",len(self.var) * [0])
        #if self.mip: # for CPLEXversion < 10 only
        #    CPXgetmipx(self.Env,self.LP,ptr(x),0,len(self.var)-1)
        #else:
        cplex.CPXgetx(self.Env,self.LP,ptr(x),0,len(self.var)-1)
        for v in self.var: v.x = x[v.id]
        if not self.mip:
            cplex.CPXgetdj(self.Env,self.LP,ptr(x),0,len(self.var)-1)
            for v in self.var: v.rc = x[v.id]
        # retrieve dual solution        
        x = array("d",len(self.eqn) * [0])
        cplex.CPXgetslack(self.Env,self.LP,ptr(x),0,len(self.eqn)-1)
        for eq in self.eqn: eq.slack = x[eq.id]
        if not self.mip:
            cplex.CPXgetpi(self.Env,self.LP,ptr(x),0,len(self.eqn)-1)
            for eq in self.eqn: eq.x = x[eq.id]

        # retrieve optimal base
        #self.cstat = array("i",[0]*len(self.var))
        #self.rstat = array("i",[0]*len(self.eqn))
        #e = cplex.CPXgetbase(self.Env, self.LP, ptr(self.cstat), ptr(self.rstat))
        #print 'base received: %i'%e

    def copyStart(self):
        """Start with the optimal base of the last run"""
        if self.solverInitialised == False:
            print('No solution found. Make sure to run optimise() first')
        else:
            print("copyStart() Not implemented")
            #cplex.CPXcopystart(self.Env,self.LP,ptr(self.cstat),ptr(self.rstat))
    def addStartSolution(self,solutions=None):
        """Add one or more initial MIP solutions
        Without arguments assumes that each var.x field has been set to desired
        solution. If solutions is a dictionary or list of dicionary, assumes
        that dictionary maps (a subset of) the variables to desired values
        """
        if not self.solverInitialised: self.load()
        mcnt = nzcnt = 0
        if not solutions:
            mcnt,nzcnt = 1,len(self.var)
        elif type(solutions) == type({}):
            mcnt,nzcnt = 1,len(solutions)
            solutions = [solutions]
        else:
            mcnt,nzcnt = len(solutions),sum(len(s) for s in solutions)
        beg = array('i',[0]*mcnt)
        varidx = array('i',range(nzcnt))
        values = array('d',[0]*nzcnt)
        # effort:  _AUTO, _CHECKFEAS,SOLVEFIXED, _SOLVEMIP, _REPAIR
        effort = array('i',[CPX_MIPSTART_AUTO]*mcnt)
        mipstartname=c_void_p(0) # could be char ** of length mcnt with names
        if not solutions:
            for i,v in enumerate(self.var): values[i] = v.x
        else:
            nzcnt =0
            for s,soln in enumerate(solutions):
                beg[s] = nzcnt
                for v,val in soln.items():
                    varidx[nzcnt] = v.id
                    values[nzcnt] = val
                    nzcnt += 1
        cplex.CPXaddmipstarts(self.Env,self.LP,c_int(mcnt),c_int(nzcnt),
                              ptr(beg),ptr(varidx),ptr(values),ptr(effort),
                              mipstartname)                
        

    def solve(self):
        "Another name for optimise()"
        self.optimise()
 
    def branchAndBound(self):
        """Redundant method: really just does optimise() assuming the
        problem has been set up (ie optimise was called previously)"""
        cplex.CPXmipopt(self.Env,self.LP)
        # retrieve primal solution
        x = array("d",len(self.var) * [0])
        cplex.CPXgetx(self.Env,self.LP,ptr(x),len(self.var))
        for v in self.var:
            v.x = x[v.id]      
        # retrieve dual solution - doesn't make sense for IP
        for eq in self.eqn:
            eq.x = None
    
    def objective(self):
        "Objective value"
        obj = array("d",[0.0])
        #if self.mip:      # for CPLEXversion < 10 only
        #    CPXgetmipobjval(self.Env,self.LP,obj.buffer_info()[0])
        #else:
        cplex.CPXgetobjval(self.Env,self.LP,ptr(obj))
        return obj[0]
        
    def getLowerBound(self):
        val = array("d",[0.0])
        cplex.CPXgetbestobjval(self.Env, self.LP, ptr(val))
        return val[0]

    def getNodeCnt(self):
        return cplex.CPXgetnodecnt(self.Env,self.LP)
        
    def getGap(self):
        val = array('d',[0.0])
        cplex.CPXgetmiprelgap(self.Env, self.LP, ptr(val))
        return val[0]
        
    def changeProblemType(self,new_type):
        """ Change the problem type. 
        new_type must be one of cpxconst
        e.g. cpxconst.CPXPROB_MILP"""
        cplex.CPXchgprobtype(self.Env, self.LP, new_type)
    
    def setPriorityOrder(self, vars, priority, direction="GLOBAL"):
        """ Sets the priority order for brance and bound
        index - list of variables
        priority - the priority for each variable (high number means branch first)
        direction - branch direction UP or DN for each variable
        priority & direction may be a single value which is used for all values
        """
        # map 'UP' to cplex.UP
        def str2Int(direction):
            if direction == 'UP':
                return CPX_BRANCH_UP
            elif direction.startswith('D'): # DN or DOWN
                return CPX_BRANCH_DOWN
            else: 
                return CPX_BRANCH_GLOBAL
                
        mIndex = array('i', map(lambda x: x.id,
                                self._flattenVariableList(vars)))
        if hasattr(priority,"__iter__"):
            mPriority = array('i', priority)
            if len(mPriority) < len(mIndex):
                mPriority = mPriority + array(
                    'i',[mPriority[-1]]*(len(mIndex)-len(mPriority)))
        else:
            mPriority = array('i',[int(priority)]*len(mIndex))
        if hasattr(direction,"__iter__"):
            mDirection = array('i', map(str2Int,direction))#['UP' for i in range(len(order))])
            if len(mDirection) < len(mIndex):
                mDirection = mDirection + array(
                    'i',[mDirection[-1]]*(len(mIndex)-len(mDirection)))
        else:
            mDirection = array('i',[str2Int(direction)]*len(mIndex))
        r = cplex.CPXcopyorder(self.Env, self.LP, len(mIndex), ptr(mIndex), ptr(mPriority), ptr(mDirection))
        return (r==0)
        
    def status(self):
        "Returns status of last optimise() as string"
        s = c_int(cplex.CPXgetstat(self.Env,self.LP))
        if s.value <= 0: return ""
        cplex.CPXgetstatstring.restype = c_char_p
        return cplex.CPXgetstatstring(self.Env,s,c_char_p(b" "*CPXMESSAGEBUFSIZE)).decode()
    def getStatusCode(self):
        "Returns the cplex status code as in http://eaton.math.rpi.edu/cplex90html/overviewcplex/statuscodes.html"
        return cplex.CPXgetstat(self.Env, self.LP)


    def setLogFile(self,filename):
        """Write CPLEX log output to the given filename
        There is currently no way to reverse this and direct output back to stdout
        if filename="" then output is disabled entirely
        Returns cplex's status value (0=success)
        """
        if not filename:
            return cplex.CPXsetlogfile(self.Env,c_void_p(0))
        cplex.CPXfopen.restype=c_void_p
        f = c_void_p(cplex.CPXfopen(filename.encode(),b"w"))
        return cplex.CPXsetlogfile(self.Env,f)
    
    def write(self,filename,filetype=None):
        """Write to file. Assumes filename ends with .lp or .mps etc to
        determine the type unless the filetype is explicitly given"""
        self.load()
        if not filetype: filetype = filename.split(".")[-1].upper()
        cplex.CPXwriteprob(self.Env,self.LP,filename.encode(),filetype.encode())
    
    def write_lp(self,filename):
        """Write to file. This must be called before model is solved or
        loaded. Does not call the internal CPLEX write method
        but explicitly writes to a text file using the given variable and 
        constraint names"""
        def getString(coef, var, counter = -1):
            r = ''
            
            if coef != 0:
                if coef > 0:
                    if not counter == 1:
                        r += ' +'
                elif coef < 0:
                    if coef == -1:
                        r += ' -'
                if (abs(coef) == 1):
                    r += ' '+var
                else:
                    r += ' {0} {1}'.format(coef, var)
            return r
            
        if self.solverInitialised:
            print("""Warning: Called load befor write_lp. Constraints cannot  be written
            correctly""")
        f = open(filename, 'w')
        # Objective
        if (self.sense == 1): 
            sense = 'Minimize'
        elif (self.sense == -1):
            sense = 'Maximize'
        else:
            print('objective sense wrong')
        f.write(sense+'\n obj: ')
        objective = "" #'{0} {1} '.format(self.obj[0],self.var[0]._name)
        counter = 1
        for id,coef in enumerate(self.obj):
            if(counter%3 == 0):
                # break every third line
                objective +='\n {:<6}'.format('')
                # we don't want to get stuck here
                if coef == 0:
                    counter += 1
            if coef > 0:
                objective += '+ {0} {1} '.format(coef,self.var[id]._name)
                counter += 1
            elif coef <0:
                objective += '{0} {1} '.format(coef,self.var[id]._name)
                counter += 1
            elif coef == 0.0:
                continue
            else:
                #that should not happen
                assert True, "Error!!"
        
        f.write(objective+'\n')
        # Constraints
        f.write('Subject To:\n')
        counter = 0;
        for con in self.eqn:
            cons = ' c{0}: '.format(counter)
            counter += 1
            termCounter = 1
            for (var,coef) in sorted(con.LHS.items(),reverse=True):
                if coef > 0:
                    cons += ' +'
                elif coef <0:
                    cons += ' -'
                elif coef == 0:
                    continue
                else:
                    #that should not happen
                    assert True, "Error!!"

                # format coefficients nicely, remove if 1
                coef = "{0:g}".format(abs(coef))
                if coef=="1":coef=""
                cons += '{0} {1}'.format(coef,var._name,)
                if(termCounter%10==0): cons+="\n {0:<{1}}".format("",len(str(counter))+2) #break every tenth line
            sense = { b'L' : " <= ", b'E' : " = ", b'G' : " >= "}
            cons += '{0} {1:g}'.format(sense[con.sense],con.RHS)
            f.write(cons+'\n')
        # Bounds
        f.write("Bounds \n")
        for var in self.var:
            f.write(" {0:g} <= {1} <= {2:g}\n".format(var.lb,var._name,var.ub))
        # Integers
        f.write("Integers \n")
        counter = 0
        for var in self.var:
            if not var.continuous:
                f.write(" {0} ".format(var._name))
                counter += 1
            if (counter%10==0):
                f.write("\n")
# end Model    

class Arc:
    """Arcs have a src and to node, and a net pointer
    Arcs are usually created after nodes with net.addArc(from,to,...)
    """
    def __init__(self,net,id,src,to,lb=0,ub=CPX_INFBOUND,obj=0,name=""):
        self.net = net
        self.id = id
        self.src = src
        self.to = to
        self.name=name
        self.lb,self.ub=lb,ub
        self.cost=obj
    def getCost(self):
        return self.cost
    def setCost(self,cost):
        self.cost = cost
        if self.net.solverInitialised:
            indices = array('i',[self.id])
            obj = array('d',[cost])
            cplex.CPXNETchgobj(self.net.Env,self.net.net,c_int(1),
                               ptr(indices),ptr(obj))
class Node:
    """Nodes for cplex network. These have
    id = index (from 0) used by cplex
    outArc = list out arcs
    inArc = list in arcs
    name, supply
    Nodes are usually create before arcs with net.addNode(name,supply)
    """
    def __init__(self,net,id,supply=0,name=""):
        self.net=net
        self.id = id
        self.name=name
        self.supply=supply
        self.outArc = []
        self.inArc = []
    def getSupply(self):
        return self.supply
    def setCost(self,supply,name):
        self.supply = supply
        if self.net.solverInitialised:
            indices = array('i',[self.id])
            sup = array('d',[cost])
            cplex.CPXNETchgobj(self.net.Env,self.net.net,c_int(1),
                               ptr(indices),ptr(obj))
    
            

class Network:
    """CPLEX Network solver
    Behaves a lot like a model but we don't explicitly add constraints:
    net.addNode(name,supply) # both name & supply optional
    net.addArc(fromNode,toNode,lb,ub,obj,name) returns an arc
    """
    def __init__(self,name=""):
        self.solverInitialised= False
        self.param = CpxParam() # very few network specific parameters
        self.Env = globals()["Env"]
        self.N = []                     # node list
        self.A = []                     # arc list
        self.sense=1 # min by default
        #cplex.CPXcreate
        self.net = None
    def addNode(self,supply,name=""):
        "Create a new node - should happen before adding arcs. Returns new node"
        self.N.append(Node(self,len(self.N),supply,name))
        return self.N[-1]
    def addArc(self,src,to,lb=0,ub=CPX_INFBOUND,obj=0,name=""):
        a = Arc(self,len(self.A),src,to,lb,ub,obj,name)
        self.A.append(a)
        src.outArc.append(a)
        to.inArc.append(a)
        return a
    def load(self):
        if self.solverInitialised: return
        status=c_int(0)
        cplex.CPXNETcreateprob.restype= c_void_p        
        self.net = c_void_p(cplex.CPXNETcreateprob(self.Env,byref(status),b'Network'))
        nN,nA=len(self.N),len(self.A)
        sup=(c_double*nN)()
        nname=(c_char_p*max(1,nN))()        
        for i,n in enumerate(self.N):
            sup[i] = n.supply
            nname[i]= n.name.encode() if n.name else b"N%d"%i
        lb=(c_double*nA)()
        ub=(c_double*nA)()
        obj=(c_double*nA)()
        aname=(c_char_p*max(1,nA))()
        for i,a in enumerate(self.A):
            lb[i]=a.lb
            ub[i]=a.ub
            obj[i]=a.cost
            aname[i]= a.name.encode() if n.name else b"A%d"%i
        fromNd=array("i",(a.src.id for a in self.A))
        toNd = array("i",(a.to.id for a in self.A))
        status=cplex.CPXNETcopynet(self.Env,self.net,c_int(self.sense),
                                   c_int(nN),sup,nname,
                                   c_int(nA),ptr(fromNd),ptr(toNd),lb,ub,obj,aname)
        self.solverInitialised=True
        
    def setObjective(self,objective):
        "Change objective coefficients (complete list, or dictionary arc : cost) "
        if not objective: return
        idx=None
        if type(objective) == type({}):
            idx= array('i',(a.id for a in objective.keys()))
            obj= array('d',(c  for c in objective.values()))
            for a,c in objective.items(): a.cost = c
        elif type(objective) == type([]):
            if len(objective)==len(self.A) and isinstance(objective[0],Number):
                idx=array('i',range(len(self.A)))
                obj=array('d',objective)
                for a,c in zip(self.A,objective): a.cost=c
            elif isinstance(objective[0],Arc): # set of modified arcs
                idx=array('i',(a.id for a in objective))
                obj=array('d',(a.cost for a in objective))
            else: # assume arc/cost pairs
                idx=array('i',(a.id for a,c in objective))
                obj=array('c',(c.id for a,c in objective))
                for a,c in objective: a.cost =c
        if not idx:
            print("ERROR: Could not process objective",objective)
            return
        cplex.CPXchgobj(self.Env,self.net,c_int(len(idx)),ptr(idx),ptr(obj))
    def max(self,objective=None):
        """Define maximisation objective - optionally with modified arc coefficients
        Objective may be a arc->coefficient mapping or a complete list of objective coefficients"""
        self.sense=-1
        if objective: self.setObjective(objective)
    def min(self,objective=None):
        "Problem is minimisation (default)"
        self.sense=1
        if objective: self.setObjective(objective)
    def optimise(self):
        "Solves optimisation. Sets arc.x=flow, node.x=dual"
        if not self.solverInitialised:
            self.load()
        status=cplex.CPXNETprimopt(self.Env,self.net)
        if status:
            return "ERROR: optimisation failed with status %d"%self.status
        x = array('d',[0]*len(self.A))
        cplex.CPXNETgetx(self.Env,self.net,ptr(x),c_int(0),c_int(len(self.A)-1))
        for i,a in enumerate(self.A): a.x = x[i]
        pi = array('d',[0]*len(self.N))
        cplex.CPXNETgetpi(self.Env,self.net,ptr(pi),c_int(0),c_int(len(self.N)-1))
        for i,n in enumerate(self.N): n.x = pi[i]
        return ""

    def solve(self):
        "Another name for optimise"
        self.optimise

    def objective(self):
        "Return objective value"
        obj=c_double(0)
        cplex.CPXNETgetobjval(self.Env,self.net,byref(obj))
        return obj.value

    def getSolninfo(self):
        """Return pair of integers to indicate primal & dual feasible.
        Should be (0,0) if feasible & optimal"""
        p,d=array('i',[0]),array('i',[0])
        cplex.CPXNETsolninfo(self.Env,self.net,ptr(p),ptr(d))
        return (p[0],d[0])

    def status(self):
        "Returns status of last optimise() as string"
        s = c_int(cplex.CPXNETgetstat(self.Env,self.net))
        if s.value <= 0: return ""
        cplex.CPXgetstatstring.restype = c_char_p
        return cplex.CPXgetstatstring(self.Env,s,c_char_p(b" "*CPXMESSAGEBUFSIZE)).decode()
       
    def write(self,filename,filetype=None):
        """Write to file. Filetype is inferred from the extension of the name:
        .net = CPLEX format
        .min = DIMACS ascii format
        .lp  = LP format
        .mps, .sav,.rlp,.alp are also possible"""
        if not self.solverInitialised:
            self.load()
        if not filetype: filetype=c_void_p(0)
        else: filetype=str(filetype).encode()
        cplex.CPXNETwriteprob(self.Env,self.net,str(filename).encode(),filetype)
        

if __name__ == "__main__":
      M = Model()
      M.param["SCRIND"] = "ON"
      M.setLogFile("xxx.log")
      print("Set",M.param.name(CPX_PARAM_SCRIND),"to:",M.param[CPX_PARAM_SCRIND])
      I = range(5)
      x,y,z = M.variable("x"),M.variable("y"),M.variable("z")
      for var in [x,y,z]:
          0 <= var <= 3
      eqn = (2 * x + y + 5 * z >= 18.0)
      M.min(x+y+z)
      M.SubjectTo( ("eqn",eqn) ) # equation with name
      print("Solving Min",x+y+z)
      print("Subject To:",str(eqn))
      print("            0 <= x,y,z <= 3")
      print("Model has %d vars %d eqns and %d coeff" % (M.numCols(),M.numRows(),M.numNZ()))
      M.load()
      print("Loaded model has %d vars %d eqns and %d coeff" % (M.numCols(),M.numRows(),M.numNZ()))
      print("Optimising...")
      M.optimise()      
      print("Objective value =",M.objective())
      print("Optimal solution =",[x.x,y.x,z.x],"  dual =",eqn.x)

