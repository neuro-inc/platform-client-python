# image

Container image operations

## Usage

```bash
neuro image [OPTIONS] COMMAND [ARGS]...
```

Container image operations.

**Commands:**
| Usage | Description |
| :--- | :--- |
| [_ls_](image.md#ls) | List images |
| [_push_](image.md#push) | Push an image to platform registry |
| [_pull_](image.md#pull) | Pull an image from platform registry |
| [_rm_](image.md#rm) | Remove image from platform registry |
| [_size_](image.md#size) | Get image size Image name must be URL with... |
| [_digest_](image.md#digest) | Get digest of an image from remote registry... |
| [_tags_](image.md#tags) | List tags for image in platform registry |


### ls

List images


#### Usage

```bash
neuro image ls [OPTIONS]
```

List images.

#### Options

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |
| _-l_ | List in long format. |
| _--full-uri_ | Output full image URI. |
| _-n, --name NAME_ | Filter out images by name. |
| _-o, --owner TEXT_ | Filter out images by owner \(multiple option\). Supports `ME` option to filter by the current user. |



### push

Push an image to platform registry


#### Usage

```bash
neuro image push [OPTIONS] LOCAL_IMAGE [REMOTE_IMAGE]
```

Push an image to platform registry.

Remote image must be `URL` with image://
scheme.
Image names can contain tag. If tags not specified 'latest' will
be
used as value.

#### Examples

```bash

$ neuro push myimage
$ neuro push alpine:latest image:my-alpine:production
$ neuro push alpine image://myfriend/alpine:shared
```

#### Options

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |
| _-q, --quiet_ | Run command in quiet mode \(DEPRECATED\) |



### pull

Pull an image from platform registry


#### Usage

```bash
neuro image pull [OPTIONS] REMOTE_IMAGE [LOCAL_IMAGE]
```

Pull an image from platform registry.

Remote image name must be `URL` with
image:// scheme.
Image names can contain tag.

#### Examples

```bash

$ neuro pull image:myimage
$ neuro pull image://myfriend/alpine:shared
$ neuro pull image://username/my-alpine:production alpine:from-registry
```

#### Options

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |
| _-q, --quiet_ | Run command in quiet mode \(DEPRECATED\) |



### rm

Remove image from platform registry


#### Usage

```bash
neuro image rm [OPTIONS] IMAGES...
```

Remove image from platform registry.

Image name must be `URL` with image://
scheme.
Image name must contain tag.

#### Examples

```bash

$ neuro image rm image://myfriend/alpine:shared
$ neuro image rm image:myimage:latest
```

#### Options

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |
| _-f_ | Force deletion of all tags referencing the image. |



### size

Get image size Image name must be URL with...


#### Usage

```bash
neuro image size [OPTIONS] IMAGE
```

Get image size

Image name must be `URL` with image:// scheme.
Image name must
contain tag.

#### Examples

```bash

$ neuro image size image://myfriend/alpine:shared
$ neuro image size image:myimage:latest
```

#### Options

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |



### digest

Get digest of an image from remote registry...


#### Usage

```bash
neuro image digest [OPTIONS] IMAGE
```

Get digest of an image from remote registry

Image name must be `URL` with
image:// scheme.
Image name must contain tag.

#### Examples

```bash

$ neuro image digest image://myfriend/alpine:shared
$ neuro image digest image:myimage:latest
```

#### Options

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |



### tags

List tags for image in platform registry


#### Usage

```bash
neuro image tags [OPTIONS] IMAGE
```

List tags for image in platform registry.

Image name must be `URL` with
image:// scheme.

#### Examples

```bash

$ neuro image tags image://myfriend/alpine
$ neuro image tags -l image:myimage
```

#### Options

| Name | Description |
| :--- | :--- |
| _--help_ | Show this message and exit. |
| _-l_ | List in long format, with image sizes. |


