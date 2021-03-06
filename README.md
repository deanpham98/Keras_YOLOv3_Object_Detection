# YOLOv3
> YOLO version 3 repository for development

## Getting Started
> Instructions for setting up environments, source codes for both development and production. General docker commands for using the image

## Prerequisites
- Host machine must be a Linux machine (Preferably Ubuntu 16.04) with GPU having compute capability > 3.0. (Check out [here](https://developer.nvidia.com/cuda-gpus) for your GPU)
- nvidia driver ver. 390 is preferred (Install from [here](http://www.linuxandubuntu.com/home/how-to-install-latest-nvidia-drivers-in-linux) for Ubuntu 16.04)
- docker 18.03.1. (Install from [here](https://docs.docker.com/install/))
- nvidia-docker 2 (Install from [here](https://github.com/NVIDIA/nvidia-docker/blob/master/README.md))
- git 

## Setup Environment
Pull docker image from docker hub
```
docker pull nguyenkh001/vebits-yolov3:latest
```
**Note**: 
1/ Dockerfile for building this docker image is [here](/Dockerfile)
2/ This docker image includes:
- Ubuntu 16.04
- nvidia driver ver. 390
- Cuda 9.0
- Cudnn 7.0.5
- Python 3.5
- Pip 10.0.1
- Python libraries: numpy, pandas, matplotlib, scipy, scikit-learn, opencv 3.4, tensorflow-gpu 1.5, keras 2.1.6, IPython[all]

### Start the environment
**Run this scripts for simplicity:**
```
bash Scripts/docker.sh
```

### Docker commands
**nvidia-docker run** (Must not use **docker run**)
```
# Normal run command
nvidia-docker run nguyenkh001/vebits-yolov3:latest

# Naming the container with --name flag
nvidia-docker run --name yolov3 nguyenkh001/vebits-yolov3:latest

# Run the container in an interactive shell with -ti flag
nvidia-docker run -ti nguyenkh001/vebits-yolov3:latest

# Remove the container when it is stopped with --rm flag
nvidia-docker run --rm nguyenkh001/vebits-yolov3:latest

# To be able to use opencv with -v and -e flags (mounting volume and environment variable placement)
# Before that we need to run this command to allow non-network service to access host machine X11 server
xhost +local:root
# or
xhost +local:docker
# Run the image
nvidia-docker run -v /tmp/.X11-unix:/tmp/.X11-unix -e DISPLAY=$DISPLAY nguyenkh001/vebits-yolov3:latest
# After we finish using our container we need to run this command to return the access back to our host machine
xhost -local:root
# or
xhost -local:docker

# To be able to use jupyter notebook with -p flag (make connection between host machine's port and container's port)
nvidia-docker run -p <host-port>:8080 nguyenkh001/vebits-yolov3:latest

# To create a new volume, which will store everything in the directory /var/lib/docker/volumes/<name>/_data
docker volume create <name>

# To mount a volume from anywhere in your host machine (not necessarily created as above) to a directory inside the container, use -v flag
nvidia-docker run -v <volume-path-in-host-machine>:<directory-path-in-container> nguyenkh001/vebits-yolov3:latest

# To mount a volume in your host machine to your container when running the image
nvidia-docker run --mount source=<volume-name>,target=<path-in-container> nguyenkh001/vebits-yolov3:latest
```

**docker commit**
```
# To commit a change to the environment
docker commit <running-container-id> <new-image-name>
```

**docker container**
```
# To list all containers
docker ps

# To stop a container
docker container stop <container-name-or-id>

# To stop all container
docker container stop $(docker ps -qa)

# To remove a container
docker container rm <container-name-or-id>


# To remove all containers
docker container rm $(docker ps -qa)

# To inspect a container
docker inspect <container-name-or-id>
```

**docker image**
```
# To list all images
docker image ls

# To remove an image
docker image rm <image-name-or-id>
```

**docker volume**
```
# To create a new volume
docker volume create <volume-name>

# To inspect a volume
docker volume inspect <volume-name>

# To remove a volume
docker volume rm <volume-name>
```

## Source Code and Data
Download weights file [**yolov3.weights**](https://pjreddie.com/media/files/yolov3.weights):
```
wget https://pjreddie.com/media/files/yolov3.weights
```

Convert Darknet model to Keras model:
```
python setup/convert.py config/yolov3.cfg yolov3.weights models/yolo.h5
```

Download COCO data:
```
bash Scripts/get_coco_dataset.sh
```

Download Pascal VOC 2007 and 2012 data:
```
bash Scripts/get_voc_dataset.sh
```