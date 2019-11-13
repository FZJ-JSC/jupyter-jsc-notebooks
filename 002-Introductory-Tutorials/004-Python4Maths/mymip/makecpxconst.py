#!/usr/bin/env python3
USAGE = """Simple script to create cpxconst.py from cpxconst.h with all of the required constants
makecpxconst.py [/path/to/cpxconst.h]"""
import re,os,sys

cpxconstPath = ""
if len(sys.argv) == 2:
	if sys.argv[-1].startswith("-h"):
		print(USAGE)
		sys.exit(1)
	else:
		cpxconstPath = sys.argv[-1]
if not cpxconstPath or not os.path.exists(cpxconstPath):
	for path in ["/tools/ILOG/cplex125/cplex","/tools/ILOG/cplex125", r"C:\Program Files\IBM\ILOG\CPLEX_Studio125\cplex" "/usr/local/cplex/12.6.3/cplex"]:
		if os.path.exists(path):
			cpxconstPath = os.sep.join([path,"include","ilcplex","cpxconst.h"])
			if os.path.exists(cpxconstPath): break
if not cpxconstPath or not os.path.exists(cpxconstPath):
	print("Error cannot find cpxconst.h",cpxconstPath)
	sys.exit(2)

out = open("cpxconst.py","w")
tmp = ""
for line in open(cpxconstPath,"r").readlines():
	if tmp:
		line = tmp+line.strip()
	if not line.startswith("#define"): continue
	if line.strip().endswith("\\"):
		tmp = line.strip()[:-1]+" "
		continue
	else:
		tmp = ""
	field = line.strip().split()
	if len(field) < 3 or not field[1].startswith("CPX"): continue
	if field[2].startswith("_"): continue
	if field[2].startswith('"'):
		field[2] = " ".join(field[2:])
		if field[2][-1] != '"': field[2] += '"'
	if field[2].endswith("L") and field[2][-2].isdigit() :
		field[2] = field[2].strip("L") # long integer
	print(field[1],"=",field[2], file=out)
	
out.close()
print("Wrote cpxconst.py. Testing:", end=' ')
import cpxconst
print("OK")
