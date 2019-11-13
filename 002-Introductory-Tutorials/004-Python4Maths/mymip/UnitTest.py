### NEEDS UPDATING FOR PYTHON version 3.x
from mycplex import *

passed,failed=0,0

def OK(testPassed):
    if testPassed:
        global passed
        passed += 1
        print("OK")
    else:
        global failed
        failed += 1
    return testPassed

m = Model()
N = range(3)
x = [m.variable() for j in N]
m.min(x[0])
for i in N: 0 <= x[i] <= 1
#m.SubjectTo(0.1*x[0] <= 10)
#cplex.CPXdelrows(m.Env,m.LP,0,0)

print("Testing load with empty constraints ...",end="")
m.optimise()
if not OK(cplex.CPXgetnumcols(m.Env,m.LP) == len(N)):
    print("FAIL: Model has",cplex.CPXgetnumcols(m.Env,m.LP),"cols and",
          cplex.CPXgetnumrows(m.Env,m.LP),"rows")

print("Testing change bounds ...",end="")
x[0] == 2
m.optimise()
if not OK(m.objective() == 2.0):
    print("FAIL: x[0] fixed to",m.objective(),"not 2.0")

print("Testing change objective ...",end="")
x[1].setCost(-1.0)
m.optimise()
if not OK(x[1].x == 1.0 or x[1].getCost() != -1.0):
    print("FAIL: cost should be -1 but is",x[1].getCost()," x[1] =",x[1].x)

print("Testing adding row ...",end="")
m.addRows( sum(x) == 2, dict( (i,sum(x) <= 10+i) for i in N) )
m.optimise()
if not OK(x[1].x == 0.0):
    print("FAIL: addRow() didn't work correctly")

print("Testing change of variable type ...",end="")
x[2] in ZeroOne
m.max(sum(x))
m.addRows( 2*x[2] <= 1)
m.optimise()
if not OK(x[2].x == 0.0):
    print("FAIL: binary variable should have forced x[2]==0 but it's",x[2].x)

print("Passed %d tests and failed %d" % (passed,failed))


