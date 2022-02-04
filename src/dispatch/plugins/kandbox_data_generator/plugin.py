"""
.. module: dispatch.plugins.dispatch_pagerduty.plugin
    :platform: Unix
    :copyright: (c) 2019 by Netflix Inc., see AUTHORS for more
    :license: Apache, see LICENSE for more details.
"""
import logging

from dispatch.decorators import apply, counter, timer
from dispatch.plugins import kandbox_data_generator as this_plugin
from dispatch.plugins.bases import DataGeneratorPlugin

from .service import populate_all


log = logging.getLogger(__name__)


@apply(timer)
@apply(counter)
class BeijingDataGeneratorPlugin(DataGeneratorPlugin):
    title = "Data Generator Plugin - To generate sample Geo Location job and worker record"
    slug = "beijing-sample-data-generator"
    author = "Kandbox"
    author_url = "https://github.com/qiyangduan/kandbox_planner"
    description = "To generate sample Geo Location job and worker record."
    version = this_plugin.__version__

    def populate_all(self, service_id: str = None, service_name: str = None):
        """Gets the oncall person."""
        return populate_all(service_id=service_id, service_name=service_name)
