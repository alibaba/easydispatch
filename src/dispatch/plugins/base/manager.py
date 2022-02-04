"""
.. module: dispatch.plugins.base.manager
    :copyright: (c) 2019 by Netflix Inc., see AUTHORS for more
    :license: Apache, see LICENSE for more details.

.. moduleauthor:: Kevin Glisson (kglisson@netflix.com)
"""
import logging
from dispatch.common.managers import InstanceManager


logger = logging.getLogger(__name__)


# inspired by https://github.com/getsentry/sentry
class PluginManager(InstanceManager):
    def __iter__(self):
        return iter(self.all())

    def __len__(self):
        return sum(1 for i in self.all())

    def __init__(self):
        self.plugins_sorted = None

    def all(self, version=1, plugin_type=None):
        if not self.plugins_sorted:
            self.plugins_sorted = sorted(super(PluginManager, self).all(), key=lambda x: x.title)
        return self.plugins_sorted
        for plugin in self.plugins_sorted:
            if not plugin.type == plugin_type and plugin_type:
                continue
            if not plugin.is_enabled():
                continue
            if version is not None and plugin.__version__ != version:
                continue
            # yield plugin
            return plugin

    def get(self, slug):
        for plugin in self.all(version=1):
            if plugin.slug == slug:
                return plugin
        for plugin in self.all(version=2):
            if plugin.slug == slug:
                return plugin
        logger.error(
            f"Unable to find slug: {slug} in self.all version 1: {self.all(version=1)} or version 2: {self.all(version=2)}"
        )
        raise KeyError(slug)

    def get_class(self, slug):
        for plugin in self.all_classes():
            if plugin.slug == slug:
                return plugin

        logger.error(
            f"Unable to find slug: {slug} in self.all version 1: {self.all(version=1)} or version 2: {self.all(version=2)}"
        )
        raise KeyError(slug)

    def first(self, func_name, *args, **kwargs):
        version = kwargs.pop("version", 1)
        for plugin in self.all(version=version):
            try:
                result = getattr(plugin, func_name)(*args, **kwargs)
            except Exception as e:
                logger.error(
                    f"Error processing {func_name}() on {plugin.__class__}: {e}",
                    extra={"func_arg": args, "func_kwargs": kwargs},
                    exc_info=True,
                )
                continue

            if result is not None:
                return result

    def register(self, cls):
        from dispatch.database import SessionLocal
        from dispatch.plugin import service as plugin_service
        from dispatch.plugin.models import Plugin

        db_session = SessionLocal()
        record = plugin_service.get_by_slug(db_session=db_session, slug=cls.slug)
        if cls.slug == "kandbox_env":
            logger.debug("Debugging loading kandbox_env")
        if not record:

            config = {}
            config_spec = {}
            try:
                config_spec = cls.config_form_spec
                config = cls.default_config
            except Exception as e:
                logger.warn(
                    f"Unable to find config spec for plugin: {cls.slug}, type = {cls.type} "
                )
            plugin = Plugin(
                title=cls.title,
                slug=cls.slug,
                type=cls.type,
                version=cls.version,
                author=cls.author,
                author_url=cls.author_url,
                required=cls.required,
                multiple=cls.multiple,
                description=cls.description,
                enabled=cls.enabled,
                config=config,
                config_form_spec=config_spec,
            )
            db_session.add(plugin)
        else:
            # we only update values that should change
            record.tile = cls.title
            record.version = cls.version
            record.author = cls.author
            record.author_url = cls.author_url
            record.description = cls.description
            db_session.add(record)

        db_session.commit()
        db_session.close()
        self.add(f"{cls.__module__}.{cls.__name__}")
        return cls

    def unregister(self, cls):
        self.remove(f"{cls.__module__}.{cls.__name__}")
        return cls
