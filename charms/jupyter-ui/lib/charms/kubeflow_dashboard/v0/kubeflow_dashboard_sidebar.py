"""# KubeflowDashboardSidebar Library
This library is designated to ease the process of adding the componentes 
to the UI sidebar of Kubeflow dashboard. The sidbar is dynamic and allows 
to add and remove items based on the configmap content.

In order to add an item to the library `sidebar` relation needs to be established
between the application which is going to be added and the kubeflow dashboard application.
At the joining event the joning application needs to send a json containing the sidebar element
details. Charm using this library is expected to provide these details on initialization.
These details are send through relation data.

These are the required fields:
- **type**: type of the sidebar element (only `item` option is allowed)
- **link**: relative path to the place of redirection.
- **text**: text of the displayed sidebar element
- **icon**: icon of the sidebar element

Bellow is the example (for tensorboards application) of json body. Remember list of configuration
is expected so one or many sidebars can be added at the same time:
```
{
    "position": 3,
    "type": "item",
    "link": "/tensorboards/",
    "text": "Tensorboards",
    "icon": "assessment",
}
```

In oder to remove the item from the sidebar `sidebar` relation needs to be removed.

## Getting Started

To get started using the library, you just need to fetch the library using `charmcraft`.

```shell
cd some-charm
charmcraft fetch-lib charms.kubeflow_dashboard.v0.kubeflow_dashboard_sidebar
```

Then, to initialise the library:

```python
from charms.kubeflow_dashboard.v0.kubeflow_dashboard_sidebar import (
    KubeflowDashboardSidebar,
)
# ...

SIDEBAR_LINK = [
    {
        "position": 4,
        "type": "item",
        "link": "/tensorboards/",
        "text": "Tensorboards",
        "icon": "assessment",
    }
] # list of items must be provided

class SomeCharm(CharmBase):
  def __init__(self, *args):
    # ...
    self.kubeflow_dashboard_sidebar = KubeflowDashboardSidebar(self, SIDEBAR_LINK)
    # ...
```
"""

import json
import logging

from typing import Dict
from ops.charm import CharmBase, RelationJoinedEvent, RelationDepartedEvent
from ops.framework import Object

logger = logging.getLogger(__name__)

# The unique Charmhub library identifier, never change it
LIBID = "a5795a88ee31458f9bc3ae026a04b89f"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1


class KubeflowDashboardSidebar(Object):
    def __init__(
        self,
        charm: CharmBase,
        sidebar_link: Dict,
    ):
        """Constructor for KubernetesServicePatch.

        Args:
            charm: the charm that is instantiating the library.
            sidebar_link: dictionary specifying the elemnt of the sidebar to be added.
        """
        super().__init__(charm, None)
        self.charm = charm
        self.sidebar_link = sidebar_link
        self.framework.observe(
            self.charm.on.sidebar_relation_joined,
            self._on_sidebar_relation_joined,
        )
        self.framework.observe(
            self.charm.on.sidebar_relation_departed,
            self._on_sidebar_relation_departed,
        )

    def _on_sidebar_relation_joined(self, event: RelationJoinedEvent):
        """Send the confing  on relation joined

        Args:
            event: relation joined object
        """
        if not self.charm.unit.is_leader():
            return
        event.relation.data[self.charm.app].update({"config": json.dumps(self.sidebar_link)})

    def _on_sidebar_relation_departed(self, event: RelationDepartedEvent):
        """Remove the confing  on relation departed

        Args:
            event: relation departed object
        """
        if not self.charm.unit.is_leader():
            return
        event.relation.data[self.charm.app].update({"config": json.dumps([])})
