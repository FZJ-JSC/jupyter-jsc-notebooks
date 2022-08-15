from ipyparallel import interactive

@interactive
class C(object):
    a = 5

@interactive
class D(C):
    b = 10

@interactive
def foo(a):
    return a * b
