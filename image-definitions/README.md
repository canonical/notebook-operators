# Image Definitions

This directory contains image definitions for containers that are used in deployment of Notebook Operators. Only selected container images are maintained. The list of images and/or repositories can change. In addition, tools required to maintain container images are included in this repository:

- `setup.sh` - Used to setup initial image definitions and in maintanance of image definitions.
- `install-tools.sh` - Install all required tools for building, scanning, and publishing container images.
- `build.sh` - Build container images.
- `publish.sh` - Publish container images.
- `scan.sh` - Scan container images for vulnerabilities.

See [#Usage] for more details on each tool.

## Image Definitions

Image definitions contain copies of selected sources from upstream. These differ from one repository to the next. Scripts should be updated accordingly. In addtion, it is a good practice to update this README file with what repositories are tracked.

### Kubeflow

`setup.sh` contains a list of container images that are maintained in this repository from Kubeflow upstream repository (https://github.com/kubeflow/kubeflow.git). Sources for those images are located in `./kubeflow/` directory.

Additional resources are also located in this repository such as `base` and `common`. For detailed resources that these images require refer to `setup.sh` script.

There were modification done to `Makefile(s)` and `Dockerfiles(s)` to ensure bulding only required images.

Version of Kubeflow is retrieved and stored in `./kubeflow/version.txt`

## Usage

This repository contains tools - a collection of `bash` scripts - that help in maintenance of image definitions. All these tools are specific to image definitions for the repository they are in. Different repositories can be included and scripts are adjusted accordingly.

Required tools include Docker which might cause some conflicts on development machines. If required, image definiton work can be done in isolation on a VM. Using `multipass` create a VM and log into it:

```
multipass launch 20.04 --cpus 2 --mem 8G --disk 50G --name docker-vm
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

To build all container images:

```
build.sh
```

Tag will be set to contents of `version.txt` file. If different tag and registry required supply required parameters:

```
build.sh <tag> <registry>
```

Note that in some of `Makefile(s)` registry is ignored.

### Security scan

Scanning for vulnerabilities is done using `trivy` tool. Unfixed CVEs are ignored.

To perform security scan:

```
scan.sh
```

Tag will be set to contents of `version.txt`. If different tag and registry required supply required parameters:

```
scan.sh <tag> <registry>
```

### Publish

Login into the registry before running publishing of images. This step is left out of the tools on purposed to enable tools to be re-used in different scenarios such as Github workflows and manual publishing. For example, to login into Docker hub:

```
docker login --username <username> --password <password-or-access-token>
```

To publish all container images to the registry specified during build process:

```
publish.sh
```

Tag will be set to contents of `version.txt` file and registry will be set to default `charmedkubeflow`. If different tag and registry required supply required parameters:

```
publish.sh <tag> <registry>
```

In many cases only single image should be published. In such cases perform publishing manually based on the instructions in `publish.sh` script.

### Maintenance

From time to time an update in upstream source, an addition of new container image, or a new vulnerability fix will require re-evaluation of image definitions. To perform difference analysis between upstream, set up a clean copy of upstream source in temporary directory and diff the contents with current image definitions.

For Kubeflow:

```
mkdir ./update
setup.sh ./update
diff -r ./update/kubeflow kubeflow
```

Analyze differences and act accordingly, i.e. change `Makefiles` and/or `Dockerfile(s)`, add, remove, or modify image definitions in this repository.

In many cases difference in `Makefile(s)`, `Dockerfile(s)`, and `requirements.*` files should be carefully reviewed. Other files could be copied directrly.

This is a manual merge process. No automation can be done at this point.

Whenever making changes to image definitions include meaninful commit message that explains why changes were made.

Changes to the scripts might be required if Makefiles have changed.

To clean up all Docker images creared during build process:

```
docker rmi -f $(docker images -aq)
```