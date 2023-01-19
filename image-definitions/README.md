# Image Definitions

This directory contains image definitions for containers that are used in deployment of Notebook Operators. Only selected container images are maintained. The list of images can change. In addition, tools required to maintain container images are also included in this repository:

- `setup.sh` - Used to setup initial image definitions and in maintanance of image definitions.
- `install-tools.sh` - Used to install all required tools for building, scanning, and publishing container images.
- `build.sh` - Used to build container images.
- `publish.sh` - Used to publish container images.
- `scan.sh` - Used to scan container images for vulnerabilities.

See [#Usage] for more details on each tool.

## Image Definitions - Kubeflow

`setup.sh` contains a list of container images that are maintained in this repository from Kubeflow repository (https://github.com/kubeflow/kubeflow.git). Sources for those images are located in `./kubeflow/` directory.

Additional resources are also located in this repository such as `base` and `common`. For detailed resources that these images require refer to `setup.sh` script.

## Usage

This repository contains tools that help in maintenance of image definitions. Optionally these tools can be made executable for easy maintenance:

```
chmod +x *.sh
```

### Required tools

Tools include Docker which might cause some conflicts on development machines. If required, image definiton work can be done in isolation of a VM. Using `multipass` create a VM and log into it:

```
multipass launch 20.04 --cpus 2 --mem 8G --disk 30G --name docker-vm
multipass shell docker-vm
```
Checkout this repository and perform all steps inside the VM>.

### Tools install

To install all tools:

```
install-tools.sh
```

### Setup

Initial setup of image definitions was peformed. If required, initial setup can be done again using:

```
setup.sh .
```

This will create image definitions in current (`.`) directory.

### Build

To build all container images:

```
build.sh
```

If different tag and registry required supply required parameters:

```
build.sh <tag> <registry>
```

### Publish

To publish all container images:

```
publish.sh
```

### Security scan

To perform security scan:

```
scan.sh
```

### Maintenance

From time to time an update in upstream source or an addition of new container image will require re-evaluation of image definitions. To perform difference analysis between upstream set up a clean copy of upstream source in temporary directory and diff the contents with current image definitions.

For Kubeflow:

```
setup.sh new-kubeflow
diff new-kubeflow kubeflow
```

Analyze differences and act accordingly, i.e. change `Makefiles`, add, remove, of modify image definitions in this repository.

