from ipywidgets import *
w = Text(placeholder='Search')

def handle_submit(args):
    print(args['new'])
w.observe(handle_submit, names='value')

w