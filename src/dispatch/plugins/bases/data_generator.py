"""
.. module: dispatch.plugins.bases.oncall
    :platform: Unix
    :copyright: (c) 2019 by Netflix Inc., see AUTHORS for more
    :license: Apache, see LICENSE for more details.
.. moduleauthor:: Kevin Glisson <kglisson@netflix.com>
"""
from dispatch.plugins.base import Plugin
from dispatch.models import PluginOptionModel


class DataGeneratorPlugin(Plugin):
    type = "data_generator"
    _schema = PluginOptionModel

    def populate_all(self, **kwargs):
        raise NotImplementedError
