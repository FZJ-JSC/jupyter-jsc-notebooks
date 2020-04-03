coProcessor = None

def initialize():
    global coProcessor
    import paraview
    from vtk import vtkParallelCore
    import paraview.servermanager as pvsm
    import vtk
    from mpi4py import MPI
    import os, sys

    paraview.options.batch = True
    paraview.options.symmetric = True
    from paraview.modules import vtkRemotingServerManager as CorePython
    from paraview.modules.vtkRemotingApplication import vtkInitializationHelper

    if not pvsm.vtkProcessModule.GetProcessModule():
        pvoptions = None
        if paraview.options.batch:
            pvoptions = CorePython.vtkPVOptions();
            pvoptions.SetProcessType(CorePython.vtkPVOptions.PVBATCH)
            if paraview.options.symmetric:
                pvoptions.SetSymmetricMPIMode(True)
        vtkInitializationHelper.Initialize(sys.executable, pvsm.vtkProcessModule.PROCESS_BATCH, pvoptions)

    
    # we need ParaView 4.2 since ParaView 4.1 doesn't properly wrap
    # vtkPVPythonCatalyst
    if pvsm.vtkSMProxyManager.GetVersionMajor() < 4 or (pvsm.vtkSMProxyManager.GetVersionMajor() == 4 and pvsm.vtkSMProxyManager.GetVersionMinor() < 2):
        print('Must use ParaView v4.2 or greater')
        sys.exit(0)

    import numpy
    from paraview.modules import vtkPVCatalyst as catalyst
    from paraview.modules import vtkPVPythonCatalyst as pythoncatalyst
    import paraview.simple
    import paraview.vtk as vtk
    from paraview.vtk.util import numpy_support
    paraview.options.batch = True
    paraview.options.symmetric = True

    coProcessor = catalyst.vtkCPProcessor()
    pm = paraview.servermanager.vtkProcessModule.GetProcessModule()
    from mpi4py import MPI

def finalize():
    global coProcessor
    coProcessor.Finalize()
    # if we are running through Python we need to finalize extra stuff
    # to avoid memory leak messages.
    import sys, ntpath
    if ntpath.basename(sys.executable) == 'python':
        from paraview.modules.vtkRemotingApplication import vtkInitializationHelper
        vtkInitializationHelper.Finalize()

def addscript(name):
    global coProcessor
    from paraview.modules import vtkPVPythonCatalyst as pythoncatalyst
    pipeline = pythoncatalyst.vtkCPPythonScriptPipeline()
    pipeline.Initialize(name)
    coProcessor.AddPipeline(pipeline)

def coprocess(time, timeStep, grid, attributes):
    global coProcessor
    import vtk
    from paraview.modules import vtkPVCatalyst as catalyst
    import paraview
    from paraview.vtk.util import numpy_support
    dataDescription = catalyst.vtkCPDataDescription()
    dataDescription.SetTimeData(time, timeStep)
    dataDescription.AddInput("input")

    if coProcessor.RequestDataDescription(dataDescription):
        import fedatastructures
        imageData = vtk.vtkImageData()
        imageData.SetExtent(grid.XStartPoint, grid.XEndPoint, 0, grid.NumberOfYPoints-1, 0, grid.NumberOfZPoints-1)
        imageData.SetSpacing(grid.Spacing)

        velocity = numpy_support.numpy_to_vtk(attributes.Velocity)
        velocity.SetName("velocity")
        imageData.GetPointData().AddArray(velocity)

        pressure = numpy_support.numpy_to_vtk(attributes.Pressure)
        pressure.SetName("pressure")
        imageData.GetCellData().AddArray(pressure)
        dataDescription.GetInputDescriptionByName("input").SetGrid(imageData)
        dataDescription.GetInputDescriptionByName("input").SetWholeExtent(0, grid.NumberOfGlobalXPoints-1, 0, grid.NumberOfYPoints-1, 0, grid.NumberOfZPoints-1)
        coProcessor.CoProcess(dataDescription)
