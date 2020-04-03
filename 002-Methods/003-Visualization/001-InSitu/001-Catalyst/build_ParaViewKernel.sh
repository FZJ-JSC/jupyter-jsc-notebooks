# INPUT NEEDED:
export KERNEL_NAME="paraviewkernel5.8"
export KERNEL_TYPE="private" # private or project
export KERNEL_VENVS_DIR=~/jupyter/kernels
export LOAD_PARAVIEW_COMMAND="module load ParaView/5.8.0-EGL-opengl-Python-3.6.8"
export LOAD_JUPYTER_COMMAND="module load Jupyter/2019a-devel-Python-3.6.8"
export UNLOAD_VTK_COMMAND="module unload VTK"


echo "Kernel Name:"
echo ${KERNEL_NAME}
echo "Kernel Type:"
echo ${KERNEL_TYPE}
echo "Kernel venvs dir:"
echo ${KERNEL_VENVS_DIR} # double check


###################
# private kernel
if [ ${KERNEL_TYPE} == "private" ]; then
  export KERNEL_SPECS_PREFIX=${HOME}/.local
  echo "private kernel"
# project kernel
else
  export KERNEL_SPECS_PREFIX=${PROJECT}/.local
  echo "project kernel"
fi
export KERNEL_SPECS_DIR=${KERNEL_SPECS_PREFIX}/share/jupyter/kernels

# check if kernel name is unique
if [ -d "${KERNEL_SPECS_DIR}/${KERNEL_NAME}" ]; then
  echo "ERROR: Kernel already exists in ${KERNEL_SPECS_DIR}/${KERNEL_NAME}"
  echo "       Rename kernel name or remove directory."
fi

echo ${KERNEL_SPECS_DIR}/${KERNEL_NAME} # double check



###################
mkdir -p ${KERNEL_VENVS_DIR}
if [ ${KERNEL_TYPE} != "private" ]; then
  echo "Please check the permissions and ensure your project partners have read/execute permissions:"
  namei -l ${KERNEL_VENVS_DIR}
fi


module -q purge
module -q use $OTHERSTAGES        
module -q load Stages/Devel-2019a 2> /dev/null # any stage can be used
module -q load GCCcore/.8.3.0     2> /dev/null
module -q load Python/3.6.8                    # only Python is required
#module -q load GCC/8.3.0
#module -q load ParaStationMPI/5.2.2-1
#module -q load ParaView/5.7.0-EGL-opengl-Python-3.6.8

module list # double check


python -m venv --system-site-packages ${KERNEL_VENVS_DIR}/${KERNEL_NAME}
source ${KERNEL_VENVS_DIR}/${KERNEL_NAME}/bin/activate
export PYTHONPATH=${VIRTUAL_ENV}/lib/python3.6/site-packages:${PYTHONPATH}
echo ${VIRTUAL_ENV} # double check

which pip
#pip install --ignore-installed ipykernel
ls ${VIRTUAL_ENV}/lib/python3.6/site-packages/ # double check


echo "#!/bin/bash

# Load required modules
module purge
module use "'$OTHERSTAGES'"
module load Stages/Devel-2019a
module load GCCcore/.8.3.0
module load Python/3.6.8

# Load extra modules you need for your kernel (as you did in step 1.2)
module load GCC/8.3.0
module load ParaStationMPI/5.2.2-1
${LOAD_PARAVIEW_COMMAND}
${LOAD_JUPYTER_COMMAND}
${UNLOAD_VTK_COMMAND}
module list
    
# Activate your Python virtual environment
source ${KERNEL_VENVS_DIR}/${KERNEL_NAME}/bin/activate
    
# Ensure python packages installed in the virtual environment are always prefered
export PYTHONPATH=${VIRTUAL_ENV}/lib/python3.6/site-packages:"'${PYTHONPATH}'"
echo ${PYTHONPATH}

exec python -m ipykernel "'$@' > ${VIRTUAL_ENV}/kernel.sh
chmod +x ${VIRTUAL_ENV}/kernel.sh

python -m ipykernel install --name=${KERNEL_NAME} --prefix ${VIRTUAL_ENV}
export VIRTUAL_ENV_KERNELS=${VIRTUAL_ENV}/share/jupyter/kernels

mv ${VIRTUAL_ENV_KERNELS}/${KERNEL_NAME}/kernel.json ${VIRTUAL_ENV_KERNELS}/${KERNEL_NAME}/kernel.json.orig

echo '{
  "argv": [
    "'${KERNEL_VENVS_DIR}/${KERNEL_NAME}/kernel.sh'",
    "-m",
    "ipykernel_launcher",
    "-f",
    "{connection_file}"
  ],
  "display_name": "'${KERNEL_NAME}'",
  "language": "python"
}' > ${VIRTUAL_ENV_KERNELS}/${KERNEL_NAME}/kernel.json

cd ${KERNEL_SPECS_DIR}
ln -s ${VIRTUAL_ENV_KERNELS}/${KERNEL_NAME} .
ls ${KERNEL_SPECS_DIR} # double check


deactivate
