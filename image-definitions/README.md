# Image Definitions

This directory contains image definitions for containers that are used in deployment of Notebook Operators. Only selected container images are maintained. The list of images and/or repositories can change. In addition, tools required to maintain container images are included in this repository:

- `setup.sh` - Used to setup initial image definitions and in maintanance of image definitions.
- `install-tools.sh` - Install all required tools for building, scanning, and publishing container images.
- `build.sh` - Build container images.
- `publish.sh` - Publish container images.
- `scan.sh` - Scan container images for vulnerabilities.

See [#Usage] for more details on each tool.

## Image Definitions

Image definitions contain patches for selected sources from upstream. These differ from one repository to the next. Scripts should be updated accordingly. In addtion, it is a good practice to update this README file with what repositories are tracked.

### Kubeflow

Kubeflow repository `https://github.com/kubeflow/kubeflow.git`.

`setup.sh` contains a list of container images that are maintained in this repository from Kubeflow upstream repository (https://github.com/kubeflow/kubeflow.git). Patches for this repository are contained in `kubeflow*.patch` files.

For detailed resources that these images require refer to `setup.sh` script.

There were modification done to `Makefile`, `Dockerfile`, and `requirements.*` files to ensure bulding only required images.

When repository is setup a version of Kubeflow is retrieved and stored in `./kubeflow/version.txt` and a current commit is stored in `./kubeflow-patch-commit.txt`. The latter file is used in tagging images with specific commit ID. In addition, it can be used to the exact version of the tree the patch was created with.

## Usage

This repository contains tools - a collection of `bash` scripts - that help in maintenance of image definitions. All these tools are specific to image definitions for the repository they are in. Different repositories can be included and scripts are adjusted accordingly.

Required tools include Docker which might cause some conflicts on development machines. If required, image definiton work can be done in isolation on a VM. Using `multipass` create a VM and log into it:

```
multipass launch 20.04 --cpus 2 --mem 8G --disk 100G --name docker-vm
multipass shell docker-vm
```

Checkout this repository and perform all steps inside the VM.

### Tools install

To install all tools:

```
install-tools.sh
```

### Setup

To setup all required repositories:

```
setup.sh .
```

This will perform a sparse checkout of all required repositories in current (`.`) directory. Refer to `setup.sh` script for more detail on what directories are created. Those are also described in [Image Definitions](#image-definitions) section of this README.

Refere to [Maintenance](#maintenance) section for more details on how to use and create patches.

### Build

To build all container images:

```
build.sh
```

Tag will be set to contents of `version.txt` file. If different tag is required supply required parameters:

```
build.sh <tag>
```

Note that in some of `Makefile(s)` `REGISTRY` is ignored.

### Security scan

Scanning for vulnerabilities is done using `trivy` tool. Unfixed CVEs are ignored.

To perform security scan:

```
scan.sh
```

Tag will be set to contents of `version.txt`. If different tag is required supply required parameters:

```
scan.sh <tag>
```

Some images could be excluded from security scanning, because they are used as builder images. At this point all images are scanned for vulnerabilities.

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

To create initial patch setup a clean copy of upstream source, make required adjustments that would resolve CVEs and produced the initial patch:

For Kubeflow:

```
cd image-definitions
setup.sh .
cd kubeflow

# Manually make any modifications in the kubeflow directory, either by changing the files yourself
# or applying a patch

# Save a patch file describing your modified state
git diff > ../kubeflow.patch

# Save commit ID as base commit for the patch
git rev-parse --short HEAD > ../kubeflow-patch-commit.txt
```

Commit this patch to this repository. Commit `./kubeflow-patch-commit.txt` to this repository as well. This will ensure that it is possible to retrieve exact copy of the tree which `./kubeflow.patch` was based on. If required to work on particular version/commit of Kubeflow tree, after cloning this repo make a note of the commig stored in `./kubeflow-patch-commit.txt`, setup Kubeflow tree and checkout the noted commit ID. Then do the required work. Also note that scripts depend on `kubeflow-patch-commit.txt` file for tagging images.

From time to time an update in upstream source, an addition of new container image, or a new vulnerability fix will require re-evaluation of image definitions. To perform difference analysis between upstream, set up a clean copy of upstream source, apply existing patch and diff the contents with current image definitions.

For Kubeflow:

```
setup.sh .
cd kubeflow
git apply ../kubeflow.patch
git diff
```

Analyze differences and act accordingly, i.e. change `Makefiles` and/or `Dockerfile(s)`, add, remove, or modify image definitions in this repository.

In many cases difference in `Makefile(s)`, `Dockerfile(s)`, and `requirements.*` files should be carefully reviewed. Other files could be copied directrly.

This is a manual merge process. No automation can be done at this point.

Whenever making changes to image definitions include meaninful commit message that explains why changes were made.

If patch fails, examine which lines cause the problem and analyze the differences. In some cases upstream change could be integrated into patch. In other cases changes should be made to override that change.

Changes to the scripts might be required if Makefiles have changed.

Produce updated patch (in `kubeflow/` execute `git diff > ../kubeflow.patch`) and commit it to this repository.

To clean up all Docker images creared during build process:

```
docker rmi -f $(docker images -aq)
```

#### Notes

As of 23.01.01 when building upstream Kubeflow images the following error is seen:
```
ERROR: pip's dependency resolver does not currently take into account all the packages that are installed. This behaviour is the source of the following dependency conflicts.
jupyterlab-server 2.19.0 requires jsonschema>=4.17.3, but you have jsonschema 3.2.0 which is incompatible.
```
