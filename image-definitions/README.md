# Image Definitions

This directory contains image definitions for containers that are used in deployment of Notebook Operators. Only selected container images are maintained. The list of images can change. In addition, tools required to maintain container images are included in this repository:

- `setup.sh` - Setup initial image definitions and in maintanance of image definitions.
- `install-tools.sh` - Install all required tools for building, scanning, and publishing container images.
- `build.sh` - Build container images.
- `publish.sh` - Publish container images.
- `scan.sh` - Scan container images for vulnerabilities.

See [#Usage] for more details on each tool.

## Image Definitions - Kubeflow

`setup.sh` contains a list of container images that are maintained in this repository from Kubeflow upstream repository (https://github.com/kubeflow/kubeflow.git). Sources for those images are located in `./kubeflow/` directory.

Additional resources are also located in this repository such as `base` and `common`. For detailed resources that these images require refer to `setup.sh` script.

There were modification done to `Makefile(s)` to ensure bulding only required images.

Version of Kubeflow is retrieved and stored in `./kubeflow/version.txt`

## Usage

This repository contains tools - a collection of `bash` scripts - that help in maintenance of image definitions.

### Required tools

Required tools include Docker which might cause some conflicts on development machines. If required, image definiton work can be done in isolation on a VM. Using `multipass` create a VM and log into it:

```
multipass launch 20.04 --cpus 2 --mem 8G --disk 30G --name docker-vm
multipass shell docker-vm
```
Checkout this repository and perform all steps inside the VM.

### Tools install

To install all tools:

```
install-tools.sh
```

### Setup

Initial setup of image definitions was already peformed. If required, initial setup can be done again using:

```
setup.sh .
```

This will create image definitions in current (`.`) directory. Refer to `setup.sh` script for more detail on what directories are created.

### Build

To build all container images.

```
build.sh
```

Tag will be set to contents of `version.txt` file and registry will be set to default `charmedkubeflow`. If different tag and registry required supply required parameters, otherwise :

```
build.sh <tag> <registry>
```

### Publish

To publish all container images to the registry specified during build process:

```
publish.sh
```

### Security scan

To perform security scan:

```
scan.sh
```

### Maintenance

From time to time an update in upstream source or an addition of new container image will require re-evaluation of image definitions. To perform difference analysis between upstream, set up a clean copy of upstream source in temporary directory and diff the contents with current image definitions.

For Kubeflow:

```
mkdir ./update
setup.sh ./update
diff ./update/kubeflow kubeflow
```

Analyze differences and act accordingly, i.e. change `Makefiles`, add, remove, or modify image definitions in this repository.

